from __future__ import annotations

import importlib
from asyncio import SelectorEventLoop
from pathlib import Path
import sys
from typing import Final
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from v3_runner_postgres_harness import RunnerPostgresHarness


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(BACKEND_DIR))
agent_runner = importlib.import_module("agent_runner")
from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (  # noqa: E402
    AgentRunReviewSnapshotResponse,
)
from simulator.versions.v2_postgres_react_ops.backend.agent_review_snapshot_repository import (  # noqa: E402
    get_review_snapshot,
)


@pytest.fixture
def anyio_backend():
    return ("asyncio", {"loop_factory": SelectorEventLoop})


@pytest.mark.anyio
async def test_production_runner_persists_review_snapshot_after_task_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = await RunnerPostgresHarness.create()

    async def execute_graph(*_args, **kwargs):
        request = kwargs.get("request")
        if request is None:
            request = _args[1]
        return await fixture.complete_graph(
            request,
            include_capture=request.run_id != fixture.legacy_run_id,
        )

    monkeypatch.setattr(
        agent_runner,
        "execute_agent_graph_with_capture",
        execute_graph,
    )
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)
    try:
        success = await agent_runner.run_agent_graph(
            fixture.engine,
            fixture.request(fixture.success_run_id),
            runtime=AsyncMock(),
        )
        before_review = await _task_state(fixture.engine, fixture.success_run_id)
        review = await _review(fixture.engine, fixture.success_run_id)

        reclaimed = await agent_runner.run_reserved_agent_graph(
            fixture.engine,
            fixture.request(fixture.success_run_id),
            runtime=AsyncMock(),
        )
        await agent_runner._capture_completed_review_snapshot(
            fixture.engine,
            fixture.capture_source(fixture.success_run_id).model_copy(
                update={"handling_reason": "conflicting immutable content"}
            ),
        )
        snapshot_state = await _snapshot_state(
            fixture.engine,
            fixture.success_run_id,
        )
        review_after_conflict = await _review(
            fixture.engine,
            fixture.success_run_id,
        )

        monkeypatch.setattr(
            agent_runner,
            "PostgresReviewSnapshotAdapter",
            fixture.failing_adapter_factory,
        )
        _, failure_created = await agent_runner.reserve_agent_run(
            fixture.engine,
            run_id=fixture.failure_run_id,
            alert_id=fixture.alert_id,
            card_id=fixture.card_id,
            force_new=True,
        )
        failed_capture = await agent_runner.run_reserved_agent_graph(
            fixture.engine,
            fixture.request(fixture.failure_run_id),
            runtime=AsyncMock(),
        )
        unavailable = await _review(fixture.engine, fixture.failure_run_id)
        failure_state = await _failure_state(
            fixture.engine,
            fixture.failure_run_id,
        )

        monkeypatch.setattr(
            agent_runner,
            "PostgresReviewSnapshotAdapter",
            fixture.real_adapter_factory,
        )
        _, legacy_created = await agent_runner.reserve_agent_run(
            fixture.engine,
            run_id=fixture.legacy_run_id,
            alert_id=fixture.alert_id,
            card_id=fixture.card_id,
            force_new=True,
        )
        async with fixture.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE agent_runs SET review_snapshot_expected = NULL "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": fixture.legacy_run_id},
            )
        legacy = await agent_runner.run_reserved_agent_graph(
            fixture.engine,
            fixture.request(fixture.legacy_run_id),
            runtime=AsyncMock(),
        )
        legacy_review = await _review(fixture.engine, fixture.legacy_run_id)

        assert success.status == "completed", success.error
        assert before_review["task_status"] == "completed"
        assert before_review["ledger_status"] == "settled"
        assert before_review["checkpoint_id"] == fixture.success_checkpoint_id
        assert review.status == "available"
        assert review.snapshot is not None
        assert review.snapshot_hash is not None
        manual = next(
            item
            for item in review.snapshot.evidence
            if item.evidence_id == fixture.rag_chunk_id
        )
        assert manual.document_type == "operator_manual_evidence"
        assert manual.source == fixture.rag_source_path
        assert manual.source_owner == "operations"
        assert manual.provenance.source == fixture.rag_source_path
        assert [step.decision for step in review.snapshot.decisions] == [
            "rerun_model",
            "request_human",
        ]
        assert [step.sequence for step in review.snapshot.decisions] == [1, 2]
        assert review.snapshot.checkpoint.checkpoint_id == before_review["checkpoint_id"]
        assert reclaimed.status == "completed"
        assert snapshot_state["snapshot_count"] == 1
        assert snapshot_state["conflict_count"] == 1
        assert review_after_conflict.snapshot_hash == review.snapshot_hash

        assert failed_capture.status == "completed"
        assert failure_created is True
        assert unavailable.status == "unavailable"
        assert failure_state["run_status"] == "completed"
        assert failure_state["task_status"] == "completed"
        assert failure_state["snapshot_count"] == 0
        assert failure_state["unavailable_count"] == 1
        assert "must-not-persist" not in failure_state["unavailable_reason"]

        assert legacy.status == "completed"
        assert legacy_created is True
        assert legacy_review.status == "legacy_unavailable"
        assert legacy_review.snapshot is None
    finally:
        await _cleanup(fixture)


async def _review(
    engine: AsyncEngine,
    run_id: str,
) -> AgentRunReviewSnapshotResponse:
    review = await get_review_snapshot(engine, run_id)
    if review is None:
        raise AssertionError(f"review run is missing: {run_id}")
    return review


async def _task_state(engine: AsyncEngine, run_id: str) -> RowMapping:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT tasks.status AS task_status, ledger.status AS ledger_status, "
                "tasks.checkpoint_id FROM agent_run_tasks tasks "
                "JOIN agent_budget_ledger ledger ON ledger.task_id = tasks.task_id "
                "AND ledger.parent_ledger_id IS NULL WHERE tasks.run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    return result.mappings().one()


async def _snapshot_state(engine: AsyncEngine, run_id: str) -> RowMapping:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT count(*) AS snapshot_count, (SELECT count(*) "
                "FROM agent_run_events WHERE run_id = :run_id "
                "AND event_type = 'review_snapshot_conflict') AS conflict_count "
                "FROM agent_run_review_snapshots WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    return result.mappings().one()


async def _failure_state(engine: AsyncEngine, run_id: str) -> RowMapping:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT runs.status AS run_status, tasks.status AS task_status, "
                "(SELECT count(*) FROM agent_run_review_snapshots snapshots "
                "WHERE snapshots.run_id = runs.run_id) AS snapshot_count, "
                "(SELECT payload ->> 'reason' FROM agent_run_events events "
                "WHERE events.run_id = runs.run_id "
                "AND events.event_type = 'review_snapshot_unavailable' "
                "ORDER BY event_id DESC LIMIT 1) AS unavailable_reason "
                ", (SELECT count(*) FROM agent_run_events unavailable "
                "WHERE unavailable.run_id = runs.run_id "
                "AND unavailable.event_type = 'review_snapshot_unavailable') "
                "AS unavailable_count "
                "FROM agent_runs runs JOIN agent_run_tasks tasks "
                "ON tasks.run_id = runs.run_id WHERE runs.run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    return result.mappings().one()


async def _cleanup(harness: RunnerPostgresHarness) -> None:
    params = {
        "success": harness.success_run_id,
        "failure": harness.failure_run_id,
        "legacy": harness.legacy_run_id,
    }
    run_filter = (
        "IN (CAST(:success AS uuid), CAST(:failure AS uuid), CAST(:legacy AS uuid))"
    )
    try:
        async with harness.engine.begin() as connection:
            await connection.execute(
                text(f"DELETE FROM agent_loop_iterations WHERE run_id {run_filter}"),
                params,
            )
            await connection.execute(
                text("DELETE FROM windows WHERE window_id = :window_id"),
                {"window_id": harness.window_id},
            )
            await connection.execute(
                text("DELETE FROM rag_documents WHERE document_id = :document_id"),
                {"document_id": harness.rag_document_id},
            )
            remaining = await connection.execute(
                text(
                    "SELECT "
                    f"(SELECT count(*) FROM agent_runs WHERE run_id {run_filter}) + "
                    f"(SELECT count(*) FROM agent_run_tasks WHERE run_id {run_filter}) + "
                    f"(SELECT count(*) FROM agent_budget_ledger WHERE run_id {run_filter}) + "
                    f"(SELECT count(*) FROM agent_run_events WHERE run_id {run_filter}) + "
                    f"(SELECT count(*) FROM agent_loop_iterations WHERE run_id {run_filter}) + "
                    f"(SELECT count(*) FROM agent_run_review_snapshots WHERE run_id {run_filter})"
                ),
                params,
            )
            assert int(remaining.scalar_one()) == 0
    finally:
        await harness.engine.dispose()
