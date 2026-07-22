from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from operations_report_api_models import OperationsReportRunSummary, ReportType
from operations_report_repository import PostgresOperationsReportRepository
from operations_report_writer import OperationsReportWriter


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class OperationsReportScheduler:
    repository: PostgresOperationsReportRepository
    writer: OperationsReportWriter | None = None
    lookback_hours: int = 48

    async def run_due_reports(self, *, now: datetime) -> OperationsReportRunSummary:
        await self.repository.mark_overdue_before(
            now.astimezone(UTC) - timedelta(hours=self.lookback_hours)
        )
        due_periods = self._due_periods(now)
        generated = 0
        failed = 0
        for report_type, period_start, period_end in due_periods:
            summary = await self.repository.finalize_period(
                report_type,
                period_start,
                period_end,
                generated_at=now.astimezone(UTC),
                writer=self.writer,
            )
            generated += summary.generated_count
            failed += summary.failed_count
        return OperationsReportRunSummary(
            checked_count=len(due_periods),
            generated_count=generated,
            failed_count=failed,
        )

    def current_shift_window(self, now: datetime) -> tuple[datetime, datetime]:
        now_kst = now.astimezone(KST)
        boundary = _floor_shift_boundary(now_kst)
        next_boundary = _next_shift_boundary(boundary)
        return boundary.astimezone(UTC), next_boundary.astimezone(UTC)

    def _due_periods(self, now: datetime) -> list[tuple[ReportType, datetime, datetime]]:
        now_kst = now.astimezone(KST)
        cursor = _floor_shift_boundary(now_kst - timedelta(hours=self.lookback_hours))
        due: list[tuple[ReportType, datetime, datetime]] = []
        while True:
            next_boundary = _next_shift_boundary(cursor)
            if next_boundary > now_kst:
                break
            due.append(("shift", cursor.astimezone(UTC), next_boundary.astimezone(UTC)))
            cursor = next_boundary
        for daily_start, daily_end in _daily_periods(now_kst, self.lookback_hours):
            due.append(("daily", daily_start.astimezone(UTC), daily_end.astimezone(UTC)))
        return due


def _floor_shift_boundary(now_kst: datetime) -> datetime:
    eight = now_kst.replace(hour=8, minute=0, second=0, microsecond=0)
    twenty = now_kst.replace(hour=20, minute=0, second=0, microsecond=0)
    if now_kst >= twenty:
        return twenty
    if now_kst >= eight:
        return eight
    return twenty - timedelta(days=1)


def _next_shift_boundary(boundary_kst: datetime) -> datetime:
    if boundary_kst.timetz().replace(tzinfo=None) == time(8, 0):
        return boundary_kst.replace(hour=20)
    return (boundary_kst + timedelta(days=1)).replace(hour=8)


def _daily_periods(now_kst: datetime, lookback_hours: int) -> list[tuple[datetime, datetime]]:
    lookback_start = now_kst - timedelta(hours=lookback_hours)
    latest_report_day = _latest_due_daily_report_day(now_kst)
    cursor = lookback_start.date()
    periods: list[tuple[datetime, datetime]] = []
    while cursor <= latest_report_day:
        start = datetime.combine(cursor, time(0, 0), tzinfo=KST)
        end = start + timedelta(days=1)
        due_at = end + timedelta(hours=8)
        if due_at >= lookback_start:
            periods.append((start, end))
        cursor += timedelta(days=1)
    return periods


def _latest_due_daily_report_day(now_kst: datetime) -> date:
    close = now_kst.replace(hour=8, minute=0, second=0, microsecond=0)
    if now_kst < close:
        return (now_kst - timedelta(days=2)).date()
    return (now_kst - timedelta(days=1)).date()
