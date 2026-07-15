from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
from typing import Final
from unittest.mock import AsyncMock

import pytest

from heatgrid_ops.agent.graph import AgentGraphExecution
from heatgrid_ops.agent.models import OpsAgentOutput, TokenUsage
from heatgrid_ops.agent.review_models import (
    AgentRunReviewCaptureSource,
    ReviewCaptureFailure,
    ReviewBudgetLineage,
    ReviewCaptureSourceCardSnapshot,
    ReviewCheckpointLineage,
    ReviewDecisionStep,
    ReviewDiagnosticSnapshot,
    ReviewFinalResultSnapshot,
    ReviewOpsAgentOutput,
)
from heatgrid_ops.agent.run_models import AgentRunResult


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(BACKEND_DIR))

agent_runner = importlib.import_module("agent_runner")
snapshot_lineage = importlib.import_module("agent_review_snapshot_lineage")


@dataclass(frozen=True, slots=True)
class FakeTaskClaim:
    claimed: bool
    resume_from_checkpoint: bool = False
    lease_owner: str | None = None


@dataclass(frozen=True, slots=True)
class FakeSnapshotLineage:
    decisions: tuple[ReviewDecisionStep, ...]
    budget: ReviewBudgetLineage
    checkpoint: ReviewCheckpointLineage


@pytest.fixture(autouse=True)
def runner_input_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable_lineage(_engine, run_id: str):
        return agent_runner.AgentInputLineage(
            run_id=run_id,
            source_input=None,
            input_schema_version=None,
            input_hash=None,
            origin="native_v2",
            status="unavailable",
        )

    monkeypatch.setattr(
        agent_runner,
        "get_agent_input_lineage",
        unavailable_lineage,
    )


@pytest.mark.anyio
async def test_runner_completes_task_before_capturing_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    async def claim(*_args, **_kwargs) -> FakeTaskClaim:
        return FakeTaskClaim(claimed=True, lease_owner="lease-1")

    async def execute(*_args, **_kwargs) -> AgentGraphExecution:
        return AgentGraphExecution(result=_result(), review_capture_source=_source())

    async def complete(*_args, **_kwargs) -> None:
        events.append("task_completed")

    async def capture(*_args, **_kwargs) -> None:
        events.append("snapshot_captured")

    adapter = AsyncMock()

    async def mark_pending(_run_id: str) -> None:
        events.append("snapshot_pending")

    adapter.mark_pending.side_effect = mark_pending

    monkeypatch.setattr(agent_runner, "claim_agent_graph_task", claim)
    monkeypatch.setattr(agent_runner, "execute_agent_graph_with_capture", execute)
    monkeypatch.setattr(agent_runner, "complete_agent_graph_task", complete)
    monkeypatch.setattr(agent_runner, "_capture_completed_review_snapshot", capture)
    monkeypatch.setattr(
        agent_runner, "PostgresReviewSnapshotAdapter", lambda _engine: adapter
    )
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)

    response = await agent_runner.run_reserved_agent_graph(
        AsyncMock(),
        agent_runner.AgentRunRequest(
            run_id="run-1", alert_id="alert-1", card_id="card-1"
        ),
        runtime=AsyncMock(),
    )

    assert response.status == "completed"
    assert events == ["snapshot_pending", "task_completed", "snapshot_captured"]


@pytest.mark.anyio
async def test_pending_marker_failure_does_not_prevent_task_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    adapter = AsyncMock()
    adapter.mark_pending.side_effect = RuntimeError("secret=do-not-log")

    async def claim(*_args, **_kwargs) -> FakeTaskClaim:
        return FakeTaskClaim(claimed=True, lease_owner="lease-1")

    async def execute(*_args, **_kwargs) -> AgentGraphExecution:
        return AgentGraphExecution(result=_result(), review_capture_source=_source())

    async def complete(*_args, **_kwargs) -> None:
        events.append("task_completed")

    async def capture(*_args, **_kwargs) -> None:
        events.append("snapshot_captured")

    monkeypatch.setattr(agent_runner, "claim_agent_graph_task", claim)
    monkeypatch.setattr(agent_runner, "execute_agent_graph_with_capture", execute)
    monkeypatch.setattr(agent_runner, "complete_agent_graph_task", complete)
    monkeypatch.setattr(agent_runner, "_capture_completed_review_snapshot", capture)
    monkeypatch.setattr(
        agent_runner, "PostgresReviewSnapshotAdapter", lambda _engine: adapter
    )
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)

    response = await agent_runner.run_reserved_agent_graph(
        AsyncMock(),
        agent_runner.AgentRunRequest(
            run_id="run-1", alert_id="alert-1", card_id="card-1"
        ),
        runtime=AsyncMock(),
    )

    assert response.status == "completed"
    assert events == ["task_completed", "snapshot_captured"]
    assert adapter.mark_pending.await_count == 2


@pytest.mark.anyio
async def test_capture_failure_marks_unavailable_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = AsyncMock()
    adapter.capture.side_effect = RuntimeError("secret=do-not-store")
    monkeypatch.setattr(
        agent_runner,
        "PostgresReviewSnapshotAdapter",
        lambda _engine: adapter,
    )
    monkeypatch.setattr(
        agent_runner,
        "load_review_snapshot_lineage",
        AsyncMock(return_value=_lineage()),
    )

    await agent_runner._capture_completed_review_snapshot(AsyncMock(), _source())

    adapter.mark_unavailable.assert_awaited_once()
    reason = adapter.mark_unavailable.await_args.args[1]
    assert "RuntimeError" in reason
    assert "do-not-store" not in reason


@pytest.mark.anyio
async def test_runner_does_not_fabricate_snapshot_without_capture_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = AsyncMock()
    adapter = AsyncMock()

    async def claim(*_args, **_kwargs) -> FakeTaskClaim:
        return FakeTaskClaim(claimed=True, lease_owner="lease-1")

    async def execute(*_args, **_kwargs) -> AgentGraphExecution:
        return AgentGraphExecution(result=_result(), review_capture_source=None)

    monkeypatch.setattr(agent_runner, "claim_agent_graph_task", claim)
    monkeypatch.setattr(agent_runner, "execute_agent_graph_with_capture", execute)
    monkeypatch.setattr(agent_runner, "complete_agent_graph_task", AsyncMock())
    monkeypatch.setattr(agent_runner, "_capture_completed_review_snapshot", capture)
    monkeypatch.setattr(
        agent_runner, "PostgresReviewSnapshotAdapter", lambda _engine: adapter
    )
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)

    response = await agent_runner.run_reserved_agent_graph(
        AsyncMock(),
        agent_runner.AgentRunRequest(
            run_id="run-1", alert_id="alert-1", card_id="card-1"
        ),
        runtime=AsyncMock(),
    )

    assert response.status == "completed"
    capture.assert_not_awaited()
    adapter.mark_pending.assert_not_awaited()
    adapter.mark_unavailable.assert_not_awaited()


@pytest.mark.anyio
async def test_runner_marks_capture_build_failure_unavailable_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    adapter = AsyncMock()

    async def claim(*_args, **_kwargs) -> FakeTaskClaim:
        return FakeTaskClaim(claimed=True, lease_owner="lease-1")

    async def execute(*_args, **_kwargs) -> AgentGraphExecution:
        return AgentGraphExecution(
            result=_result(),
            review_capture_source=None,
            review_capture_failure=ReviewCaptureFailure(
                error_type="ValidationError",
                message="secret=do-not-store",
            ),
        )

    async def complete(*_args, **_kwargs) -> None:
        events.append("task_completed")

    async def mark_unavailable(_run_id: str, reason: str) -> None:
        events.append("snapshot_unavailable")
        assert reason == "ValidationError: review snapshot source unavailable"

    adapter.mark_unavailable.side_effect = mark_unavailable
    monkeypatch.setattr(agent_runner, "claim_agent_graph_task", claim)
    monkeypatch.setattr(agent_runner, "execute_agent_graph_with_capture", execute)
    monkeypatch.setattr(agent_runner, "complete_agent_graph_task", complete)
    monkeypatch.setattr(
        agent_runner, "PostgresReviewSnapshotAdapter", lambda _engine: adapter
    )
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)

    response = await agent_runner.run_reserved_agent_graph(
        AsyncMock(),
        agent_runner.AgentRunRequest(
            run_id="run-1", alert_id="alert-1", card_id="card-1"
        ),
        runtime=AsyncMock(),
    )

    assert response.status == "completed"
    assert events == ["snapshot_unavailable", "task_completed"]
    adapter.mark_pending.assert_not_awaited()


@pytest.mark.anyio
async def test_unavailable_marker_failure_does_not_prevent_task_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete = AsyncMock()
    adapter = AsyncMock()
    adapter.mark_unavailable.side_effect = RuntimeError("secret=do-not-log")

    async def claim(*_args, **_kwargs) -> FakeTaskClaim:
        return FakeTaskClaim(claimed=True, lease_owner="lease-1")

    async def execute(*_args, **_kwargs) -> AgentGraphExecution:
        return AgentGraphExecution(
            result=_result(),
            review_capture_source=None,
            review_capture_failure=ReviewCaptureFailure(
                error_type="RuntimeError",
                message="secret=do-not-store",
            ),
        )

    monkeypatch.setattr(agent_runner, "claim_agent_graph_task", claim)
    monkeypatch.setattr(agent_runner, "execute_agent_graph_with_capture", execute)
    monkeypatch.setattr(agent_runner, "complete_agent_graph_task", complete)
    monkeypatch.setattr(
        agent_runner, "PostgresReviewSnapshotAdapter", lambda _engine: adapter
    )
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)

    response = await agent_runner.run_reserved_agent_graph(
        AsyncMock(),
        agent_runner.AgentRunRequest(
            run_id="run-1", alert_id="alert-1", card_id="card-1"
        ),
        runtime=AsyncMock(),
    )

    assert response.status == "completed"
    complete.assert_awaited_once()
    assert adapter.mark_unavailable.await_count == 2


@pytest.mark.anyio
async def test_completed_task_reclaim_does_not_capture_snapshot_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = iter(
        (
            FakeTaskClaim(claimed=True, lease_owner="lease-1"),
            FakeTaskClaim(claimed=False),
        )
    )
    execute = AsyncMock(
        return_value=AgentGraphExecution(
            result=_result(), review_capture_source=_source()
        )
    )
    capture = AsyncMock()
    adapter = AsyncMock()
    existing = agent_runner.AgentRunResponse.model_validate(
        _result().model_dump(mode="json")
    )

    async def claim(*_args, **_kwargs) -> FakeTaskClaim:
        return next(claims)

    monkeypatch.setattr(agent_runner, "claim_agent_graph_task", claim)
    monkeypatch.setattr(agent_runner, "execute_agent_graph_with_capture", execute)
    monkeypatch.setattr(agent_runner, "complete_agent_graph_task", AsyncMock())
    monkeypatch.setattr(agent_runner, "_capture_completed_review_snapshot", capture)
    monkeypatch.setattr(
        agent_runner, "PostgresReviewSnapshotAdapter", lambda _engine: adapter
    )
    monkeypatch.setattr(agent_runner, "get_agent_run", AsyncMock(return_value=existing))
    monkeypatch.setattr(agent_runner, "create_agent_graph_context", lambda *_: None)
    request = agent_runner.AgentRunRequest(
        run_id="run-1", alert_id="alert-1", card_id="card-1"
    )

    first = await agent_runner.run_reserved_agent_graph(
        AsyncMock(), request, runtime=AsyncMock()
    )
    reclaimed = await agent_runner.run_reserved_agent_graph(
        AsyncMock(), request, runtime=AsyncMock()
    )

    assert first.status == "completed"
    assert reclaimed.status == "completed"
    execute.assert_awaited_once()
    capture.assert_awaited_once()
    adapter.mark_pending.assert_awaited_once()


def test_snapshot_assembly_maps_db_lineage_and_graph_evidence() -> None:
    snapshot = snapshot_lineage.assemble_review_snapshot(_source(), _lineage())

    assert [step.decision for step in snapshot.decisions] == [
        "rerun_model",
        "request_human",
    ]
    assert snapshot.loop_count == 2
    assert snapshot.budget.parent_tokens_used == 900
    assert snapshot.budget.diagnostic_tokens_used == 120
    assert snapshot.checkpoint.checkpoint_id == "checkpoint-2"
    assert snapshot.source_card.priority_level == "urgent"


def _source() -> AgentRunReviewCaptureSource:
    return AgentRunReviewCaptureSource(
        run_id="run-1",
        result=ReviewFinalResultSnapshot(
            status="completed",
            agent_mode="fallback",
            ops_output=ReviewOpsAgentOutput(
                summary="summary",
                action_plan="monitor",
                caution="review",
            ),
        ),
        loop_count=2,
        handling_reason="human verification required",
        diagnostic=ReviewDiagnosticSnapshot(
            status="completed",
            input_tokens=100,
            output_tokens=20,
        ),
        source_card=ReviewCaptureSourceCardSnapshot(
            card_id="card-1",
            substation_id=31,
            manufacturer_id="maker-1",
            priority_level="urgent",
            status="open",
            review_required=True,
            reason="model mismatch",
        ),
    )


def _lineage() -> FakeSnapshotLineage:
    return FakeSnapshotLineage(
        decisions=(
            ReviewDecisionStep(
                sequence=1,
                decision="rerun_model",
                reason="assessment",
            ),
            ReviewDecisionStep(
                sequence=2,
                decision="request_human",
                reason="assessment",
            ),
        ),
        budget=ReviewBudgetLineage(
            parent_token_limit=60_000,
            parent_tokens_used=900,
            diagnostic_token_limit=4_000,
            diagnostic_tokens_used=120,
        ),
        checkpoint=ReviewCheckpointLineage(
            thread_id="run-1",
            namespace="",
            checkpoint_id="checkpoint-2",
        ),
    )


def _result() -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        status="completed",
        input_source="alert",
        alert_id="alert-1",
        card_id="card-1",
        agent_mode="fallback",
        ops_output=OpsAgentOutput(
            summary="summary",
            action_plan="monitor",
            caution="review",
        ),
        token_usage=TokenUsage(total_tokens=900),
    )
