from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.contracts import AgentReviewRequest
from heatgrid_ops.agent.run_models import ReviewTaskSnapshot
from review_repository import create_review_task
from schemas import HumanReviewTask


@dataclass(frozen=True, slots=True)
class PostgresAgentReviewAdapter:
    engine: AsyncEngine

    async def create_review(self, request: AgentReviewRequest) -> ReviewTaskSnapshot:
        payload: dict[str, object] = {
            key: value for key, value in request.payload.items()
        }
        task = await create_review_task(
            self.engine,
            task_type=request.task_type,
            risk_level=request.risk_level,
            title=request.title,
            payload=payload,
            status=request.status,
            run_id=request.run_id,
            candidate_id=request.candidate_id,
            reviewed_by=request.reviewed_by,
            operation_key=None
            if request.run_id is None
            else f"agent-review:{request.run_id}:{request.task_type}",
        )
        return _task_snapshot(task)


def _task_snapshot(task: HumanReviewTask) -> ReviewTaskSnapshot:
    return ReviewTaskSnapshot(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
    )
