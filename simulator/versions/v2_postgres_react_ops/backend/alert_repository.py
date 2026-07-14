from __future__ import annotations

from decimal import Decimal
from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.priority.evaluation import ensure_latest_priority_evaluation

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

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
            result.manufacturer_id || '|' || result.substation_id::text
        )::uuid AS alert_id,
        result.source_card_id AS card_id,
        result.evaluation_run_id,
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
     AND q.manufacturer_id = c.manufacturer_id
     AND q.substation_id = c.substation_id
),
inserted AS (
    INSERT INTO ops_alert_queue (
        alert_id,
        card_id,
        evaluation_run_id,
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


async def ensure_alert_queue(engine: AsyncEngine) -> None:
    del engine


async def enqueue_priority_alerts(
    engine: AsyncEngine,
    *,
    stale_after_hours: int = 720,
    model_version: str = "active-priority-contract-v1",
    expected_substations: int = 31,
) -> dict[str, JsonValue]:
    await ensure_latest_priority_evaluation(
        engine,
        stale_after_hours=stale_after_hours,
        model_version=model_version,
        expected_substations=expected_substations,
    )
    await ensure_alert_queue(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), "
                "acked_by = 'snapshot-rollover' "
                "WHERE status = 'open' AND evaluation_run_id IS DISTINCT FROM ("
                "SELECT evaluation_run_id FROM priority_evaluation_runs "
                "WHERE status = 'completed' "
                "ORDER BY is_active DESC, as_of_time DESC, completed_at DESC LIMIT 1"
                ")"
            )
        )
        result = await connection.execute(text(ENQUEUE_ALERTS_SQL))
        inserted = result.mappings().one()
        open_result = await connection.execute(
            text(
                "SELECT count(*) FROM ops_alert_queue WHERE status = 'open' "
                "AND evaluation_run_id = :evaluation_run_id"
            ),
            {"evaluation_run_id": inserted["evaluation_run_id"]},
        )
        total_result = await connection.execute(
            text(
                "SELECT count(*) FROM ops_alert_queue "
                "WHERE evaluation_run_id = :evaluation_run_id"
            ),
            {"evaluation_run_id": inserted["evaluation_run_id"]},
        )
    return {
        "queued_count": int(inserted["queued_count"]),
        "existing_count": int(inserted["existing_count"]),
        "open_count": int(open_result.scalar_one()),
        "total_count": int(total_result.scalar_one()),
        "evaluation_run_id": None
        if inserted["evaluation_run_id"] is None
        else str(inserted["evaluation_run_id"]),
        "as_of_time": None
        if inserted["as_of_time"] is None
        else inserted["as_of_time"].isoformat(),
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
    filters.append(
        "q.evaluation_run_id = ("
        "SELECT evaluation_run_id FROM priority_evaluation_runs "
        "WHERE status = 'completed' "
        "ORDER BY is_active DESC, as_of_time DESC, completed_at DESC LIMIT 1"
        ")"
    )
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(
        "SELECT q.alert_id, q.card_id, q.evaluation_run_id, evaluation.as_of_time, "
        "q.manufacturer_id, q.substation_id, q.priority_rank, q.freshness_status, "
        "q.priority_level, q.priority_score, q.status, q.enqueue_reason, "
        "q.created_at, q.acked_at, q.acked_by "
        "FROM ops_alert_queue q "
        "LEFT JOIN priority_evaluation_runs evaluation "
        "ON evaluation.evaluation_run_id = q.evaluation_run_id "
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
        "WHERE alert_id = :alert_id RETURNING alert_id"
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {"alert_id": alert_id, "acked_by": acked_by},
        )
        row = result.mappings().one_or_none()
    return None if row is None else await get_alert(engine, alert_id)


async def resolve_alert(
    engine: AsyncEngine,
    alert_id: str,
    acked_by: str,
) -> dict[str, JsonValue] | None:
    await ensure_alert_queue(engine)
    query = text(
        "UPDATE ops_alert_queue "
        "SET status = 'resolved', acked_at = now(), acked_by = :acked_by "
        "WHERE alert_id = :alert_id RETURNING alert_id"
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {"alert_id": alert_id, "acked_by": acked_by},
        )
        row = result.mappings().one_or_none()
    return None if row is None else await get_alert(engine, alert_id)


async def get_alert(
    engine: AsyncEngine,
    alert_id: str,
) -> dict[str, JsonValue] | None:
    await ensure_alert_queue(engine)
    query = text(
        "SELECT q.alert_id, q.card_id, q.evaluation_run_id, evaluation.as_of_time, "
        "q.manufacturer_id, q.substation_id, q.priority_rank, q.freshness_status, "
        "q.priority_level, q.priority_score, q.status, q.enqueue_reason, "
        "q.created_at, q.acked_at, q.acked_by "
        "FROM ops_alert_queue q "
        "LEFT JOIN priority_evaluation_runs evaluation "
        "ON evaluation.evaluation_run_id = q.evaluation_run_id "
        "WHERE q.alert_id = :alert_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"alert_id": alert_id})
    row = result.mappings().one_or_none()
    return None if row is None else _alert_from_row(row)


def _alert_from_row(row: RowMapping) -> dict[str, JsonValue]:
    acked_at = row["acked_at"]
    return {
        "alert_id": str(row["alert_id"]),
        "card_id": str(row["card_id"]),
        "evaluation_run_id": None
        if row["evaluation_run_id"] is None
        else str(row["evaluation_run_id"]),
        "as_of_time": None
        if row["as_of_time"] is None
        else row["as_of_time"].isoformat(),
        "manufacturer_id": row["manufacturer_id"],
        "substation_id": row["substation_id"],
        "priority_rank": row["priority_rank"],
        "freshness_status": row["freshness_status"],
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
