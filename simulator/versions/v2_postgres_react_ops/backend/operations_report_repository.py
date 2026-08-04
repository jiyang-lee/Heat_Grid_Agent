from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from operations_report_api_models import (
    CurrentShiftMemoResponse,
    OperationsReportPage,
    OperationsReportPeriodResponse,
    OperationsReportRunSummary,
    OperationsReportVersionResponse,
    ReportType,
)
from operations_report_errors import StaleOperationsReportVersionError
from operations_report_memo_storage import select_memo, upsert_memo
from operations_report_rows import memo_response
from operations_report_snapshot import build_report_draft
from operations_report_storage import (
    claim_period,
    create_correction_version,
    get_period,
    get_period_by_range,
    insert_official_version,
    latest_version,
    list_periods,
    lock_period,
    mark_overdue_periods,
    mark_failed,
    operation_key_for,
)
from operations_report_writer import (
    DeterministicOperationsReportWriter,
    OperationsReportWriter,
)
from schemas import JsonValue

@dataclass(frozen=True, slots=True)
class PostgresOperationsReportRepository:
    engine: AsyncEngine

    async def ensure_runtime_tables(self) -> None:
        return None

    async def save_current_shift_memo(
        self,
        period_start: datetime,
        period_end: datetime,
        *,
        memo: str,
        updated_by: str,
    ) -> CurrentShiftMemoResponse:
        async with self.engine.begin() as connection:
            return await upsert_memo(
                connection,
                period_start,
                period_end,
                memo=memo,
                updated_by=updated_by,
            )

    async def get_current_shift_memo(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> CurrentShiftMemoResponse:
        async with self.engine.connect() as connection:
            row = await select_memo(connection, period_start, period_end)
        return memo_response(row)

    async def finalize_period(
        self,
        report_type: ReportType,
        period_start: datetime,
        period_end: datetime,
        *,
        generated_at: datetime,
        writer: OperationsReportWriter | None = None,
    ) -> OperationsReportRunSummary:
        active_writer = writer or DeterministicOperationsReportWriter()
        operation_key = operation_key_for(report_type, period_start, period_end)
        async with self.engine.begin() as connection:
            period = await claim_period(connection, report_type, period_start, period_end)
            if period["status"] == "official":
                return OperationsReportRunSummary(
                    checked_count=1,
                    generated_count=0,
                    failed_count=0,
                )
            draft = await build_report_draft(
                connection,
                report_type,
                period_start,
                period_end,
                generated_at=generated_at,
            )
            try:
                content = await active_writer.write_report(draft)
                await insert_official_version(connection, period, content, generated_at)
            except (RuntimeError, ValueError, OSError) as exc:
                await mark_failed(connection, operation_key, str(exc))
                return OperationsReportRunSummary(
                    checked_count=1,
                    generated_count=0,
                    failed_count=1,
                )
        return OperationsReportRunSummary(checked_count=1, generated_count=1, failed_count=0)

    async def mark_overdue_before(self, cutoff: datetime) -> None:
        async with self.engine.begin() as connection:
            await mark_overdue_periods(connection, cutoff)

    async def get_period_by_range(
        self,
        report_type: ReportType,
        period_start: datetime,
        period_end: datetime,
    ) -> OperationsReportPeriodResponse | None:
        async with self.engine.connect() as connection:
            return await get_period_by_range(
                connection,
                report_type,
                period_start,
                period_end,
            )

    async def get_period(self, report_period_id: str) -> OperationsReportPeriodResponse | None:
        async with self.engine.connect() as connection:
            return await get_period(connection, report_period_id)

    async def list_periods(
        self,
        *,
        report_type: ReportType | None = None,
        limit: int = 50,
    ) -> OperationsReportPage:
        async with self.engine.connect() as connection:
            return await list_periods(connection, report_type=report_type, limit=limit)

    async def create_correction(
        self,
        report_period_id: str,
        *,
        expected_latest_version: int,
        content: dict[str, JsonValue],
        reason: str,
        created_by: str,
    ) -> OperationsReportVersionResponse:
        async with self.engine.begin() as connection:
            if await lock_period(connection, report_period_id) is None:
                raise LookupError("report period was not found")
            latest = await latest_version(connection, report_period_id)
            if latest is None or int(latest["version"]) != expected_latest_version:
                raise StaleOperationsReportVersionError()
            return await create_correction_version(
                connection,
                report_period_id,
                latest,
                content=content,
                version=int(latest["version"]) + 1,
                reason=reason,
                created_by=created_by,
            )
