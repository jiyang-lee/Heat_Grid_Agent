from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from operations_policy_api_models import CurrentUserResponse
from operations_policy_routes import require_admin
from operations_report_api_models import (
    CurrentShiftMemoRequest,
    CurrentShiftMemoResponse,
    OperationsReportCorrectionRequest,
    OperationsReportPage,
    OperationsReportPeriodResponse,
    OperationsReportRunSummary,
    OperationsReportVersionResponse,
    ReportType,
)
from operations_report_errors import StaleOperationsReportVersionError
from operations_report_repository import PostgresOperationsReportRepository
from operations_report_scheduler import OperationsReportScheduler


def make_operations_report_router(
    repository: PostgresOperationsReportRepository,
    scheduler: OperationsReportScheduler,
    *,
    clock: Callable[[], datetime] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/operations-reports", tags=["operations-reports"])
    active_clock = clock or _utc_now

    @router.get("/current-shift", response_model=CurrentShiftMemoResponse)
    async def current_shift_memo() -> CurrentShiftMemoResponse:
        period_start, period_end = scheduler.current_shift_window(active_clock())
        return await repository.get_current_shift_memo(period_start, period_end)

    @router.put("/current-shift/memo", response_model=CurrentShiftMemoResponse)
    async def update_current_shift_memo(
        request: CurrentShiftMemoRequest,
        admin: Annotated[CurrentUserResponse, Depends(require_admin)],
    ) -> CurrentShiftMemoResponse:
        period_start, period_end = scheduler.current_shift_window(active_clock())
        return await repository.save_current_shift_memo(
            period_start,
            period_end,
            memo=request.memo,
            updated_by=admin.user_id,
        )

    @router.post("/run-due", response_model=OperationsReportRunSummary)
    async def run_due_reports(
        _admin: Annotated[CurrentUserResponse, Depends(require_admin)],
    ) -> OperationsReportRunSummary:
        return await scheduler.run_due_reports(now=active_clock())

    @router.get("", response_model=OperationsReportPage)
    async def list_operations_reports(
        report_type: ReportType | None = None,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> OperationsReportPage:
        return await repository.list_periods(report_type=report_type, limit=limit)

    @router.get("/{report_period_id}", response_model=OperationsReportPeriodResponse)
    async def get_operations_report(report_period_id: UUID) -> OperationsReportPeriodResponse:
        report = await repository.get_period(str(report_period_id))
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report period was not found")
        return report

    @router.post(
        "/{report_period_id}/corrections",
        response_model=OperationsReportVersionResponse,
    )
    async def create_operations_report_correction(
        report_period_id: UUID,
        request: OperationsReportCorrectionRequest,
        admin: Annotated[CurrentUserResponse, Depends(require_admin)],
    ) -> OperationsReportVersionResponse:
        try:
            return await repository.create_correction(
                str(report_period_id),
                expected_latest_version=request.expected_latest_version,
                content=request.content,
                reason=request.reason,
                created_by=admin.user_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="report period was not found",
            ) from exc
        except StaleOperationsReportVersionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="operations report version is stale",
            ) from exc

    return router


def _utc_now() -> datetime:
    return datetime.now(UTC)
