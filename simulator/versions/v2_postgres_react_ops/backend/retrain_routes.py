from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncEngine

from retrain_repository import (
    create_retrain_job,
    get_active_model_deployment,
    get_model_candidate,
    get_retrain_job,
    list_model_candidates,
    list_retrain_jobs,
    review_model_candidate,
    review_retrain_job,
)
from retrain_service import activate_model_candidate, execute_retrain_job
from review_repository import create_review_task
from schemas import (
    ModelCandidate,
    ModelDeployment,
    ModelPromotionRequest,
    RetrainJob,
    RetrainJobActionRequest,
    RetrainJobCreateRequest,
)


def make_retrain_router(engine: AsyncEngine) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/retrain-jobs", response_model=list[RetrainJob])
    async def retrain_jobs(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[RetrainJob]:
        return await list_retrain_jobs(engine, status=status, limit=limit)

    @router.get("/retrain-jobs/{job_id}", response_model=RetrainJob)
    async def retrain_job(job_id: str) -> RetrainJob:
        job = await get_retrain_job(engine, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_id를 찾을 수 없습니다.")
        return job

    @router.post("/retrain-jobs", response_model=RetrainJob)
    async def add_retrain_job(payload: RetrainJobCreateRequest) -> RetrainJob:
        try:
            job = await create_retrain_job(engine, payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await create_review_task(
            engine,
            task_type="retrain_approval",
            risk_level="high",
            title=f"재학습 작업 승인: {job.job_id}",
            retrain_job_id=job.job_id,
            payload=job.model_dump(mode="json"),
        )
        return job

    @router.post("/retrain-jobs/{job_id}/approve", response_model=RetrainJob)
    async def approve_retrain_job(
        job_id: str,
        payload: RetrainJobActionRequest,
        background_tasks: BackgroundTasks,
    ) -> RetrainJob:
        job = await review_retrain_job(engine, job_id, payload, approve=True)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail="승인 대기 중인 job_id를 찾을 수 없습니다.",
            )
        background_tasks.add_task(execute_retrain_job, engine, job_id)
        return job

    @router.post("/retrain-jobs/{job_id}/reject", response_model=RetrainJob)
    async def reject_retrain_job(
        job_id: str,
        payload: RetrainJobActionRequest,
    ) -> RetrainJob:
        job = await review_retrain_job(engine, job_id, payload, approve=False)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail="승인 대기 중인 job_id를 찾을 수 없습니다.",
            )
        return job

    @router.get("/model-candidates", response_model=list[ModelCandidate])
    async def model_candidates(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[ModelCandidate]:
        return await list_model_candidates(engine, status=status, limit=limit)

    @router.get("/model-candidates/{candidate_id}", response_model=ModelCandidate)
    async def model_candidate(candidate_id: str) -> ModelCandidate:
        candidate = await get_model_candidate(engine, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="candidate_id를 찾을 수 없습니다.")
        return candidate

    @router.post(
        "/model-candidates/{candidate_id}/promote",
        response_model=ModelCandidate,
    )
    async def promote_model_candidate(
        candidate_id: str,
        payload: ModelPromotionRequest,
    ) -> ModelCandidate:
        try:
            reviewed = await review_model_candidate(engine, candidate_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if reviewed is None:
            raise HTTPException(status_code=404, detail="candidate_id를 찾을 수 없습니다.")
        candidate, deployment = reviewed
        if deployment is not None:
            try:
                activate_model_candidate(
                    candidate.artifact_uri,
                    deployment.model_dump(mode="json"),
                )
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        return candidate

    @router.get("/model-deployments/active", response_model=ModelDeployment | None)
    async def active_model_deployment() -> ModelDeployment | None:
        return await get_active_model_deployment(engine)

    return router
