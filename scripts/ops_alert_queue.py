from __future__ import annotations

from typing import Final

import asyncpg

ALERT_LEVELS: Final = ("urgent", "high")

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
SELECT count(*) FROM inserted
"""


async def ensure_alert_queue(conn: asyncpg.Connection) -> None:
    await conn.execute(ALERT_QUEUE_DDL)


async def source_table_status(
    conn: asyncpg.Connection,
    table: str,
) -> dict[str, int | str | None]:
    exists = await conn.fetchval(
        "SELECT to_regclass($1) IS NOT NULL",
        f"public.{table}",
    )
    if not exists:
        return {"status": "missing", "row_count": None}
    row_count = int(await conn.fetchval(f"SELECT count(*) FROM {table}"))
    status = "available" if row_count > 0 else "empty"
    return {"status": status, "row_count": row_count}


async def collect_source_diagnostics(
    conn: asyncpg.Connection,
    agent_rows: int,
    windows_rows: int,
) -> dict[str, object]:
    sensor_readings = await source_table_status(conn, "sensor_readings")
    window_features = await source_table_status(conn, "window_features")
    raw_ready = (
        sensor_readings["status"] == "available"
        and window_features["status"] == "available"
    )
    return {
        "fallback_source": "raw_db" if raw_ready else "csv_windows",
        "sources": {
            "sensor_readings": sensor_readings,
            "window_features": window_features,
            "agent_priority_card_csv": {
                "status": "available" if agent_rows > 0 else "empty",
                "row_count": agent_rows,
            },
            "windows_csv": {
                "status": "available" if windows_rows > 0 else "empty",
                "row_count": windows_rows,
            },
        },
    }


async def enqueue_priority_alerts(conn: asyncpg.Connection) -> dict[str, int]:
    await ensure_alert_queue(conn)
    queued_count = int(await conn.fetchval(ENQUEUE_ALERTS_SQL))
    open_count = int(
        await conn.fetchval("SELECT count(*) FROM ops_alert_queue WHERE status = 'open'")
    )
    total_count = int(await conn.fetchval("SELECT count(*) FROM ops_alert_queue"))
    return {
        "queued_count": queued_count,
        "open_count": open_count,
        "total_count": total_count,
    }
