from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from operations_report_api_models import CurrentShiftMemoResponse
from operations_report_rows import memo_response


async def select_memo(
    connection: AsyncConnection,
    period_start: datetime,
    period_end: datetime,
) -> RowMapping | dict[str, str | datetime | None]:
    result = await connection.execute(
        text(
            "SELECT period_start, period_end, timezone, memo, updated_by, updated_at "
            "FROM operations_shift_handover_memos "
            "WHERE period_start = :period_start AND period_end = :period_end"
        ),
        {"period_start": period_start, "period_end": period_end},
    )
    row = result.mappings().one_or_none()
    return row or {
        "period_start": period_start,
        "period_end": period_end,
        "timezone": "Asia/Seoul",
        "memo": "no memo recorded",
        "updated_by": None,
        "updated_at": None,
    }


async def upsert_memo(
    connection: AsyncConnection,
    period_start: datetime,
    period_end: datetime,
    *,
    memo: str,
    updated_by: str,
) -> CurrentShiftMemoResponse:
    result = await connection.execute(
        text(
            "INSERT INTO operations_shift_handover_memos "
            "(period_start, period_end, timezone, memo, updated_by) "
            "VALUES (:period_start, :period_end, 'Asia/Seoul', :memo, :updated_by) "
            "ON CONFLICT (period_start, period_end) DO UPDATE SET "
            "memo = EXCLUDED.memo, updated_by = EXCLUDED.updated_by, updated_at = now() "
            "RETURNING *"
        ),
        {
            "period_start": period_start,
            "period_end": period_end,
            "memo": memo,
            "updated_by": updated_by,
        },
    )
    return memo_response(result.mappings().one())
