from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_api_models import (
    AgentRunListPage,
    AgentRunReviewSnapshotResponse,
    OperatorReviewStatus,
    WorkerStatus,
)
from agent_review_snapshot_repository import get_review_snapshot
from agent_run_listing_repository import (
    AgentRunCursor,
    AgentRunCursorError,
    AgentRunListFilters,
    list_agent_runs,
)
from schemas import AgentRunStatus


def make_agent_review_router(engine: AsyncEngine) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/agent-runs", response_model=AgentRunListPage)
    async def agent_runs(
        status: AgentRunStatus | None = None,
        operator_review_status: OperatorReviewStatus | None = None,
        worker_status: WorkerStatus | None = None,
        priority: str | None = Query(default=None, min_length=1, max_length=120),
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        cursor: str | None = Query(default=None, min_length=1, max_length=1000),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> AgentRunListPage:
        if (
            created_from is not None
            and created_to is not None
            and created_from > created_to
        ):
            raise HTTPException(
                status_code=422,
                detail="created_from must not be later than created_to",
            )
        try:
            parsed_cursor = None if cursor is None else AgentRunCursor.decode(cursor)
        except AgentRunCursorError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await list_agent_runs(
            engine,
            AgentRunListFilters(
                status=status,
                operator_review_status=operator_review_status,
                worker_status=worker_status,
                priority=priority,
                created_from=created_from,
                created_to=created_to,
                cursor=parsed_cursor,
                limit=limit,
            ),
        )

    @router.get(
        "/agent-runs/{run_id}/review",
        response_model=AgentRunReviewSnapshotResponse,
    )
    async def agent_run_review(run_id: str) -> AgentRunReviewSnapshotResponse:
        review = await get_review_snapshot(engine, run_id)
        if review is None:
            raise HTTPException(status_code=404, detail="run_id was not found")
        return review

    return router
