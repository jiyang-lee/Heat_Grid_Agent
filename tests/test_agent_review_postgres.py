from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sys
from typing import Final

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from heatgrid_ops.agent.review_models import (
    AgentRunReviewSnapshotV1,
    ReviewBudgetLineage,
    ReviewCheckpointLineage,
    ReviewDiagnosticSnapshot,
    ReviewFinalResultSnapshot,
    ReviewOpsAgentOutput,
    ReviewSourceCardSnapshot,
)
ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))
DATABASE_URL: Final = os.getenv("HEATGRID_V3_REVIEW_TEST_DATABASE_URL")

RUN_AVAILABLE: Final = "00000000-0000-0000-0000-000000000103"
RUN_HARD_STOP: Final = "00000000-0000-0000-0000-000000000101"
RUN_INTERRUPTED: Final = "00000000-0000-0000-0000-000000000102"
RUN_LEGACY: Final = "00000000-0000-0000-0000-000000000104"
RUN_UNAVAILABLE: Final = "00000000-0000-0000-0000-000000000105"
ALERT_ID: Final = "00000000-0000-0000-0000-000000000201"
CARD_ID: Final = "00000000-0000-0000-0000-000000000301"
DECISION_ID: Final = "00000000-0000-0000-0000-000000000401"
WINDOW_ID: Final = "00000000-0000-0000-0000-000000000501"
PARENT_TASK_ID: Final = "00000000-0000-0000-0000-000000000601"
PARENT_LEDGER_ID: Final = "00000000-0000-0000-0000-000000000701"
DIAGNOSTIC_LEDGER_ID: Final = "00000000-0000-0000-0000-000000000702"


pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="HEATGRID_V3_REVIEW_TEST_DATABASE_URL is required",
)


@pytest.mark.anyio
async def test_review_repository_and_api_against_postgres() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_routes import (
        make_agent_review_router,
    )
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_snapshot_adapter import (
        PostgresReviewSnapshotAdapter,
    )

    engine = create_async_engine(str(DATABASE_URL))
    try:
        await _cleanup(engine)
        await _seed(engine)
        adapter = PostgresReviewSnapshotAdapter(engine)
        inserted = await adapter.capture(_snapshot(RUN_AVAILABLE))
        existing = await adapter.capture(_snapshot(RUN_AVAILABLE))
        conflict = await adapter.capture(
            _snapshot(RUN_AVAILABLE).model_copy(
                update={"handling_reason": "different immutable content"}
            )
        )
        await adapter.mark_unavailable(RUN_UNAVAILABLE, "capture dependency failed")
        await adapter.mark_pending(RUN_INTERRUPTED)
        await adapter.mark_pending(RUN_INTERRUPTED)

        app = FastAPI()
        app.include_router(make_agent_review_router(engine))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first_page = await client.get("/api/agent-runs", params={"limit": 1})
            cursor = first_page.json()["next_cursor"]
            second_page = await client.get(
                "/api/agent-runs", params={"limit": 1, "cursor": cursor}
            )
            all_runs = await client.get("/api/agent-runs")
            available = await client.get(f"/api/agent-runs/{RUN_AVAILABLE}/review")
            legacy = await client.get(f"/api/agent-runs/{RUN_LEGACY}/review")
            unavailable = await client.get(
                f"/api/agent-runs/{RUN_UNAVAILABLE}/review"
            )
            interrupted = await client.get(
                f"/api/agent-runs/{RUN_INTERRUPTED}/review"
            )
            hard_stop = await client.get(f"/api/agent-runs/{RUN_HARD_STOP}/review")
            missing = await client.get(
                "/api/agent-runs/00000000-0000-0000-0000-000000000999/review"
            )
            malformed = await client.get(
                "/api/agent-runs", params={"cursor": "broken!"}
            )
            filtered = await client.get(
                "/api/agent-runs",
                params={
                    "status": "completed",
                    "operator_review_status": "approved",
                    "worker_status": "completed",
                    "priority": "high",
                    "created_from": "2026-07-13T00:00:00Z",
                    "created_to": "2026-07-15T00:00:00Z",
                },
            )

        assert inserted.status == "inserted"
        assert existing.status == "existing"
        assert conflict.status == "conflict"
        assert first_page.status_code == 200
        assert second_page.status_code == 200
        assert first_page.json()["items"][0]["run_id"] == RUN_UNAVAILABLE
        assert second_page.json()["items"][0]["run_id"] == RUN_LEGACY
        worker_statuses = {
            item["run_id"]: item["worker_status"]
            for item in all_runs.json()["items"]
        }
        assert worker_statuses == {
            RUN_UNAVAILABLE: "running",
            RUN_LEGACY: "timeout",
            RUN_AVAILABLE: "completed",
            RUN_INTERRUPTED: "not_triggered",
            RUN_HARD_STOP: "not_triggered",
        }
        assert available.json()["status"] == "available"
        assert available.json()["snapshot"]["handling_reason"] == "operator review"
        assert legacy.json()["status"] == "legacy_unavailable"
        assert unavailable.json()["status"] == "unavailable"
        assert interrupted.json()["status"] == "unavailable"
        assert (
            interrupted.json()["unavailable_reason"]
            == "review_snapshot_missing_after_terminal_run"
        )
        assert hard_stop.json()["status"] == "unavailable"
        assert (
            hard_stop.json()["unavailable_reason"]
            == "review_snapshot_missing_after_terminal_run"
        )
        assert missing.status_code == 404
        assert malformed.status_code == 422
        assert [item["run_id"] for item in filtered.json()["items"]] == [
            RUN_AVAILABLE
        ]

        async with engine.connect() as connection:
            conflict_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM agent_run_events "
                    "WHERE run_id = :run_id AND event_type = 'review_snapshot_conflict'"
                ),
                {"run_id": RUN_AVAILABLE},
            )
            pending_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM agent_run_events "
                    "WHERE run_id = :run_id "
                    "AND event_type = 'review_snapshot_pending'"
                ),
                {"run_id": RUN_INTERRUPTED},
            )
        assert conflict_count == 1
        assert pending_count == 1
    finally:
        await _cleanup(engine)
        await engine.dispose()


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO windows (window_id, manufacturer_id, substation_id, "
                "window_start, window_end) VALUES ("
                ":window_id, 'maker', 31, now() - interval '1 hour', now())"
            ),
            {"window_id": WINDOW_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO priority_decisions (priority_decision_id, window_id, "
                "priority_level) VALUES (:decision_id, :window_id, 'high')"
            ),
            {"decision_id": DECISION_ID, "window_id": WINDOW_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO priority_cards (card_id, priority_decision_id, "
                "review_required) VALUES (:card_id, :decision_id, true)"
            ),
            {"card_id": CARD_ID, "decision_id": DECISION_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO ops_alert_queue ("
                "alert_id, card_id, priority_level, enqueue_reason"
                ") VALUES (:alert_id, :card_id, 'high', 'review test')"
            ),
            {"alert_id": ALERT_ID, "card_id": CARD_ID},
        )
        for run_id in (
            RUN_HARD_STOP,
            RUN_INTERRUPTED,
            RUN_AVAILABLE,
            RUN_LEGACY,
            RUN_UNAVAILABLE,
        ):
            await connection.execute(
                text(
                    "INSERT INTO agent_runs ("
                    "run_id, alert_id, card_id, status, review_snapshot_expected, "
                    "created_at, updated_at"
                    ") VALUES ("
                    ":run_id, :alert_id, :card_id, :status, :expected, "
                    ":created_at, :created_at"
                    ")"
                ),
                {
                    "run_id": run_id,
                    "alert_id": ALERT_ID,
                    "card_id": CARD_ID,
                    "status": "running" if run_id == RUN_UNAVAILABLE else "completed",
                    "expected": None if run_id == RUN_LEGACY else True,
                    "created_at": datetime(2026, 7, 14, tzinfo=UTC),
                },
            )
        await connection.execute(
            text(
                "INSERT INTO agent_run_reviews ("
                "run_id, review_version, idempotency_key, request_hash, decision, "
                "reviewer, reason) VALUES ("
                ":run_id, 1, 'review-test', :request_hash, 'approve', "
                "'operator', 'verified')"
            ),
            {"run_id": RUN_AVAILABLE, "request_hash": "b" * 64},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_run_events ("
                "run_id, event_type, message, payload, operation_key"
                ") VALUES ("
                "CAST(:run_id AS uuid), 'diagnostic_worker_completed', "
                "'read-only diagnostic worker completed', "
                "CAST('{\"status\":\"timeout\"}' AS jsonb), "
                "'review-test-diagnostic-event')"
            ),
            {"run_id": RUN_LEGACY},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_run_tasks ("
                "task_id, run_id, task_key, operation_key, status, checkpoint_thread_id"
                ") VALUES ("
                ":task_id, CAST(:run_id AS uuid), 'agent_graph:v1', "
                "'agent-graph:' || :run_id, 'running', :run_id)"
            ),
            {"task_id": PARENT_TASK_ID, "run_id": RUN_UNAVAILABLE},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_budget_ledger ("
                "ledger_id, run_id, task_id, operation_key, token_limit, retry_limit"
                ") VALUES ("
                ":ledger_id, CAST(:run_id AS uuid), :task_id, "
                "'agent-budget:' || :run_id, 60000, 3)"
            ),
            {
                "ledger_id": PARENT_LEDGER_ID,
                "run_id": RUN_UNAVAILABLE,
                "task_id": PARENT_TASK_ID,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO agent_budget_ledger ("
                "ledger_id, run_id, task_id, parent_ledger_id, operation_key, "
                "token_limit, retry_limit) VALUES ("
                ":ledger_id, CAST(:run_id AS uuid), :task_id, :parent_ledger_id, "
                "'diagnostic-budget:' || :run_id || ':fault_diagnosis:v1', 4000, 1)"
            ),
            {
                "ledger_id": DIAGNOSTIC_LEDGER_ID,
                "run_id": RUN_UNAVAILABLE,
                "task_id": PARENT_TASK_ID,
                "parent_ledger_id": PARENT_LEDGER_ID,
            },
        )


async def _cleanup(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM windows WHERE window_id = :window_id"),
            {"window_id": WINDOW_ID},
        )


def _snapshot(run_id: str) -> AgentRunReviewSnapshotV1:
    return AgentRunReviewSnapshotV1(
        run_id=run_id,
        result=ReviewFinalResultSnapshot(
            status="completed",
            agent_mode="fallback",
            ops_output=ReviewOpsAgentOutput(
                summary="stable",
                action_plan="monitor",
                caution="review",
            ),
        ),
        loop_count=1,
        handling_reason="operator review",
        diagnostic=ReviewDiagnosticSnapshot(status="completed", attempts=1),
        source_card=ReviewSourceCardSnapshot(
            card_id=CARD_ID,
            substation_id=31,
            manufacturer_id="maker",
            priority_level="high",
            status="open",
            review_required=True,
            reason="review test",
        ),
        budget=ReviewBudgetLineage(
            parent_token_limit=60_000,
            parent_tokens_used=100,
            diagnostic_token_limit=4_000,
            diagnostic_tokens_used=0,
        ),
        checkpoint=ReviewCheckpointLineage(
            thread_id=run_id,
            namespace="",
            checkpoint_id="checkpoint",
        ),
    )
