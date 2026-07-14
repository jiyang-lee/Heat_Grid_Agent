import asyncio
import importlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
import orjson
import pytest
from sqlalchemy import text

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
SERVER_PATH: Final = BACKEND_DIR / "server.py"


@pytest.fixture
def anyio_backend():
    return ("asyncio", {"loop_factory": asyncio.SelectorEventLoop})


def load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("v2_postgres_react_ops_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("v2 서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def reset_contract_tables(module: ModuleType) -> None:
    async with module.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE agent_policy_candidates, agent_run_reviews, "
                "agent_run_review_snapshots, agent_budget_ledger, agent_run_tasks, "
                "agent_run_actions, agent_run_artifacts, agent_run_events, "
                "agent_runs, ops_alert_queue CASCADE"
            )
        )


async def wait_for_agent_run(client: AsyncClient, run_id: str) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(f"/api/agent-runs/{run_id}")
        payload = response.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        await asyncio.sleep(0.025)
    raise AssertionError(f"agent run {run_id} did not finish")


async def wait_for_review_snapshot(client: AsyncClient, run_id: str) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(f"/api/agent-runs/{run_id}/review")
        payload = response.json()
        if payload.get("status") == "available":
            return payload
        await asyncio.sleep(0.025)
    raise AssertionError(f"agent run {run_id} review snapshot did not finish")


@pytest.mark.anyio
async def test_v2_postgres_tools_return_ops_and_external_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    card_ids = await module.list_card_ids(module.engine)
    source_input = await module.input_for_card(card_ids[0])
    external_context = await module.external_context_for(card_ids[0], source_input)
    tools = {item.name: item for item in module.tools_for(source_input, external_context)}

    evidence = orjson.loads(tools["get_ops_evidence"].invoke({"card_id": card_ids[0]}))
    context = orjson.loads(tools["get_external_context"].invoke({"card_id": card_ids[0]}))
    references = orjson.loads(
        tools["get_internal_references"].invoke({"card_id": card_ids[0]})
    )

    assert set(tools) == {
        "get_ops_evidence",
        "get_priority_snapshot",
        "get_substation_context",
        "get_sensor_evidence",
        "get_model_evidence",
        "get_internal_references",
        "get_external_context",
        "get_agent_loop_context",
    }
    assert "site" in context
    assert "weather" in context
    assert "retrieval" in references
    assert evidence["priority_context"]["card"]["card_id"] == card_ids[0]
    assert "model_outputs" in evidence["priority_context"]
    assert isinstance(evidence["priority_context"]["model_outputs"], list)
    assert "raw_context" in evidence

@pytest.mark.anyio
async def test_api_server_exposes_health_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        root = await client.get("/")
        health = await client.get("/health")
        openapi = await client.get("/openapi.json")

    assert root.status_code == 200
    assert root.json()["service"] == "HeatGrid V2 API"
    assert root.json()["health"] == "/health"
    assert root.json()["docs"] == "/docs"
    assert "/api/alerts" in root.json()["apis"]
    assert health.status_code == 200
    assert health.json()["input"] == "postgresql"
    assert health.json()["database"] in {"connected", "unavailable"}
    assert openapi.status_code == 200
    assert "/api/alerts" in openapi.json()["paths"]
    assert "/api/agent-runs" in openapi.json()["paths"]
    assert "/api/agent-runs/{run_id}/reports/daily" in openapi.json()["paths"]
    assert "/api/priority-evaluations/latest" in openapi.json()["paths"]


@pytest.mark.anyio
async def test_api_alerts_enqueue_list_ack_and_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        enqueue = await client.post("/api/alerts/enqueue")
        duplicate_enqueue = await client.post("/api/alerts/enqueue")
        open_alerts = await client.get("/api/alerts", params={"status": "open"})
        first_alert = open_alerts.json()[0]
        detail = await client.get(f"/api/alerts/{first_alert['alert_id']}")
        ack = await client.post(
            f"/api/alerts/{first_alert['alert_id']}/ack",
            json={"acked_by": "pytest"},
        )
        resolved = await client.post(
            f"/api/alerts/{first_alert['alert_id']}/resolve",
            json={"acked_by": "pytest"},
        )

    assert enqueue.status_code == 200
    assert enqueue.json()["queued_count"] > 0
    assert enqueue.json()["existing_count"] == 0
    assert duplicate_enqueue.status_code == 200
    assert duplicate_enqueue.json()["queued_count"] == 0
    assert duplicate_enqueue.json()["existing_count"] == enqueue.json()["queued_count"]
    assert open_alerts.status_code == 200
    assert first_alert["priority_level"] in {"urgent", "high"}
    assert first_alert["evaluation_run_id"] == enqueue.json()["evaluation_run_id"]
    assert first_alert["freshness_status"] == "fresh"
    assert detail.status_code == 200
    assert detail.json()["alert_id"] == first_alert["alert_id"]
    assert ack.status_code == 200
    assert ack.json()["status"] == "acked"
    assert ack.json()["acked_by"] == "pytest"
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


@pytest.mark.anyio
async def test_api_agent_run_creates_completed_run_from_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        enqueue = await client.post("/api/alerts/enqueue")
        alerts = await client.get("/api/alerts", params={"status": "open"})
        alert = alerts.json()[0]
        created = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        run_id = created.json()["run_id"]
        completed = await wait_for_agent_run(client, run_id)
        fetched = await client.get(f"/api/agent-runs/{run_id}")
        artifacts = await client.get(f"/api/agent-runs/{run_id}/artifacts")
        iterations = await client.get(f"/api/agent-runs/{run_id}/iterations")
        events = await client.get(f"/api/agent-runs/{run_id}/events")
    async with module.engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT event_type FROM agent_run_events "
                "WHERE run_id = :run_id ORDER BY event_id"
            ),
            {"run_id": run_id},
        )
    event_types = [str(row["event_type"]) for row in result.mappings().all()]

    assert enqueue.status_code == 200
    assert created.status_code == 200
    assert created.json()["status"] == "queued"
    assert completed["status"] == "completed"
    assert completed["alert_id"] == alert["alert_id"]
    assert completed["card_id"] == alert["card_id"]
    assert completed["evaluation_run_id"] == alert["evaluation_run_id"]
    assert completed["substation_id"] == alert["substation_id"]
    assert completed["agent_mode"] == "fallback"
    assert completed["ops_output"]["summary"]
    assert completed["loop_summary"]["iterations"] >= 1
    assert completed["loop_summary"]["model_verification"]["status"] in {
        "verified",
        "partial",
        "unavailable",
        "error",
    }
    assert completed["loop_summary"]["model_verification"]["evaluation_run_id"] == alert["evaluation_run_id"]
    assert completed["loop_summary"]["model_verification"]["substation_id"] == alert["substation_id"]
    assert completed["review_status"] == "pending"
    assert completed["review_task_id"]
    assert fetched.status_code == 200
    assert fetched.json() == completed
    assert artifacts.status_code == 200
    assert artifacts.json() == []
    assert iterations.status_code == 200
    assert iterations.json()
    assert events.status_code == 200
    assert '"type":"run_started"' in events.text
    assert '"type":"run_queued"' in events.text
    assert '"type":"status_changed"' in events.text
    assert '"type":"graph_transition"' in events.text
    assert '"type":"tool_started"' in events.text
    assert '"type":"tool_completed"' in events.text
    assert '"type":"final_output"' in events.text
    assert '"type":"run_completed"' in events.text
    assert '"type":"report_failed"' in events.text
    assert event_types[:4] == [
        "run_queued",
        "status_changed",
        "status_changed",
        "run_started",
    ]
    assert "graph_transition" in event_types
    assert "model_verification" in event_types
    assert "loop_decision" in event_types
    assert "review_requested" in event_types
    assert event_types.index("final_output") < event_types.index("review_requested")
    assert event_types.index("review_requested") < event_types.index("run_completed")
    assert "report_failed" in event_types


@pytest.mark.anyio
async def test_api_agent_run_reuses_one_run_for_the_same_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        first = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        second = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        completed = await wait_for_agent_run(client, first.json()["run_id"])
        events = await client.get(
            f"/api/agent-runs/{first.json()['run_id']}/events"
        )

    async with module.engine.connect() as connection:
        run_count = await connection.scalar(
            text("SELECT count(*) FROM agent_runs WHERE alert_id = :alert_id"),
            {"alert_id": alert["alert_id"]},
        )
        review_count = await connection.scalar(
            text(
                "SELECT count(*) FROM human_review_tasks "
                "WHERE run_id = :run_id AND task_type = 'final_output'"
            ),
            {"run_id": first.json()["run_id"]},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]
    assert first.json()["status"] in {"queued", "running"}
    assert second.json()["status"] in {"queued", "running", "completed"}
    assert completed["status"] == "completed"
    assert run_count == 1
    assert review_count == 1
    assert '"type":"run_reused"' in events.text


@pytest.mark.anyio
async def test_api_agent_run_recovers_an_orphaned_queued_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]

        from agent_run_repository import create_queued_agent_run

        orphaned_run_id = str(uuid4())
        await create_queued_agent_run(
            module.engine,
            run_id=orphaned_run_id,
            alert_id=alert["alert_id"],
            card_id=alert["card_id"],
        )

        recovered = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        completed = await wait_for_agent_run(client, orphaned_run_id)
        events = await client.get(f"/api/agent-runs/{orphaned_run_id}/events")

    assert recovered.status_code == 200
    assert recovered.json()["run_id"] == orphaned_run_id
    assert completed["status"] == "completed"
    assert '"type":"run_reused"' in events.text
    assert '"type":"run_started"' in events.text


@pytest.mark.anyio
async def test_agent_run_manual_rerun_requires_audited_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        first = (await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )).json()
        await wait_for_agent_run(client, str(first["run_id"]))

        invalid = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"], "force_new": True},
        )
        rerun = await client.post(
            "/api/agent-runs",
            json={
                "alert_id": alert["alert_id"],
                "force_new": True,
                "requested_by": "pytest",
                "reason": "verify intentional rerun",
            },
        )
        completed = await wait_for_agent_run(client, rerun.json()["run_id"])
        second_rerun = await client.post(
            "/api/agent-runs",
            json={
                "alert_id": alert["alert_id"],
                "force_new": True,
                "requested_by": "pytest",
                "reason": "verify lineage depth two",
            },
        )
        await wait_for_agent_run(client, second_rerun.json()["run_id"])
        blocked_rerun = await client.post(
            "/api/agent-runs",
            json={
                "alert_id": alert["alert_id"],
                "force_new": True,
                "requested_by": "pytest",
                "reason": "must not exceed lineage depth two",
            },
        )

    assert invalid.status_code == 422
    assert rerun.status_code == 200
    assert rerun.json()["run_id"] != first["run_id"]
    assert rerun.json()["parent_run_id"] == first["run_id"]
    assert rerun.json()["trigger_type"] == "manual_rerun"
    assert rerun.json()["requested_by"] == "pytest"
    assert completed["status"] == "completed"
    assert second_rerun.status_code == 200
    assert blocked_rerun.status_code == 409
    assert blocked_rerun.json()["detail"] == "agent run lineage depth limit reached"


@pytest.mark.anyio
async def test_agent_run_event_stream_includes_events_created_after_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        created = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        events = await client.get(
            f"/api/agent-runs/{created.json()['run_id']}/events"
        )

    assert created.json()["status"] == "queued"
    assert "id: " in events.text
    assert '"type":"run_queued"' in events.text
    assert '"type":"run_completed"' in events.text


@pytest.mark.anyio
async def test_api_agent_run_replaces_expired_queued_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]

        from agent_run_repository import create_queued_agent_run

        expired_run_id = str(uuid4())
        await create_queued_agent_run(
            module.engine,
            run_id=expired_run_id,
            alert_id=alert["alert_id"],
            card_id=alert["card_id"],
        )
        async with module.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE agent_runs SET updated_at = now() - interval '1 hour' "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": expired_run_id},
            )

        replacement = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        completed = await wait_for_agent_run(client, replacement.json()["run_id"])
        expired = await client.get(f"/api/agent-runs/{expired_run_id}")

    assert replacement.status_code == 200
    assert replacement.json()["status"] == "queued"
    assert completed["status"] == "completed"
    assert replacement.json()["run_id"] != expired_run_id
    assert expired.status_code == 200
    assert expired.json()["status"] == "failed"
    assert expired.json()["error"] == "agent run lease expired"


@pytest.mark.anyio
async def test_daily_report_command_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        run = (
            await client.post(
                "/api/agent-runs",
                json={"alert_id": alert["alert_id"]},
            )
        ).json()
        run = await wait_for_agent_run(client, str(run["run_id"]))

        import agent_report_writer_adapter

        from heatgrid_ops.agent.run_models import ReportArtifactDraft

        report_calls = 0

        async def write_daily_report(_writer, request) -> ReportArtifactDraft:
            nonlocal report_calls
            report_calls += 1
            await asyncio.sleep(0.2)
            path = (
                tmp_path
                / "ops_agent"
                / "reports"
                / request.run_id
                / "daily_report.json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(orjson.dumps({"run_id": request.run_id}))
            return ReportArtifactDraft(
                kind="daily_report",
                name="daily_report.json",
                uri=f"output/ops_agent/reports/{request.run_id}/daily_report.json",
            )

        monkeypatch.setattr(
            agent_report_writer_adapter.LocalReportWriterAdapter,
            "write_daily",
            write_daily_report,
        )

        first, second = await asyncio.gather(
            client.post(
                f"/api/agent-runs/{run['run_id']}/reports/daily",
                json={"requested_by": "pytest-a"},
            ),
            client.post(
                f"/api/agent-runs/{run['run_id']}/reports/daily",
                json={"requested_by": "pytest-b"},
            ),
        )

    async with module.engine.connect() as connection:
        artifact_count = await connection.scalar(
            text(
                "SELECT count(*) FROM agent_run_artifacts "
                "WHERE run_id = :run_id AND name = 'daily_report.json'"
            ),
            {"run_id": run["run_id"]},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert report_calls == 1
    assert artifact_count == 1
    assert (
        tmp_path
        / "ops_agent"
        / "reports"
        / run["run_id"]
        / "daily_report.json"
    ).exists()


@pytest.mark.anyio
async def test_quality_review_creates_targeted_v2_child_with_stage_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with module.lifespan(module.app):
        async with AsyncClient(
            transport=ASGITransport(app=module.app),
            base_url="http://test",
        ) as client:
            await client.post("/api/alerts/enqueue")
            alert = (
                await client.get("/api/alerts", params={"status": "open"})
            ).json()[0]
            created = await client.post(
                "/api/agent-runs",
                json={"alert_id": alert["alert_id"]},
            )
            parent = await wait_for_agent_run(client, created.json()["run_id"])
            review = await client.post(
                f"/api/agent-runs/{parent['run_id']}/reviews",
                json={
                    "expected_review_version": 0,
                    "idempotency_key": f"quality-rerun-{uuid4()}",
                    "decision": "keep_human_review",
                    "reviewer": "pytest",
                    "reason": "fault analysis requires reassessment",
                    "reason_category": "fault_analysis_insufficient",
                    "disposition": "urgent_review",
                },
            )

            async with module.engine.connect() as connection:
                rerun = (
                    await connection.execute(
                        text(
                            "SELECT request.child_run_id, request.status, "
                            "request.target_stage, child.parent_run_id, "
                            "child.root_run_id, child.lineage_depth, "
                            "task.task_key, task.operation_key "
                            "FROM agent_rerun_requests request "
                            "JOIN agent_runs child ON child.run_id = request.child_run_id "
                            "JOIN agent_run_tasks task ON task.run_id = child.run_id "
                            "WHERE request.source_review_id = :review_id"
                        ),
                        {"review_id": review.json()["review_id"]},
                    )
                ).mappings().one()

            child = await wait_for_agent_run(client, str(rerun["child_run_id"]))
            parent_review_snapshot = await wait_for_review_snapshot(
                client,
                parent["run_id"],
            )
            child_review_snapshot = await wait_for_review_snapshot(
                client,
                child["run_id"],
            )

    async with module.engine.connect() as connection:
        parent_stages = (
            await connection.execute(
                text(
                    "SELECT stage_name, execution_status, quality_status, score "
                    "FROM agent_stage_snapshots WHERE run_id = :run_id "
                    "ORDER BY created_at, stage_name"
                ),
                {"run_id": parent["run_id"]},
            )
        ).mappings().all()
        child_stages = (
            await connection.execute(
                text(
                    "SELECT stage_name, execution_status, reused_from_snapshot_id "
                    "FROM agent_stage_snapshots WHERE run_id = :run_id"
                ),
                {"run_id": child["run_id"]},
            )
        ).mappings().all()

    parent_by_name = {str(row["stage_name"]): row for row in parent_stages}
    child_by_name = {str(row["stage_name"]): row for row in child_stages}
    assert review.status_code == 200
    assert rerun["status"] == "scheduled"
    assert rerun["target_stage"] == "fault_analysis"
    assert str(rerun["parent_run_id"]) == parent["run_id"]
    assert str(rerun["root_run_id"]) == parent["run_id"]
    assert rerun["lineage_depth"] == 1
    assert rerun["task_key"] == "agent_graph:v2"
    assert rerun["operation_key"] == f"agent-graph:{child['run_id']}"
    assert child["status"] == "completed"
    assert parent_review_snapshot["status"] == "available"
    assert child_review_snapshot["status"] == "available"
    assert len(parent_stages) == 9
    assert parent_by_name["rag_retrieval"]["execution_status"] == "passed"
    assert parent_by_name["rag_retrieval"]["quality_status"] == "skipped"
    assert parent_by_name["rag_retrieval"]["score"] is None
    assert child_by_name["ml_validation"]["execution_status"] == "reused"
    assert child_by_name["ml_validation"]["reused_from_snapshot_id"] is not None


@pytest.mark.anyio
async def test_startup_reclaim_dispatches_v1_and_v2_graph_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)
    run_repository = importlib.import_module("agent_run_repository")
    v1_run_id = str(uuid4())
    v2_run_id = str(uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]

    await run_repository.create_queued_agent_run(
        module.engine,
        run_id=v1_run_id,
        alert_id=alert["alert_id"],
        card_id=alert["card_id"],
    )
    await run_repository.create_queued_agent_run(
        module.engine,
        run_id=v2_run_id,
        alert_id=alert["alert_id"],
        card_id=alert["card_id"],
    )
    async with module.engine.begin() as connection:
        for run_id, task_key in (
            (v1_run_id, "agent_graph:v1"),
            (v2_run_id, "agent_graph:v2"),
        ):
            await connection.execute(
                text(
                    "INSERT INTO agent_run_tasks ("
                    "task_id, run_id, task_key, operation_key, checkpoint_thread_id, "
                    "status, input_snapshot) VALUES ("
                    ":task_id, :run_id, :task_key, :operation_key, "
                    ":checkpoint_thread_id, "
                    "'queued', CAST(:input_snapshot AS jsonb))"
                ),
                {
                    "task_id": str(uuid4()),
                    "run_id": run_id,
                    "task_key": task_key,
                    "operation_key": f"agent-graph:{run_id}",
                    "checkpoint_thread_id": run_id,
                    "input_snapshot": orjson.dumps(
                        {
                            "run_id": run_id,
                            "alert_id": alert["alert_id"],
                            "card_id": alert["card_id"],
                        }
                    ).decode("utf-8"),
                },
            )

    async with module.lifespan(module.app):
        async with AsyncClient(
            transport=ASGITransport(app=module.app),
            base_url="http://test",
        ) as client:
            v1_run = await wait_for_agent_run(client, v1_run_id)
            v2_run = await wait_for_agent_run(client, v2_run_id)
            await wait_for_review_snapshot(client, v1_run_id)
            await wait_for_review_snapshot(client, v2_run_id)

    async with module.engine.connect() as connection:
        task_rows = (
            await connection.execute(
                text(
                    "SELECT run_id, task_key, status FROM agent_run_tasks "
                    "WHERE run_id IN (:v1_run_id, :v2_run_id) ORDER BY task_key"
                ),
                {"v1_run_id": v1_run_id, "v2_run_id": v2_run_id},
            )
        ).mappings().all()
        v1_stage_count = await connection.scalar(
            text("SELECT count(*) FROM agent_stage_snapshots WHERE run_id = :run_id"),
            {"run_id": v1_run_id},
        )
        v2_stage_count = await connection.scalar(
            text("SELECT count(*) FROM agent_stage_snapshots WHERE run_id = :run_id"),
            {"run_id": v2_run_id},
        )

    assert v1_run["status"] == "completed"
    assert v2_run["status"] == "completed"
    assert [(row["task_key"], row["status"]) for row in task_rows] == [
        ("agent_graph:v1", "completed"),
        ("agent_graph:v2", "completed"),
    ]
    assert v1_stage_count == 0
    assert v2_stage_count == 9


@pytest.mark.anyio
async def test_daily_report_versions_follow_effective_output_corrections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    import agent_report_writer_adapter

    from heatgrid_ops.agent.run_models import ReportArtifactDraft

    report_summaries: list[str] = []

    async def write_daily_report(_writer, request) -> ReportArtifactDraft:
        report_summaries.append(request.ops_output.summary)
        return ReportArtifactDraft(
            kind="daily_report",
            name="daily_report.json",
            uri=(
                f"output/ops_agent/reports/{request.run_id}/"
                f"{request.source_output_hash}/daily_report.json"
            ),
        )

    monkeypatch.setattr(
        agent_report_writer_adapter.LocalReportWriterAdapter,
        "write_daily",
        write_daily_report,
    )
    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        created = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        run = await wait_for_agent_run(client, created.json()["run_id"])
        first_report = await client.post(
            f"/api/agent-runs/{run['run_id']}/reports/daily",
            json={"requested_by": "pytest"},
        )
        correction = await client.post(
            f"/api/agent-runs/{run['run_id']}/reviews",
            json={
                "expected_review_version": 0,
                "idempotency_key": f"report-correction-{uuid4()}",
                "decision": "correct",
                "reviewer": "pytest",
                "reason": "clarify the operator report",
                "disposition": "inspection_recommended",
                "correction": {
                    "summary": "operator corrected summary",
                    "action_plan": "inspect the heat exchanger",
                    "caution": "isolate the circuit before inspection",
                },
            },
        )
        second_report = await client.post(
            f"/api/agent-runs/{run['run_id']}/reports/daily",
            json={"requested_by": "pytest"},
        )

    async with module.engine.connect() as connection:
        artifacts = (
            await connection.execute(
                text(
                    "SELECT source_output_hash, source_review_id, contract_version "
                    "FROM agent_run_artifacts WHERE run_id = :run_id "
                    "AND name = 'daily_report.json' ORDER BY created_at"
                ),
                {"run_id": run["run_id"]},
            )
        ).mappings().all()
        action_count = await connection.scalar(
            text(
                "SELECT count(*) FROM agent_run_actions WHERE run_id = :run_id "
                "AND action_name LIKE 'daily_report:%'"
            ),
            {"run_id": run["run_id"]},
        )

    assert first_report.status_code == 200
    assert correction.status_code == 200
    assert second_report.status_code == 200
    assert report_summaries[-1] == "operator corrected summary"
    assert len(artifacts) == 2
    assert artifacts[0]["source_output_hash"] != artifacts[1]["source_output_hash"]
    assert artifacts[0]["source_review_id"] is None
    assert str(artifacts[1]["source_review_id"]) == correction.json()["review_id"]
    assert {row["contract_version"] for row in artifacts} == {"artifact.output-v2"}
    assert action_count == 2


@pytest.mark.anyio
async def test_api_dashboard_contract_runs_from_alert_feed_to_agent_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        enqueue = await client.post("/api/alerts/enqueue")
        alert_feed = await client.get("/api/alerts", params={"status": "open"})
        alert = alert_feed.json()[0]
        alert_detail = await client.get(f"/api/alerts/{alert['alert_id']}")
        alert_events = await client.get("/api/alerts/events")
        created = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        run_id = created.json()["run_id"]
        run_events = await client.get(f"/api/agent-runs/{run_id}/events")
        artifacts = await client.get(f"/api/agent-runs/{run_id}/artifacts")
        resolved = await client.post(
            f"/api/alerts/{alert['alert_id']}/resolve",
            json={"acked_by": "dashboard-test"},
        )

    assert enqueue.status_code == 200
    assert alert_feed.status_code == 200
    assert alert["status"] == "open"
    assert alert_detail.status_code == 200
    assert alert_detail.json()["alert_id"] == alert["alert_id"]
    assert alert_events.status_code == 200
    assert '"type":"alerts_snapshot"' in alert_events.text
    assert created.status_code == 200
    assert created.json()["alert_id"] == alert["alert_id"]
    assert created.json()["status"] == "queued"
    assert run_events.status_code == 200
    assert '"type":"run_completed"' in run_events.text
    assert '"type":"report_failed"' in run_events.text
    assert artifacts.status_code == 200
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


@pytest.mark.anyio
async def test_api_agent_run_rejects_missing_alert_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/agent-runs",
            json={"alert_id": "00000000-0000-0000-0000-000000000000"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "alert_id를 찾을 수 없습니다."
