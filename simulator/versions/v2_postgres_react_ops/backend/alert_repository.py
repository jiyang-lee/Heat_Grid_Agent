from __future__ import annotations

from decimal import Decimal
from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.priority.evaluation import ensure_latest_priority_evaluation

try:
    from .alert_episode_repository import (
        consume_latest_evaluation,
        ensure_alert_episode_tables,
        mark_alert_read,
    )
except ImportError:
    from alert_episode_repository import (
        consume_latest_evaluation,
        ensure_alert_episode_tables,
        mark_alert_read,
    )

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

ALERT_QUEUE_DDL: Final = """
CREATE TABLE IF NOT EXISTS ops_alert_queue (
    alert_id uuid PRIMARY KEY,
    card_id uuid NOT NULL REFERENCES priority_cards(card_id) ON DELETE CASCADE,
    evaluation_run_id uuid,
    substation_uid uuid NOT NULL REFERENCES substations(substation_uid),
    manufacturer_id text,
    substation_id integer,
    priority_rank integer,
    freshness_status text,
    priority_level text NOT NULL CHECK (priority_level IN ('urgent', 'high')),
    priority_score double precision,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acked', 'resolved')),
    enqueue_reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    acked_at timestamptz,
    acked_by text
)
"""

ALERT_QUEUE_TYPE_MIGRATION: Final = """
ALTER TABLE ops_alert_queue
ALTER COLUMN priority_score TYPE double precision
USING priority_score::double precision
"""

ALERT_QUEUE_COMPATIBILITY_DDL: Final = (
    "ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS evaluation_run_id uuid",
    "ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS substation_uid uuid",
    "ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS manufacturer_id text",
    "ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS substation_id integer",
    "ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS priority_rank integer",
    "ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS freshness_status text",
    "ALTER TABLE ops_alert_queue DROP CONSTRAINT IF EXISTS ops_alert_queue_card_id_key",
    "CREATE UNIQUE INDEX IF NOT EXISTS ops_alert_queue_evaluation_substation_uidx "
    "ON ops_alert_queue(evaluation_run_id, substation_uid) "
    "WHERE evaluation_run_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ops_alert_queue_evaluation_idx "
    "ON ops_alert_queue(evaluation_run_id, status, priority_score DESC)",
)

ALERT_QUEUE_STATUS_MIGRATION: Final = """
ALTER TABLE ops_alert_queue
DROP CONSTRAINT IF EXISTS ops_alert_queue_status_check
"""

ALERT_QUEUE_STATUS_CHECK: Final = """
ALTER TABLE ops_alert_queue
ADD CONSTRAINT ops_alert_queue_status_check
CHECK (status IN ('open', 'acked', 'resolved'))
"""

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


async def ensure_alert_queue(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(ALERT_QUEUE_DDL))
        await connection.execute(text(ALERT_QUEUE_TYPE_MIGRATION))
        for statement in ALERT_QUEUE_COMPATIBILITY_DDL:
            await connection.execute(text(statement))
        await connection.execute(text(ALERT_QUEUE_STATUS_MIGRATION))
        await connection.execute(text(ALERT_QUEUE_STATUS_CHECK))
    await ensure_alert_episode_tables(engine)


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
    delta = await consume_latest_evaluation(engine)
    async with engine.connect() as connection:
        latest = await connection.execute(
            text(
                "SELECT evaluation_run_id, as_of_time FROM priority_evaluation_runs "
                "WHERE stream_key = 'default' AND status = 'completed' "
                "ORDER BY is_active DESC, as_of_time DESC, completed_at DESC LIMIT 1"
            )
        )
        inserted = latest.mappings().one()
        open_result = await connection.execute(
            text(
                "SELECT count(*) FROM ops_alert_queue WHERE status = 'open' "
                "AND episode_id IS NOT NULL"
            )
        )
        total_result = await connection.execute(
            text("SELECT count(*) FROM ops_alert_queue WHERE episode_id IS NOT NULL")
        )
    return {
        "queued_count": int(delta["opened"]),
        "existing_count": int(delta["skipped"]),
        "open_count": int(open_result.scalar_one()),
        "total_count": int(total_result.scalar_one()),
        "evaluation_run_id": None
        if inserted["evaluation_run_id"] is None
        else str(inserted["evaluation_run_id"]),
        "as_of_time": None
        if inserted["as_of_time"] is None
        else inserted["as_of_time"].isoformat(),
    }


async def materialize_scenario_alert(
    engine: AsyncEngine,
    *,
    scenario_alert_id: str,
    substation_id: int,
    priority_level: str,
    priority_score: float,
    priority_rank: int,
    reason: str,
) -> dict[str, JsonValue] | None:
    await ensure_alert_queue(engine)
    existing_query = text(
        "UPDATE ops_alert_queue SET "
        " freshness_status = 'fresh', priority_level = :priority_level,"
        " priority_score = :priority_score, priority_rank = :priority_rank,"
        " status = 'open', enqueue_reason = :reason, acked_at = NULL, acked_by = NULL"
        " WHERE alert_id = md5('scenario-alert|' || :scenario_alert_id)::uuid"
        " RETURNING alert_id"
    )
    query = text(
        "WITH latest_evaluation AS ("
        " SELECT evaluation_run_id FROM priority_evaluation_runs"
        " WHERE status = 'completed'"
        " ORDER BY is_active DESC, as_of_time DESC, completed_at DESC LIMIT 1"
        "), selected_card AS ("
        " SELECT pc.card_id, s.substation_uid, s.manufacturer_id, s.substation_id, pd.priority_score"
        " FROM priority_cards pc"
        " JOIN priority_decisions pd ON pd.priority_decision_id = pc.priority_decision_id"
        " JOIN windows w ON w.window_id = pd.window_id"
        " JOIN substations s ON s.substation_uid = w.substation_uid"
        " WHERE s.substation_id = :substation_id"
        " ORDER BY w.window_end DESC, pc.created_at DESC LIMIT 1"
        "), upserted AS ("
        " INSERT INTO ops_alert_queue ("
        "  alert_id, card_id, evaluation_run_id, substation_uid, manufacturer_id, substation_id,"
        "  freshness_status, priority_level, priority_score, priority_rank, status, enqueue_reason"
        " )"
        " SELECT md5('scenario-alert|' || :scenario_alert_id)::uuid, card.card_id,"
        "  evaluation.evaluation_run_id, card.substation_uid, card.manufacturer_id, card.substation_id,"
        "  'fresh', :priority_level, :priority_score, :priority_rank, 'open', :reason"
        " FROM selected_card card CROSS JOIN latest_evaluation evaluation"
        " ON CONFLICT (evaluation_run_id, substation_uid)"
        " WHERE evaluation_run_id IS NOT NULL DO UPDATE SET"
        "  card_id = EXCLUDED.card_id, evaluation_run_id = EXCLUDED.evaluation_run_id,"
        "  substation_uid = EXCLUDED.substation_uid, manufacturer_id = EXCLUDED.manufacturer_id,"
        "  substation_id = EXCLUDED.substation_id,"
        "  freshness_status = EXCLUDED.freshness_status, priority_level = EXCLUDED.priority_level,"
        "  priority_score = EXCLUDED.priority_score, priority_rank = EXCLUDED.priority_rank, status = 'open',"
        "  enqueue_reason = EXCLUDED.enqueue_reason, acked_at = NULL, acked_by = NULL"
        " RETURNING alert_id"
        ") SELECT alert_id FROM upserted"
    )
    async with engine.begin() as connection:
        params = {
            "scenario_alert_id": scenario_alert_id,
            "substation_id": substation_id,
            "priority_level": priority_level,
            "priority_score": priority_score,
            "priority_rank": priority_rank,
            "reason": reason,
        }
        existing = await connection.execute(existing_query, params)
        row = existing.mappings().one_or_none()
        if row is None:
            result = await connection.execute(
                query,
                params,
            )
            row = result.mappings().one_or_none()
    if row is None:
        return None
    return await get_alert(engine, str(row["alert_id"]))


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
    filters.append("q.episode_id IS NOT NULL")
    # 과거 batch 평가로 만들어진 학습용 알림은 보존하되, 운영 화면에는 현재 리플레이 실행에서
    # 생성된 알림만 노출한다. scenario-alerts도 최신 replay 평가를 참조하므로 함께 포함된다.
    filters.append("evaluation.source_kind = 'replay'")
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(
        "SELECT q.alert_id, q.card_id, q.evaluation_run_id, evaluation.as_of_time, "
        "q.manufacturer_id, q.substation_id, q.priority_rank, q.freshness_status, "
        "q.priority_level, q.priority_score, q.status, q.enqueue_reason, "
        "q.created_at, q.acked_at, q.acked_by, q.episode_id, q.read_at, q.read_by "
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
    await mark_alert_read(engine, alert_id=alert_id, read_by=acked_by)
    return await get_alert(engine, alert_id)


async def resolve_alert(
    engine: AsyncEngine,
    alert_id: str,
    acked_by: str,
) -> dict[str, JsonValue] | None:
    del engine, alert_id, acked_by
    raise RuntimeError("manual alert resolution is disabled")


async def get_alert(
    engine: AsyncEngine,
    alert_id: str,
) -> dict[str, JsonValue] | None:
    await ensure_alert_queue(engine)
    query = text(
        "SELECT q.alert_id, q.card_id, q.evaluation_run_id, evaluation.as_of_time, "
        "q.manufacturer_id, q.substation_id, q.priority_rank, q.freshness_status, "
        "q.priority_level, q.priority_score, q.status, q.enqueue_reason, "
        "q.created_at, q.acked_at, q.acked_by, q.episode_id, q.read_at, q.read_by "
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
        "episode_id": None if row["episode_id"] is None else str(row["episode_id"]),
        "read_at": None if row["read_at"] is None else row["read_at"].isoformat(),
        "read_by": row["read_by"],
    }


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value
