from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

REQUIRED_EPISODE_TABLES: Final = (
    "anomaly_episodes",
    "anomaly_episode_consumptions",
    "anomaly_episode_events",
    "preventive_projections",
)


class EpisodeSchemaUnavailableError(RuntimeError):
    pass


async def ensure_alert_episode_tables(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN ("
                "'anomaly_episodes', 'anomaly_episode_consumptions', "
                "'anomaly_episode_events', 'preventive_projections')"
            )
        )
    found = {str(row["table_name"]) for row in result.mappings().all()}
    missing = sorted(set(REQUIRED_EPISODE_TABLES) - found)
    if missing:
        joined = ", ".join(missing)
        raise EpisodeSchemaUnavailableError(
            f"migration 016 is required for alert episodes: {joined}"
        )


async def list_preventive_candidates(
    engine: AsyncEngine,
    *,
    stream_key: str = "default",
) -> list[dict[str, JsonValue]]:
    await ensure_alert_episode_tables(engine)
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT preventive_projection_id, stream_key, manufacturer_id, substation_id, "
                "evaluation_run_id, priority_level, priority_score, freshness_status, "
                "CAST(reason AS text) AS reason, projected_at, expires_at "
                "FROM preventive_projections WHERE stream_key = :stream_key "
                "ORDER BY projected_at DESC, priority_score DESC NULLS LAST"
            ),
            {"stream_key": stream_key},
        )
    return [_preventive_from_row(row) for row in result.mappings().all()]


async def list_asset_telemetry(
    engine: AsyncEngine,
    *,
    manufacturer_id: str,
    substation_id: int,
    stream_key: str = "default",
    limit: int = 72,
) -> dict[str, JsonValue]:
    replay_mode = stream_key.startswith("replay:")
    source_filter = (
        "AND source_file = :source_file"
        if replay_mode
        else "AND (source_file IS NULL OR source_file NOT LIKE 'synthetic-replay:%')"
    )
    params: dict[str, JsonValue] = {
        "manufacturer_id": manufacturer_id,
        "substation_id": substation_id,
        "limit": max(1, min(limit, 720)),
    }
    if replay_mode:
        params["source_file"] = f"synthetic-replay:{stream_key.removeprefix('replay:')}"
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT reading_time, source_sensor, sensor_value, source_file, "
                "clock_timestamp() AS receipt_time FROM sensor_readings "
                "WHERE manufacturer_id = :manufacturer_id "
                f"AND substation_id = :substation_id {source_filter} "
                "ORDER BY reading_time DESC, source_sensor LIMIT :limit"
            ),
            params,
        )
        rows = result.mappings().all()
        freshness_minutes = await connection.scalar(
            text(
                "SELECT freshness_threshold_minutes FROM operations_policy "
                "WHERE policy_key = 'default'"
            )
        )
    points: list[JsonValue] = [_telemetry_from_row(row) for row in rows]
    if not rows:
        return {
            "stream_key": stream_key,
            "trust_state": "missing",
            "receipt_time": None,
            "latest_reading_time": None,
            "data_age_seconds": None,
            "points": points,
        }
    latest = rows[0]["reading_time"]
    receipt_time = rows[0]["receipt_time"]
    reference_time = latest if replay_mode else receipt_time
    data_age = max(0.0, (reference_time - latest).total_seconds())
    freshness_seconds = int(freshness_minutes or 30) * 60
    trust_state = "verified" if replay_mode or data_age <= freshness_seconds else "stale"
    return {
        "stream_key": stream_key,
        "trust_state": trust_state,
        "receipt_time": receipt_time.isoformat(),
        "latest_reading_time": latest.isoformat(),
        "data_age_seconds": data_age,
        "points": points,
    }


async def mark_alert_read(
    engine: AsyncEngine,
    *,
    alert_id: str,
    read_by: str,
) -> bool:
    await ensure_alert_episode_tables(engine)
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "UPDATE ops_alert_queue SET read_at = COALESCE(read_at, now()), "
                "read_by = COALESCE(read_by, :read_by) WHERE alert_id = :alert_id "
                "RETURNING alert_id"
            ),
            {"alert_id": alert_id, "read_by": read_by},
        )
    return result.scalar_one_or_none() is not None


def _preventive_from_row(row: RowMapping) -> dict[str, JsonValue]:
    return {
        "preventive_projection_id": str(row["preventive_projection_id"]),
        "stream_key": str(row["stream_key"]),
        "manufacturer_id": str(row["manufacturer_id"]),
        "substation_id": int(row["substation_id"]),
        "evaluation_run_id": str(row["evaluation_run_id"]),
        "priority_level": str(row["priority_level"]),
        "priority_score": _json_scalar(row["priority_score"]),
        "freshness_status": str(row["freshness_status"]),
        "reason": row["reason"],
        "projected_at": row["projected_at"].isoformat(),
        "expires_at": None if row["expires_at"] is None else row["expires_at"].isoformat(),
    }


def _telemetry_from_row(row: RowMapping) -> dict[str, JsonValue]:
    return {
        "reading_time": row["reading_time"].isoformat(),
        "source_sensor": str(row["source_sensor"]),
        "sensor_value": _json_scalar(row["sensor_value"]),
        "source_file": row["source_file"],
    }


def _json_scalar(value: JsonValue | Decimal | datetime) -> JsonValue:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
