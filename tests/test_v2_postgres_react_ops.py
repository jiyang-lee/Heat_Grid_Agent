import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from httpx import ASGITransport, AsyncClient
import orjson
import pytest
from sqlalchemy import text

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
SERVER_PATH: Final = BACKEND_DIR / "server.py"


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
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_artifacts"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_events"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_runs"))
        await connection.execute(text("DROP TABLE IF EXISTS ops_alert_queue"))


@pytest.mark.anyio
async def test_v2_postgres_tools_return_ops_and_external_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    card_ids = await module.list_card_ids(module.engine)
    source_input = await module.input_for_card(card_ids[0])
    external_context = module.external_context_for(card_ids[0], source_input)
    tools = {item.name: item for item in module.tools_for(source_input, external_context)}

    evidence = orjson.loads(tools["get_ops_evidence"].invoke({"card_id": card_ids[0]}))
    context = orjson.loads(tools["get_external_context"].invoke({"card_id": card_ids[0]}))

    assert set(tools) == {"get_ops_evidence", "get_external_context"}
    assert "site" in context
    assert "weather" in context
    assert "retrieval" in context
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
    assert created.json()["status"] == "completed"
    assert created.json()["alert_id"] == alert["alert_id"]
    assert created.json()["card_id"] == alert["card_id"]
    assert created.json()["evaluation_run_id"] == alert["evaluation_run_id"]
    assert created.json()["substation_id"] == alert["substation_id"]
    assert created.json()["agent_mode"] == "fallback"
    assert created.json()["ops_output"]["summary"]
    assert created.json()["loop_summary"]["iterations"] >= 1
    assert created.json()["loop_summary"]["model_verification"]["status"] in {
        "verified",
        "partial",
        "unavailable",
        "error",
    }
    assert created.json()["loop_summary"]["model_verification"]["evaluation_run_id"] == alert["evaluation_run_id"]
    assert created.json()["loop_summary"]["model_verification"]["substation_id"] == alert["substation_id"]
    assert created.json()["review_status"] == "pending"
    assert created.json()["review_task_id"]
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    assert artifacts.status_code == 200
    assert artifacts.json() == []
    assert iterations.status_code == 200
    assert iterations.json()
    assert events.status_code == 200
    assert '"type":"run_started"' in events.text
    assert '"type":"status_changed"' in events.text
    assert '"type":"llm_decision"' in events.text
    assert '"type":"tool_started"' in events.text
    assert '"type":"tool_completed"' in events.text
    assert '"type":"final_output"' in events.text
    assert '"type":"run_completed"' in events.text
    assert '"type":"report_failed"' in events.text
    assert event_types[:9] == [
        "run_started",
        "status_changed",
        "status_changed",
        "llm_decision",
        "tool_started",
        "tool_completed",
        "llm_decision",
        "tool_started",
        "tool_completed",
    ]
    assert "model_verification" in event_types
    assert "loop_decision" in event_types
    assert "review_requested" in event_types
    assert event_types.index("final_output") < event_types.index("review_requested")
    assert event_types.index("review_requested") < event_types.index("run_completed")
    assert event_types[-1] == "report_failed"


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
    assert created.json()["status"] == "completed"
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
