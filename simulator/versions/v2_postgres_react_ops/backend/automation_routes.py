from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.approval.policy import ApprovalPolicyContext, decide_approval
from retrain_repository import (
    create_retrain_job,
    list_model_candidates,
    list_retrain_jobs,
    review_retrain_job,
)
from retrain_service import execute_retrain_job
from review_repository import (
    create_evidence_candidate,
    create_review_task,
    get_automation_policy,
    get_evidence_candidate,
    get_review_task,
    list_evidence_candidates,
    list_review_tasks,
    list_training_feedback,
    review_evidence_candidate,
    submit_review_task,
    update_automation_policy,
)
from schemas import (
    AutomationPolicy,
    AutomationPolicyUpdateRequest,
    EvidenceCandidate,
    EvidenceCandidateCreateRequest,
    EvidenceCandidateReviewRequest,
    HumanReviewTask,
    RetrainJob,
    RetrainJobActionRequest,
    RetrainJobCreateRequest,
    ReviewSubmitResponse,
    ReviewTaskSubmitRequest,
    TrainingFeedback,
)
from settings import Settings

LOGGER = logging.getLogger(__name__)


def make_automation_router(engine: AsyncEngine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/review-tasks", response_model=list[HumanReviewTask])
    async def review_tasks(
        status: str | None = None,
        task_type: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[HumanReviewTask]:
        return await list_review_tasks(
            engine,
            status=status,
            task_type=task_type,
            limit=limit,
        )

    @router.get("/review-tasks/{task_id}", response_model=HumanReviewTask)
    async def review_task(task_id: str) -> HumanReviewTask:
        task = await get_review_task(engine, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task_id를 찾을 수 없습니다.")
        return task

    @router.post(
        "/review-tasks/{task_id}/submit",
        response_model=ReviewSubmitResponse,
    )
    async def submit_review(
        task_id: str,
        payload: ReviewTaskSubmitRequest,
        background_tasks: BackgroundTasks,
    ) -> ReviewSubmitResponse:
        if (
            payload.decision == "correct"
            and payload.corrected_output is None
            and payload.corrected_label is None
        ):
            raise HTTPException(
                status_code=422,
                detail="교정 결정에는 corrected_output 또는 corrected_label이 필요합니다.",
            )
        try:
            result = await submit_review_task(engine, task_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="task_id를 찾을 수 없습니다.")
        try:
            retrain_job = await _maybe_start_automatic_retrain(
                engine,
                settings,
                result,
                background_tasks,
            )
        except Exception:  # 검수 저장 성공을 후속 자동화 장애로 되돌리지 않는다.
            LOGGER.exception("자동 재학습 예약에 실패했습니다.")
            retrain_job = None
        if retrain_job is None:
            return result
        return result.model_copy(
            update={
                "automatic_retrain_job_id": retrain_job.job_id,
                "automatic_retrain_status": retrain_job.status,
            }
        )

    @router.get("/evidence-candidates", response_model=list[EvidenceCandidate])
    async def evidence_candidates(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[EvidenceCandidate]:
        return await list_evidence_candidates(engine, status=status, limit=limit)

    @router.get(
        "/evidence-candidates/{candidate_id}",
        response_model=EvidenceCandidate,
    )
    async def evidence_candidate(candidate_id: str) -> EvidenceCandidate:
        candidate = await get_evidence_candidate(engine, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="candidate_id를 찾을 수 없습니다.")
        return candidate

    @router.post("/evidence-candidates", response_model=EvidenceCandidate)
    async def add_evidence_candidate(
        payload: EvidenceCandidateCreateRequest,
    ) -> EvidenceCandidate:
        policy = await get_automation_policy(engine)
        approval = decide_approval(
            policy,
            ApprovalPolicyContext(
                task_type="evidence_candidate",
                risk_level=payload.risk_level,
                confidence=payload.trust_score,
                source_trust=payload.trust_score,
            ),
        )
        auto = approval.action == "auto_approve"
        candidate = await create_evidence_candidate(
            engine,
            payload,
            status="auto_approved" if auto else "pending",
            reviewed_by="automation-policy" if auto else None,
            review_reason=approval.reason if auto else None,
        )
        await create_review_task(
            engine,
            task_type="evidence_candidate",
            risk_level=payload.risk_level,
            title=f"외부 근거 후보 검수: {payload.title}",
            run_id=payload.run_id,
            candidate_id=candidate.candidate_id,
            payload=candidate.model_dump(mode="json"),
            status="auto_approved" if auto else "pending",
            reviewed_by="automation-policy" if auto else None,
        )
        return candidate

    @router.post(
        "/evidence-candidates/{candidate_id}/review",
        response_model=EvidenceCandidate,
    )
    async def review_candidate(
        candidate_id: str,
        payload: EvidenceCandidateReviewRequest,
    ) -> EvidenceCandidate:
        candidate = await review_evidence_candidate(engine, candidate_id, payload)
        if candidate is None:
            raise HTTPException(status_code=404, detail="candidate_id를 찾을 수 없습니다.")
        return candidate

    @router.get("/training-feedback", response_model=list[TrainingFeedback])
    async def training_feedback(
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[TrainingFeedback]:
        return await list_training_feedback(engine, limit=limit)

    @router.get("/automation-policy", response_model=AutomationPolicy)
    async def automation_policy() -> AutomationPolicy:
        return await get_automation_policy(engine)

    @router.patch("/automation-policy", response_model=AutomationPolicy)
    async def patch_automation_policy(
        payload: AutomationPolicyUpdateRequest,
    ) -> AutomationPolicy:
        return await update_automation_policy(engine, payload)

    return router


async def _maybe_start_automatic_retrain(
    engine: AsyncEngine,
    settings: Settings,
    result: ReviewSubmitResponse,
    background_tasks: BackgroundTasks,
) -> RetrainJob | None:
    feedback = result.feedback
    if (
        not settings.retrain_auto_execute_enabled
        or feedback is None
        or not feedback.corrected_label
    ):
        return None

    policy = await get_automation_policy(engine)
    approval = decide_approval(
        policy,
        ApprovalPolicyContext(
            task_type="retrain_approval",
            risk_level="low",
            confidence=1.0,
            source_trust=1.0,
            drift_score=0.0,
        ),
    )
    if approval.action != "auto_approve":
        return None

    jobs = await list_retrain_jobs(engine, limit=500)
    if any(job.status in {"pending_approval", "approved", "running"} for job in jobs):
        return None
    candidates = await list_model_candidates(engine, limit=500)
    if any(candidate.status == "awaiting_promotion" for candidate in candidates):
        return None

    job = await create_retrain_job(
        engine,
        RetrainJobCreateRequest(
            requested_by="automation-policy",
            reason="누적 사람 검수 교정 라벨을 반영한 제한 자동 재학습",
            feedback_ids=[],
            auto_start_when_approved=True,
        ),
    )
    approved = await review_retrain_job(
        engine,
        job.job_id,
        RetrainJobActionRequest(
            reviewer="automation-policy",
            reason=approval.reason,
        ),
        approve=True,
    )
    if approved is None:
        return None
    background_tasks.add_task(execute_retrain_job, engine, approved.job_id)
    return approved
