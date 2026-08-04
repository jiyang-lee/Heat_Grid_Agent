from __future__ import annotations

from datetime import datetime
from hashlib import sha256

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from operations_report_api_models import (
    CurrentShiftMemoResponse,
    OperationsReportPeriodResponse,
    OperationsReportVersionResponse,
)
from schemas import JsonValue


async def period_response(
    connection: AsyncConnection,
    period: RowMapping,
) -> OperationsReportPeriodResponse:
    versions = await connection.execute(
        text(
            "SELECT versions.*, corrections.reason AS correction_reason "
            "FROM operations_report_versions versions "
            "LEFT JOIN operations_report_corrections corrections "
            "ON corrections.corrected_report_version_id = versions.report_version_id "
            "WHERE versions.report_period_id = :report_period_id "
            "ORDER BY versions.version"
        ),
        {"report_period_id": period["report_period_id"]},
    )
    return OperationsReportPeriodResponse(
        report_period_id=str(period["report_period_id"]),
        report_type=period["report_type"],
        period_start=period["period_start"],
        period_end=period["period_end"],
        timezone=period["timezone"],
        status=period["status"],
        operation_key=period["operation_key"],
        error=period["error"],
        created_at=period["created_at"],
        updated_at=period["updated_at"],
        versions=tuple(version_response(row) for row in versions.mappings().all()),
    )


def version_response(
    row: RowMapping,
    *,
    correction_reason: str | None = None,
) -> OperationsReportVersionResponse:
    return OperationsReportVersionResponse(
        report_version_id=str(row["report_version_id"]),
        version=int(row["version"]),
        source_report_version_id=None
        if row["source_report_version_id"] is None
        else str(row["source_report_version_id"]),
        official=bool(row["official"]),
        content=row_json_object(row["content"]),
        content_hash=row["content_hash"],
        data_quality_caveats=tuple(row_json_array(row["data_quality_caveats"])),
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
        correction_reason=correction_reason or row.get("correction_reason"),
    )


def memo_response(row: RowMapping | dict[str, str | datetime | None]) -> CurrentShiftMemoResponse:
    period_start = row["period_start"]
    period_end = row["period_end"]
    memo = row["memo"]
    updated_by = row["updated_by"]
    updated_at = row["updated_at"]
    assert isinstance(period_start, datetime)
    assert isinstance(period_end, datetime)
    assert isinstance(memo, str)
    assert updated_by is None or isinstance(updated_by, str)
    assert updated_at is None or isinstance(updated_at, datetime)
    return CurrentShiftMemoResponse(
        period_start=period_start,
        period_end=period_end,
        timezone="Asia/Seoul",
        memo=memo,
        updated_by=updated_by,
        updated_at=updated_at,
    )


def row_json_object(value: JsonValue | str) -> dict[str, JsonValue]:
    loaded = orjson.loads(value) if isinstance(value, str) else value
    return loaded if isinstance(loaded, dict) else {}


def row_json_array(value: JsonValue | str) -> list[str]:
    loaded = orjson.loads(value) if isinstance(value, str) else value
    return [str(item) for item in loaded] if isinstance(loaded, list) else []


def json_text(value: JsonValue) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def content_hash(content: dict[str, JsonValue]) -> str:
    return sha256(orjson.dumps(content, option=orjson.OPT_SORT_KEYS)).hexdigest()
