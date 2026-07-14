from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from httpx import ASGITransport, AsyncClient
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
    spec = importlib.util.spec_from_file_location(
        "agent_automation_server", SERVER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def reset_automation_tables(module: ModuleType) -> None:
    async with module.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE training_feedback, human_review_tasks, evidence_candidates CASCADE"
            )
        )
        await connection.execute(
            text(
                "TRUNCATE TABLE model_deployments, model_candidates, retrain_jobs CASCADE"
            )
        )
        await connection.execute(text("TRUNCATE TABLE automation_policy"))
        await connection.execute(
            text(
                "INSERT INTO automation_policy (policy_id, mode) "
                "VALUES ('default', 'human_only')"
            )
        )
        await connection.execute(text("TRUNCATE TABLE agent_loop_iterations"))
        await connection.execute(text("TRUNCATE TABLE agent_runs CASCADE"))
        await connection.execute(text("TRUNCATE TABLE ops_alert_queue CASCADE"))
    await module.ensure_alert_queue(module.engine)
    await module.ensure_agent_run_tables(module.engine)
    await module.ensure_agent_loop_iteration_table(module.engine)


async def wait_for_agent_run(client: AsyncClient, run_id: str) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(f"/api/agent-runs/{run_id}")
        payload = response.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        await asyncio.sleep(0.025)
    raise AssertionError(f"agent run {run_id} did not finish")


@pytest.mark.anyio
async def test_review_feedback_evidence_and_policy_api_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await module.ensure_agent_run_tables(module.engine)
    await module.ensure_review_tables(module.engine)
    await module.ensure_retrain_tables(module.engine)
    await reset_automation_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app), base_url="http://test"
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        run = (
            await client.post("/api/agent-runs", json={"alert_id": alert["alert_id"]})
        ).json()
        run = await wait_for_agent_run(client, str(run["run_id"]))

        tasks = await client.get("/api/review-tasks", params={"status": "pending"})
        final_task = next(
            item for item in tasks.json() if item["task_type"] == "final_output"
        )
        reviewed = await client.post(
            f"/api/review-tasks/{final_task['task_id']}/submit",
            json={
                "decision": "correct",
                "reviewer": "pytest",
                "reason": "라벨 교정",
                "corrected_label": "pre_fault",
                "corrected_output": {
                    "summary": "사람이 교정한 상황 요약",
                    "action_plan": "현장 점검을 우선 수행합니다.",
                    "caution": "교정 결과도 최종 운영 판단과 함께 확인합니다.",
                },
            },
        )
        feedback = await client.get("/api/training-feedback")
        updated_run = await client.get(f"/api/agent-runs/{run['run_id']}")

        candidate = await client.post(
            "/api/evidence-candidates",
            json={
                "title": "검수된 운영 사례",
                "content": "차압 저하 시 밸브와 스트레이너 상태를 함께 점검한 운영 사례입니다.",
                "source_type": "manual",
                "risk_level": "low",
                "trust_score": 0.9,
                "requested_by": "pytest",
            },
        )
        candidate_id = candidate.json()["candidate_id"]
        candidate_review = await client.post(
            f"/api/evidence-candidates/{candidate_id}/review",
            json={"decision": "approve", "reviewer": "pytest", "reason": "원문 확인"},
        )

        policy = await client.patch(
            "/api/automation-policy",
            json={
                "mode": "assisted",
                "auto_transition_enabled": True,
                "updated_by": "pytest",
            },
        )

    assert reviewed.status_code == 200
    assert reviewed.json()["task"]["status"] == "corrected"
    assert reviewed.json()["feedback"]["corrected_label"] == "pre_fault"
    assert feedback.json()[0]["task_id"] == final_task["task_id"]
    assert updated_run.json()["review_status"] == "corrected"
    assert updated_run.json()["ops_output"]["summary"] == "사람이 교정한 상황 요약"
    assert candidate.status_code == 200
    assert candidate_review.status_code == 200
    assert candidate_review.json()["status"] in {"approved", "ingest_failed"}
    assert policy.status_code == 200
    assert policy.json()["mode"] == "assisted"
    assert policy.json()["auto_transition_enabled"] is True


@pytest.mark.anyio
async def test_retrain_job_requires_explicit_approval_or_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await module.ensure_agent_run_tables(module.engine)
    await module.ensure_review_tables(module.engine)
    await module.ensure_retrain_tables(module.engine)

    async with AsyncClient(
        transport=ASGITransport(app=module.app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/retrain-jobs",
            json={
                "requested_by": "pytest",
                "reason": "승인 계약 검증",
                "feedback_ids": [],
                "auto_start_when_approved": False,
            },
        )
        job_id = created.json()["job_id"]
        rejected = await client.post(
            f"/api/retrain-jobs/{job_id}/reject",
            json={"reviewer": "pytest", "reason": "테스트 반려"},
        )

    assert created.status_code == 200
    assert created.json()["status"] == "pending_approval"
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


@pytest.mark.anyio
async def test_guarded_auto_starts_one_retrain_and_blocks_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEATGRID_RETRAIN_AUTO_EXECUTE_ENABLED", "1")
    module = load_server(monkeypatch)
    await module.ensure_agent_run_tables(module.engine)
    await module.ensure_review_tables(module.engine)
    await module.ensure_retrain_tables(module.engine)
    await reset_automation_tables(module)

    automation_routes = importlib.import_module("automation_routes")

    async def skip_training(_engine, _job_id: str) -> None:
        return None

    monkeypatch.setattr(automation_routes, "execute_retrain_job", skip_training)

    async with AsyncClient(
        transport=ASGITransport(app=module.app), base_url="http://test"
    ) as client:
        policy = await client.patch(
            "/api/automation-policy",
            json={
                "mode": "guarded_auto",
                "minimum_review_count": 1,
                "minimum_approval_rate": 0,
                "minimum_confidence": 0,
                "minimum_source_trust": 0,
                "maximum_drift_score": 1,
                "updated_by": "pytest",
            },
        )
        await client.post("/api/alerts/enqueue")
        async with module.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ops_alert_queue ("
                    "alert_id, card_id, evaluation_run_id, manufacturer_id, "
                    "substation_id, priority_rank, freshness_status, priority_level, "
                    "priority_score, enqueue_reason"
                    ") "
                    "SELECT md5('pytest-retrain|' || result.evaluation_result_id::text)::uuid, "
                    "result.source_card_id, result.evaluation_run_id, result.manufacturer_id, "
                    "result.substation_id, result.priority_rank, result.freshness_status, "
                    "'high', result.priority_score, 'pytest guarded-auto retrain' "
                    "FROM priority_evaluation_results result "
                    "JOIN priority_evaluation_runs evaluation "
                    "ON evaluation.evaluation_run_id = result.evaluation_run_id "
                    "WHERE evaluation.is_active "
                    "AND result.freshness_status = 'fresh' "
                    "AND result.rank_included "
                    "AND result.source_card_id IS NOT NULL "
                    "AND NOT EXISTS ("
                    "SELECT 1 FROM ops_alert_queue queued "
                    "WHERE queued.evaluation_run_id = result.evaluation_run_id "
                    "AND queued.manufacturer_id = result.manufacturer_id "
                    "AND queued.substation_id = result.substation_id"
                    ") "
                    "ORDER BY result.priority_rank NULLS LAST "
                    "LIMIT 1 ON CONFLICT DO NOTHING"
                )
            )
        alerts = (await client.get("/api/alerts", params={"status": "open"})).json()
        assert len(alerts) >= 2

        automatic_job_ids: list[str | None] = []
        for alert in alerts[:2]:
            run = (
                await client.post(
                    "/api/agent-runs",
                    json={"alert_id": alert["alert_id"]},
                )
            ).json()
            run = await wait_for_agent_run(client, str(run["run_id"]))
            tasks = (
                await client.get(
                    "/api/review-tasks",
                    params={"status": "pending", "task_type": "final_output"},
                )
            ).json()
            final_task = next(item for item in tasks if item["run_id"] == run["run_id"])
            reviewed = await client.post(
                f"/api/review-tasks/{final_task['task_id']}/submit",
                json={
                    "decision": "correct",
                    "reviewer": "pytest",
                    "reason": "자동 재학습 경로 검증",
                    "corrected_label": "pre_fault",
                },
            )
            automatic_job_ids.append(reviewed.json()["automatic_retrain_job_id"])

        jobs = await client.get("/api/retrain-jobs")
        restored_policy = await client.patch(
            "/api/automation-policy",
            json={
                "mode": "human_only",
                "auto_transition_enabled": False,
                "minimum_review_count": 100,
                "minimum_approval_rate": 0.95,
                "minimum_confidence": 0.9,
                "minimum_source_trust": 0.85,
                "maximum_drift_score": 0.1,
                "updated_by": "pytest-cleanup",
            },
        )

    assert policy.status_code == 200
    assert automatic_job_ids[0] is not None
    assert automatic_job_ids[1] is None
    assert len(jobs.json()) == 1
    assert jobs.json()[0]["status"] == "approved"
    assert restored_policy.json()["mode"] == "human_only"


@pytest.mark.anyio
async def test_legacy_review_submission_records_v3_reject_state_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    async with module.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE human_review_tasks, evidence_candidates CASCADE"
            )
        )
        await connection.execute(text("TRUNCATE TABLE automation_policy"))
        await connection.execute(
            text(
                "INSERT INTO automation_policy (policy_id, mode) "
                "VALUES ('default', 'human_only')"
            )
        )
        await connection.execute(text("TRUNCATE TABLE agent_loop_iterations"))
        await connection.execute(text("TRUNCATE TABLE agent_runs CASCADE"))
        await connection.execute(text("TRUNCATE TABLE ops_alert_queue CASCADE"))
    await module.ensure_alert_queue(module.engine)
    await module.ensure_agent_run_tables(module.engine)
    await module.ensure_agent_loop_iteration_table(module.engine)

    async with AsyncClient(
        transport=ASGITransport(app=module.app), base_url="http://test"
    ) as client:
        await client.post("/api/alerts/enqueue")
        alert = (await client.get("/api/alerts", params={"status": "open"})).json()[0]
        created = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        run = await wait_for_agent_run(client, str(created.json()["run_id"]))
        tasks = await client.get(
            "/api/review-tasks",
            params={"status": "pending", "task_type": "final_output"},
        )
        task = next(item for item in tasks.json() if item["run_id"] == run["run_id"])
        payload = {
            "decision": "reject",
            "reviewer": "pytest",
            "reason": "legacy reject mapping",
        }
        submitted = await client.post(
            f"/api/review-tasks/{task['task_id']}/submit",
            json=payload,
        )
        duplicate = await client.post(
            f"/api/review-tasks/{task['task_id']}/submit",
            json=payload,
        )
        detail = await client.get(f"/api/agent-runs/{run['run_id']}")
        listed = await client.get(
            "/api/agent-runs",
            params={"limit": 100, "status": "completed"},
        )

    async with module.engine.connect() as connection:
        review_count = await connection.scalar(
            text(
                "SELECT count(*) FROM agent_run_reviews "
                "WHERE run_id = :run_id"
            ),
            {"run_id": run["run_id"]},
        )

    listed_run = next(
        item for item in listed.json()["items"] if item["run_id"] == run["run_id"]
    )
    assert submitted.status_code == 200
    assert duplicate.status_code == 409
    assert detail.json()["review_status"] == "rejected"
    assert listed_run["operator_review_status"] == "keep_human_review"
    assert review_count == 1
