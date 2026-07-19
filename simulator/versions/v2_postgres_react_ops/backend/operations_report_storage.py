from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from operations_report_api_models import (
    OperationsReportPage,
    OperationsReportPeriodResponse,
    OperationsReportVersionResponse,
    ReportType,
)
from operations_report_rows import (
    content_hash,
    json_text,
    period_response,
    version_response,
)
from schemas import JsonValue


async def claim_period(
    connection: AsyncConnection,
    report_type: ReportType,
    period_start: datetime,
    period_end: datetime,
) -> RowMapping:
    operation_key = operation_key_for(report_type, period_start, period_end)
    await connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:operation_key))"),
        {"operation_key": operation_key},
    )
    result = await connection.execute(
        text(
            "INSERT INTO operations_report_periods "
            "(report_type, period_start, period_end, timezone, status, operation_key) "
            "VALUES (:report_type, :period_start, :period_end, 'Asia/Seoul', "
            "'generating', :operation_key) "
            "ON CONFLICT (operation_key) DO UPDATE SET "
            "status = CASE WHEN operations_report_periods.status IN "
            "('pending', 'generating', 'failed', 'overdue') THEN 'generating' "
            "ELSE operations_report_periods.status END, "
            "error = CASE WHEN operations_report_periods.status IN "
            "('pending', 'generating', 'failed', 'overdue') THEN NULL "
            "ELSE operations_report_periods.error END, updated_at = now() "
            "RETURNING *"
        ),
        {
            "report_type": report_type,
            "period_start": period_start,
            "period_end": period_end,
            "operation_key": operation_key,
        },
    )
    return result.mappings().one()


async def mark_failed(
    connection: AsyncConnection,
    operation_key: str,
    error: str,
) -> None:
    await connection.execute(
        text(
            "UPDATE operations_report_periods SET status = 'failed', "
            "error = :error, updated_at = now() WHERE operation_key = :operation_key "
            "AND status <> 'official'"
        ),
        {"operation_key": operation_key, "error": error[:1000]},
    )


async def mark_overdue_periods(connection: AsyncConnection, cutoff: datetime) -> None:
    await connection.execute(
        text(
            "UPDATE operations_report_periods SET status = 'overdue', updated_at = now() "
            "WHERE status IN ('pending', 'generating', 'failed') AND period_end < :cutoff"
        ),
        {"cutoff": cutoff},
    )


async def insert_official_version(
    connection: AsyncConnection,
    period: RowMapping,
    content: dict[str, JsonValue],
    generated_at: datetime,
) -> None:
    report_period_id = str(period["report_period_id"])
    if await latest_version(connection, report_period_id) is not None:
        await set_period_official(connection, report_period_id)
        return
    await connection.execute(
        text(
            "INSERT INTO operations_report_versions "
            "(report_period_id, version, official, content, content_hash, "
            "data_quality_caveats, generated_by, generated_at) "
            "VALUES (:report_period_id, 1, true, CAST(:content AS jsonb), "
            ":content_hash, CAST(:caveats AS jsonb), 'system', :generated_at)"
        ),
        {
            "report_period_id": report_period_id,
            "content": json_text(content),
            "content_hash": content_hash(content),
            "caveats": json_text(content.get("data_quality_caveats", [])),
            "generated_at": generated_at,
        },
    )
    await set_period_official(connection, report_period_id)


async def set_period_official(connection: AsyncConnection, report_period_id: str) -> None:
    await connection.execute(
        text(
            "UPDATE operations_report_periods SET status = 'official', error = NULL, "
            "updated_at = now() WHERE report_period_id = :report_period_id"
        ),
        {"report_period_id": report_period_id},
    )


async def get_period_by_range(
    connection: AsyncConnection,
    report_type: ReportType,
    period_start: datetime,
    period_end: datetime,
) -> OperationsReportPeriodResponse | None:
    result = await connection.execute(
        text(
            "SELECT * FROM operations_report_periods WHERE report_type = :report_type "
            "AND period_start = :period_start AND period_end = :period_end"
        ),
        {"report_type": report_type, "period_start": period_start, "period_end": period_end},
    )
    period = result.mappings().one_or_none()
    return None if period is None else await period_response(connection, period)


async def get_period(
    connection: AsyncConnection,
    report_period_id: str,
) -> OperationsReportPeriodResponse | None:
    result = await connection.execute(
        text("SELECT * FROM operations_report_periods WHERE report_period_id = CAST(:id AS uuid)"),
        {"id": report_period_id},
    )
    period = result.mappings().one_or_none()
    return None if period is None else await period_response(connection, period)


async def list_periods(
    connection: AsyncConnection,
    *,
    report_type: ReportType | None,
    limit: int,
) -> OperationsReportPage:
    params: dict[str, str | int] = {"limit": min(max(limit, 1), 100)}
    where = "TRUE"
    if report_type is not None:
        where = "report_type = :report_type"
        params["report_type"] = report_type
    result = await connection.execute(
        text(
            f"SELECT * FROM operations_report_periods WHERE {where} "
            "ORDER BY period_end DESC, created_at DESC LIMIT :limit"
        ),
        params,
    )
    items = [await period_response(connection, row) for row in result.mappings().all()]
    return OperationsReportPage(items=tuple(items))


async def create_correction_version(
    connection: AsyncConnection,
    report_period_id: str,
    latest: RowMapping,
    *,
    content: dict[str, JsonValue],
    version: int,
    reason: str,
    created_by: str,
) -> OperationsReportVersionResponse:
    inserted = await connection.execute(
        text(
            "INSERT INTO operations_report_versions "
            "(report_period_id, version, source_report_version_id, official, content, "
            "content_hash, data_quality_caveats, generated_by) "
            "VALUES (CAST(:report_period_id AS uuid), :version, "
            ":source_report_version_id, false, CAST(:content AS jsonb), "
            ":content_hash, CAST(:caveats AS jsonb), :created_by) RETURNING *"
        ),
        {
            "report_period_id": report_period_id,
            "version": version,
            "source_report_version_id": latest["report_version_id"],
            "content": json_text(content),
            "content_hash": content_hash(content),
            "caveats": json_text(content.get("data_quality_caveats", [])),
            "created_by": created_by,
        },
    )
    row = inserted.mappings().one()
    await connection.execute(
        text(
            "INSERT INTO operations_report_corrections "
            "(source_report_version_id, corrected_report_version_id, reason, created_by) "
            "VALUES (:source_report_version_id, :corrected_report_version_id, "
            ":reason, :created_by)"
        ),
        {
            "source_report_version_id": latest["report_version_id"],
            "corrected_report_version_id": row["report_version_id"],
            "reason": reason,
            "created_by": created_by,
        },
    )
    return version_response(row, correction_reason=reason)


async def lock_period(connection: AsyncConnection, report_period_id: str) -> RowMapping | None:
    result = await connection.execute(
        text(
            "SELECT * FROM operations_report_periods "
            "WHERE report_period_id = CAST(:report_period_id AS uuid) FOR UPDATE"
        ),
        {"report_period_id": report_period_id},
    )
    return result.mappings().one_or_none()


async def latest_version(connection: AsyncConnection, report_period_id: str) -> RowMapping | None:
    result = await connection.execute(
        text(
            "SELECT * FROM operations_report_versions "
            "WHERE report_period_id = CAST(:report_period_id AS uuid) "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"report_period_id": report_period_id},
    )
    return result.mappings().one_or_none()


def operation_key_for(report_type: ReportType, period_start: datetime, period_end: datetime) -> str:
    return f"operations-report:{report_type}:{period_start.isoformat()}:{period_end.isoformat()}"
