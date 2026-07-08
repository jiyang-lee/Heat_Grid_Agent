from __future__ import annotations

from decimal import Decimal
from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

ALERT_QUEUE_DDL: Final = """
CREATE TABLE IF NOT EXISTS ops_alert_queue (
    alert_id uuid PRIMARY KEY,
    card_id uuid NOT NULL UNIQUE REFERENCES priority_cards(card_id) ON DELETE CASCADE,
    priority_level text NOT NULL CHECK (priority_level IN ('urgent', 'high')),
    priority_score numeric,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acked')),
    enqueue_reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    acked_at timestamptz,
    acked_by text
)
"""

ENQUEUE_ALERTS_SQL: Final = """
WITH inserted AS (
    INSERT INTO ops_alert_queue (
        alert_id,
        card_id,
        priority_level,
        priority_score,
        enqueue_reason
    )
    SELECT
        md5('ops_alert|' || pc.card_id::text)::uuid,
        pc.card_id,
        lower(pd.priority_level),
        pd.priority_score,
        'priority_level=' || lower(pd.priority_level)
    FROM priority_cards pc
    JOIN priority_decisions pd
    ON pd.priority_decision_id = pc.priority_decision_id
    WHERE lower(pd.priority_level) IN ('urgent', 'high')
    ON CONFLICT (card_id) DO NOTHING
    RETURNING 1
)
SELECT count(*) AS queued_count FROM inserted
"""


async def ensure_alert_queue(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(ALERT_QUEUE_DDL))


async def enqueue_priority_alerts(engine: AsyncEngine) -> dict[str, JsonValue]:
    await ensure_alert_queue(engine)
    async with engine.begin() as connection:
        result = await connection.execute(text(ENQUEUE_ALERTS_SQL))
        queued_count = int(result.scalar_one())
        open_result = await connection.execute(
            text("SELECT count(*) FROM ops_alert_queue WHERE status = 'open'")
        )
        total_result = await connection.execute(text("SELECT count(*) FROM ops_alert_queue"))
    return {
        "queued_count": queued_count,
        "open_count": int(open_result.scalar_one()),
        "total_count": int(total_result.scalar_one()),
    }


async def list_alerts(
    engine: AsyncEngine,
    status: str,
    priority_level: str | None,
) -> list[dict[str, JsonValue]]:
    await ensure_alert_queue(engine)
    filters: list[str] = []
    params: dict[str, JsonValue] = {}
    if status != "all":
        filters.append("q.status = :status")
        params["status"] = status
    if priority_level is not None:
        filters.append("q.priority_level = :priority_level")
        params["priority_level"] = priority_level
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(
        "SELECT q.alert_id, q.card_id, q.priority_level, q.priority_score, "
        "q.status, q.enqueue_reason, q.created_at, q.acked_at, q.acked_by "
        "FROM ops_alert_queue q "
        f"{where_sql} "
        "ORDER BY q.created_at DESC, q.priority_score DESC NULLS LAST, q.alert_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, params)
    return [_alert_from_row(row) for row in result.mappings().all()]


async def ack_alert(
    engine: AsyncEngine,
    alert_id: str,
    acked_by: str,
) -> dict[str, JsonValue] | None:
    await ensure_alert_queue(engine)
    query = text(
        "UPDATE ops_alert_queue "
        "SET status = 'acked', acked_at = now(), acked_by = :acked_by "
        "WHERE alert_id = :alert_id "
        "RETURNING alert_id, card_id, priority_level, priority_score, status, "
        "enqueue_reason, created_at, acked_at, acked_by"
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {"alert_id": alert_id, "acked_by": acked_by},
        )
        row = result.mappings().one_or_none()
    return None if row is None else _alert_from_row(row)


def _alert_from_row(row: RowMapping) -> dict[str, JsonValue]:
    acked_at = row["acked_at"]
    return {
        "alert_id": str(row["alert_id"]),
        "card_id": str(row["card_id"]),
        "priority_level": row["priority_level"],
        "priority_score": _json_scalar(row["priority_score"]),
        "status": row["status"],
        "enqueue_reason": row["enqueue_reason"],
        "created_at": row["created_at"].isoformat(),
        "acked_at": None if acked_at is None else acked_at.isoformat(),
        "acked_by": row["acked_by"],
    }


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value
