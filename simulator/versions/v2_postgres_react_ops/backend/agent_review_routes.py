from __future__ import annotations

from datetime import UTC, datetime
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_execution_repository import AGENT_GRAPH_TASK_KEY_V2
from agent_rerun_repository import TargetedChildRun
from agent_runner import schedule_reserved_agent_graph
from agent_runtime_factory import create_agent_runtime

from agent_activity_projection_repository import (
    ActivityProjectionFilters,
    list_agent_reports,
    list_work_orders,
)
from agent_review_api_models import (
    AgentOperationsMetricsResponse,
    AgentReportListPage,
    AgentRunEvaluationPage,
    AgentRunListPage,
    AgentRunReviewSnapshotResponse,
    OperatorReviewStatus,
    OperatorReviewHistoryResponse,
    OperatorReviewRecordResponse,
    OperatorReviewSubmitRequest,
    ParentHandling,
    PolicyCandidateDecisionRequest,
    PolicyCandidatePage,
    PolicyCandidateResponse,
    PolicyCandidateStatus,
    WorkOrderListPage,
    WorkerStatus,
)
from agent_operations_metrics_repository import (
    AgentOperationsMetricFilters,
    get_agent_operations_metrics,
)
from agent_operator_review_repository import (
    IdempotencyConflictError,
    StaleReviewVersionError,
    UnknownRunError,
    list_operator_reviews,
    submit_operator_review,
)
from agent_policy_candidate_repository import (
    StalePolicyCandidateVersionError,
    decide_policy_candidate,
    list_policy_candidates,
)
from agent_review_snapshot_repository import get_review_snapshot
from agent_run_evaluation_repository import (
    AgentRunEvaluationFilters,
    list_agent_run_evaluations,
)
from agent_run_listing_repository import (
    AgentRunCursor,
    AgentRunCursorError,
    AgentRunListFilters,
    list_agent_runs,
)
from schemas import AgentRunStatus
from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.graph import AgentGraphInvoker
from heatgrid_ops.agent.services import AgentRuntime
from settings import Settings


def make_agent_review_router(
    engine: AsyncEngine,
    settings: Settings | None = None,
    runtime: AgentRuntime | None = None,
    graph_provider: Callable[[], AgentGraphInvoker | None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    active_settings = settings or Settings()
    active_runtime = runtime or create_agent_runtime(active_settings, engine)

    def schedule_child(child: TargetedChildRun) -> None:
        schedule_reserved_agent_graph(
            engine,
            AgentRunRequest(
                run_id=child.run_id,
                alert_id=child.alert_id,
                card_id=child.card_id,
            ),
            runtime=active_runtime,
            graph=None if graph_provider is None else graph_provider(),
            task_key=AGENT_GRAPH_TASK_KEY_V2,
        )

    @router.get("/agent-runs", response_model=AgentRunListPage)
    async def agent_runs(
        status: AgentRunStatus | None = None,
        operator_review_status: OperatorReviewStatus | None = None,
        worker_status: WorkerStatus | None = None,
        priority: str | None = Query(default=None, min_length=1, max_length=120),
        substation_id: int | None = Query(default=None, ge=0),
        search: str | None = Query(default=None, min_length=1, max_length=200),
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        cursor: str | None = Query(default=None, min_length=1, max_length=1000),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> AgentRunListPage:
        normalized_from, normalized_to = _normalize_period(created_from, created_to)
        parsed_cursor = _parse_cursor(cursor)
        return await list_agent_runs(
            engine,
            AgentRunListFilters(
                status=status,
                operator_review_status=operator_review_status,
                worker_status=worker_status,
                priority=priority,
                substation_id=substation_id,
                search=search,
                created_from=normalized_from,
                created_to=normalized_to,
                cursor=parsed_cursor,
                limit=limit,
            ),
        )

    @router.get("/work-orders", response_model=WorkOrderListPage)
    async def work_orders(
        operator_review_status: OperatorReviewStatus | None = None,
        substation_id: int | None = Query(default=None, ge=0),
        search: str | None = Query(default=None, min_length=1, max_length=200),
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        cursor: str | None = Query(default=None, min_length=1, max_length=1000),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> WorkOrderListPage:
        normalized_from, normalized_to = _normalize_period(created_from, created_to)
        parsed_cursor = _parse_cursor(cursor)
        return await list_work_orders(
            engine,
            ActivityProjectionFilters(
                operator_review_status=operator_review_status,
                substation_id=substation_id,
                search=search,
                created_from=normalized_from,
                created_to=normalized_to,
                cursor=parsed_cursor,
                limit=limit,
            ),
        )

    @router.get("/agent-reports", response_model=AgentReportListPage)
    async def agent_reports(
        operator_review_status: OperatorReviewStatus | None = None,
        substation_id: int | None = Query(default=None, ge=0),
        search: str | None = Query(default=None, min_length=1, max_length=200),
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        cursor: str | None = Query(default=None, min_length=1, max_length=1000),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> AgentReportListPage:
        normalized_from, normalized_to = _normalize_period(created_from, created_to)
        parsed_cursor = _parse_cursor(cursor)
        return await list_agent_reports(
            engine,
            ActivityProjectionFilters(
                operator_review_status=operator_review_status,
                substation_id=substation_id,
                search=search,
                created_from=normalized_from,
                created_to=normalized_to,
                cursor=parsed_cursor,
                limit=limit,
            ),
        )

    @router.get(
        "/agent-runs/{run_id}/review",
        response_model=AgentRunReviewSnapshotResponse,
    )
    async def agent_run_review(run_id: UUID) -> AgentRunReviewSnapshotResponse:
        review = await get_review_snapshot(engine, str(run_id))
        if review is None:
            raise HTTPException(status_code=404, detail="run_id was not found")
        return review

    @router.get(
        "/agent-run-evaluations",
        response_model=AgentRunEvaluationPage,
    )
    async def agent_run_evaluations(
        run_id: UUID | None = None,
        worker_status: WorkerStatus | None = None,
        parent_handling: ParentHandling | None = None,
        operator_review_status: OperatorReviewStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        cursor: str | None = Query(default=None, min_length=1, max_length=1000),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> AgentRunEvaluationPage:
        normalized_from, normalized_to = _normalize_period(created_from, created_to)
        parsed_cursor = _parse_cursor(cursor)
        return await list_agent_run_evaluations(
            engine,
            AgentRunEvaluationFilters(
                run_id=None if run_id is None else str(run_id),
                worker_status=worker_status,
                parent_handling=parent_handling,
                operator_review_status=operator_review_status,
                created_from=normalized_from,
                created_to=normalized_to,
                cursor=parsed_cursor,
                limit=limit,
            ),
        )

    @router.post(
        "/agent-runs/{run_id}/reviews",
        response_model=OperatorReviewRecordResponse,
    )
    async def submit_agent_run_review(
        run_id: UUID,
        request: OperatorReviewSubmitRequest,
    ) -> OperatorReviewRecordResponse:
        try:
            return await submit_operator_review(
                engine,
                str(run_id),
                request,
                rag_quality_enabled=active_settings.rag_quality_enabled,
                schedule_child=schedule_child,
            )
        except UnknownRunError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StaleReviewVersionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get(
        "/agent-runs/{run_id}/reviews",
        response_model=OperatorReviewHistoryResponse,
    )
    async def agent_run_reviews(run_id: UUID) -> OperatorReviewHistoryResponse:
        history = await list_operator_reviews(engine, str(run_id))
        if history is None:
            raise HTTPException(status_code=404, detail="run_id was not found")
        return history

    @router.get(
        "/agent-policy-candidates",
        response_model=PolicyCandidatePage,
    )
    async def agent_policy_candidates(
        status: PolicyCandidateStatus | None = None,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> PolicyCandidatePage:
        return await list_policy_candidates(engine, status=status, limit=limit)

    @router.post(
        "/agent-policy-candidates/{candidate_id}/approve",
        response_model=PolicyCandidateResponse,
    )
    async def approve_policy_candidate(
        candidate_id: UUID,
        request: PolicyCandidateDecisionRequest,
    ) -> PolicyCandidateResponse:
        return await _decide_policy_candidate(
            str(candidate_id), request, decision="approved"
        )

    @router.post(
        "/agent-policy-candidates/{candidate_id}/reject",
        response_model=PolicyCandidateResponse,
    )
    async def reject_policy_candidate(
        candidate_id: UUID,
        request: PolicyCandidateDecisionRequest,
    ) -> PolicyCandidateResponse:
        return await _decide_policy_candidate(
            str(candidate_id), request, decision="rejected"
        )

    @router.get(
        "/agent-operations/metrics",
        response_model=AgentOperationsMetricsResponse,
    )
    async def agent_operations_metrics(
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AgentOperationsMetricsResponse:
        normalized_from, normalized_to = _normalize_period(created_from, created_to)
        return await get_agent_operations_metrics(
            engine,
            AgentOperationsMetricFilters(
                created_from=normalized_from,
                created_to=normalized_to,
            ),
        )

    async def _decide_policy_candidate(
        candidate_id: str,
        request: PolicyCandidateDecisionRequest,
        *,
        decision: PolicyCandidateStatus,
    ) -> PolicyCandidateResponse:
        try:
            candidate = await decide_policy_candidate(
                engine,
                candidate_id,
                request,
                decision=decision,
            )
        except StalePolicyCandidateVersionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if candidate is None:
            raise HTTPException(status_code=404, detail="candidate_id was not found")
        return candidate

    return router


def _normalize_period(
    created_from: datetime | None,
    created_to: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if any(
        value is not None and value.utcoffset() is None
        for value in (created_from, created_to)
    ):
        raise HTTPException(
            status_code=422,
            detail="created_from and created_to must include UTC offsets",
        )
    normalized_from = None if created_from is None else created_from.astimezone(UTC)
    normalized_to = None if created_to is None else created_to.astimezone(UTC)
    if (
        normalized_from is not None
        and normalized_to is not None
        and normalized_from > normalized_to
    ):
        raise HTTPException(
            status_code=422,
            detail="created_from must not be later than created_to",
        )
    return normalized_from, normalized_to


def _parse_cursor(cursor: str | None) -> AgentRunCursor | None:
    try:
        return None if cursor is None else AgentRunCursor.decode(cursor)
    except AgentRunCursorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
