from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.priority.evaluation import (
    create_priority_evaluation,
    ensure_latest_priority_evaluation,
    get_latest_priority_evaluation,
    get_latest_substation_result,
    get_priority_evaluation,
    latest_alert_results,
)
from schemas import (
    PriorityEvaluationCreateRequest,
    PriorityEvaluationResult,
    PriorityEvaluationSnapshot,
    PrioritySubstationSnapshot,
)
from settings import Settings


def make_priority_evaluation_router(
    engine: AsyncEngine,
    settings: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/api/priority-evaluations")

    @router.post("", response_model=PriorityEvaluationSnapshot)
    async def create_evaluation(
        payload: PriorityEvaluationCreateRequest,
    ) -> PriorityEvaluationSnapshot:
        try:
            snapshot = await create_priority_evaluation(
                engine,
                as_of_time=payload.as_of_time,
                stale_after_hours=(
                    payload.stale_after_hours
                    or settings.priority_stale_after_hours
                ),
                model_version=settings.priority_model_version,
                expected_substations=settings.priority_expected_substations,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return PriorityEvaluationSnapshot.model_validate(snapshot)

    @router.get("/latest", response_model=PriorityEvaluationSnapshot)
    async def latest_evaluation() -> PriorityEvaluationSnapshot:
        snapshot = await _latest_or_create(engine, settings)
        return PriorityEvaluationSnapshot.model_validate(snapshot)

    @router.get(
        "/latest/alerts",
        response_model=list[PriorityEvaluationResult],
    )
    async def latest_priority_alert_results() -> list[PriorityEvaluationResult]:
        snapshot = await _latest_or_create(engine, settings)
        return [
            PriorityEvaluationResult.model_validate(row)
            for row in latest_alert_results(snapshot)
        ]

    @router.get(
        "/latest/substations/{substation_id}",
        response_model=PrioritySubstationSnapshot,
    )
    async def latest_substation(
        substation_id: int,
        manufacturer_id: str | None = Query(default=None),
    ) -> PrioritySubstationSnapshot:
        await _latest_or_create(engine, settings)
        snapshot = await get_latest_substation_result(
            engine,
            substation_id,
            manufacturer_id=manufacturer_id,
        )
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail="최신 평가에서 Substation을 찾을 수 없습니다.",
            )
        return PrioritySubstationSnapshot.model_validate(snapshot)

    @router.get("/{evaluation_run_id}", response_model=PriorityEvaluationSnapshot)
    async def evaluation(evaluation_run_id: str) -> PriorityEvaluationSnapshot:
        snapshot = await get_priority_evaluation(engine, evaluation_run_id)
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail="evaluation_run_id를 찾을 수 없습니다.",
            )
        return PriorityEvaluationSnapshot.model_validate(snapshot)

    return router


async def _latest_or_create(
    engine: AsyncEngine,
    settings: Settings,
) -> dict[str, object]:
    latest = await get_latest_priority_evaluation(engine)
    if latest is not None:
        return latest
    try:
        return await ensure_latest_priority_evaluation(
            engine,
            stale_after_hours=settings.priority_stale_after_hours,
            model_version=settings.priority_model_version,
            expected_substations=settings.priority_expected_substations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
