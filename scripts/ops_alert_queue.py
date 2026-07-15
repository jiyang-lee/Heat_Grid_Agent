from __future__ import annotations

from typing import Final

import asyncpg

ALERT_LEVELS: Final = ("urgent", "high")

ENQUEUE_ALERTS_SQL: Final = """
WITH latest AS (
    SELECT evaluation_run_id, as_of_time
    FROM priority_evaluation_runs
    WHERE status = 'completed'
    ORDER BY is_active DESC, as_of_time DESC, completed_at DESC
    LIMIT 1
),
candidates AS (
    SELECT
        md5(
            'ops_alert|' || result.evaluation_run_id::text || '|' ||
            result.substation_uid::text
        )::uuid AS alert_id,
        result.source_card_id AS card_id,
        result.evaluation_run_id,
        result.substation_uid,
        result.manufacturer_id,
        result.substation_id,
        result.priority_rank,
        result.freshness_status,
        lower(result.priority_level) AS priority_level,
        result.priority_score,
        'evaluation_run_id=' || result.evaluation_run_id::text ||
            ';priority_level=' || lower(result.priority_level) AS enqueue_reason
    FROM priority_evaluation_results result
    JOIN latest ON latest.evaluation_run_id = result.evaluation_run_id
    WHERE result.freshness_status = 'fresh'
      AND result.rank_included
      AND result.source_card_id IS NOT NULL
      AND lower(result.priority_level) IN ('urgent', 'high')
),
existing AS (
    SELECT count(*) AS existing_count
    FROM candidates c
    JOIN ops_alert_queue q
      ON q.evaluation_run_id = c.evaluation_run_id
     AND q.substation_uid = c.substation_uid
),
inserted AS (
    INSERT INTO ops_alert_queue (
        alert_id,
        card_id,
        evaluation_run_id,
        substation_uid,
        manufacturer_id,
        substation_id,
        priority_rank,
        freshness_status,
        priority_level,
        priority_score,
        enqueue_reason
    )
    SELECT * FROM candidates
    ON CONFLICT DO NOTHING
    RETURNING 1
)
SELECT
    (SELECT count(*) FROM inserted) AS queued_count,
    (SELECT existing_count FROM existing) AS existing_count,
    (SELECT evaluation_run_id FROM latest) AS evaluation_run_id,
    (SELECT as_of_time FROM latest) AS as_of_time
"""


async def ensure_alert_queue(conn: asyncpg.Connection) -> None:
    exists = await conn.fetchval("SELECT to_regclass('public.ops_alert_queue') IS NOT NULL")
    if not exists:
        raise RuntimeError("database migrations have not created ops_alert_queue")


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
    window_features = await source_table_status(conn, "model_feature_snapshots")
    raw_ready = (
        sensor_readings["status"] == "available"
        and window_features["status"] == "available"
    )
    return {
        "fallback_source": "raw_db" if raw_ready else "csv_windows",
        "sources": {
            "sensor_readings": sensor_readings,
            "model_feature_snapshots": window_features,
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


async def enqueue_priority_alerts(conn: asyncpg.Connection) -> dict[str, int | str | None]:
    await ensure_alert_queue(conn)
    await conn.execute(
        "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), "
        "acked_by = 'snapshot-rollover' "
        "WHERE status = 'open' AND evaluation_run_id IS DISTINCT FROM ("
        "SELECT evaluation_run_id FROM priority_evaluation_runs "
        "WHERE status = 'completed' "
        "ORDER BY is_active DESC, as_of_time DESC, completed_at DESC LIMIT 1"
        ")"
    )
    inserted = await conn.fetchrow(ENQUEUE_ALERTS_SQL)
    if inserted is None:
        queued_count = 0
        existing_count = 0
    else:
        queued_count = int(inserted["queued_count"])
        existing_count = int(inserted["existing_count"])
    evaluation_run_id = None if inserted is None else inserted["evaluation_run_id"]
    open_count = int(
        await conn.fetchval(
            "SELECT count(*) FROM ops_alert_queue "
            "WHERE status = 'open' AND evaluation_run_id = $1",
            evaluation_run_id,
        )
    )
    total_count = int(
        await conn.fetchval(
            "SELECT count(*) FROM ops_alert_queue WHERE evaluation_run_id = $1",
            evaluation_run_id,
        )
    )
    return {
        "queued_count": queued_count,
        "existing_count": existing_count,
        "open_count": open_count,
        "total_count": total_count,
        "evaluation_run_id": None
        if evaluation_run_id is None
        else str(evaluation_run_id),
        "as_of_time": None
        if inserted is None or inserted["as_of_time"] is None
        else inserted["as_of_time"].isoformat(),
    }
