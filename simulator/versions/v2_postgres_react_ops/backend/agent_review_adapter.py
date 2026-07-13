from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.contracts import AgentReviewRequest, EvidenceCandidateStage
from heatgrid_ops.agent.run_models import (
    AutomationPolicySnapshot,
    EvidenceCandidateSnapshot,
    ReviewTaskSnapshot,
)
from review_repository import (
    create_evidence_candidate,
    create_review_task,
    get_automation_policy,
    get_review_task,
)
from schemas import EvidenceCandidateCreateRequest, HumanReviewTask


@dataclass(frozen=True, slots=True)
class PostgresAgentReviewAdapter:
    engine: AsyncEngine

    async def automation_policy(self) -> AutomationPolicySnapshot:
        policy = await get_automation_policy(self.engine)
        return AutomationPolicySnapshot.model_validate(policy.model_dump(mode="json"))

    async def review_task(self, task_id: str) -> ReviewTaskSnapshot | None:
        task = await get_review_task(self.engine, task_id)
        return None if task is None else _task_snapshot(task)

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
        )
        return _task_snapshot(task)

    async def stage_evidence(
        self,
        stage: EvidenceCandidateStage,
    ) -> EvidenceCandidateSnapshot:
        request = EvidenceCandidateCreateRequest.model_validate(
            stage.candidate.model_dump(mode="json")
        )
        candidate = await create_evidence_candidate(
            self.engine,
            request,
            status=stage.status,
            reviewed_by=stage.reviewed_by,
            review_reason=stage.review_reason,
        )
        await create_review_task(
            self.engine,
            task_type="evidence_candidate",
            risk_level=request.risk_level,
            title=f"외부 근거 후보 검수: {candidate.title}",
            payload=candidate.model_dump(mode="json"),
            status=stage.status,
            run_id=request.run_id,
            candidate_id=candidate.candidate_id,
            reviewed_by=stage.reviewed_by,
        )
        return EvidenceCandidateSnapshot(
            candidate_id=candidate.candidate_id,
            title=candidate.title,
            content=candidate.content,
            source_uri=candidate.source_uri,
            status=candidate.status,
            trust_score=candidate.trust_score,
        )


def _task_snapshot(task: HumanReviewTask) -> ReviewTaskSnapshot:
    return ReviewTaskSnapshot(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
    )
