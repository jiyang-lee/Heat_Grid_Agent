from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, assert_never
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

try:
    from .alert_episode_policy import (
        EpisodePolicy,
        EpisodeSnapshot,
        EpisodeTransition,
        Observation,
        Severity,
        transition_episode,
    )
except ImportError:
    from alert_episode_policy import (
        EpisodePolicy,
        EpisodeSnapshot,
        EpisodeTransition,
        Observation,
        Severity,
        transition_episode,
    )

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

REQUIRED_EPISODE_TABLES: Final = (
    "anomaly_episodes",
    "anomaly_episode_consumptions",
    "anomaly_episode_events",
    "preventive_projections",
)


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
        raise RuntimeError(f"migration 016 is required for alert episodes: {', '.join(missing)}")


async def consume_latest_evaluation(engine: AsyncEngine, *, stream_key: str = "default") -> dict[str, int]:
    await ensure_alert_episode_tables(engine)
    async with engine.connect() as connection:
        evaluation_run_id = await connection.scalar(
            text(
                "SELECT evaluation_run_id::text FROM priority_evaluation_runs "
                "WHERE stream_key = :stream_key AND status = 'completed' "
                "ORDER BY is_active DESC, as_of_time DESC, completed_at DESC LIMIT 1"
            ),
            {"stream_key": stream_key},
        )
    if evaluation_run_id is None:
        return _empty_delta()
    return await consume_evaluation(engine, str(evaluation_run_id))


async def consume_evaluation(engine: AsyncEngine, evaluation_run_id: str) -> dict[str, int]:
    await ensure_alert_episode_tables(engine)
    async with engine.begin() as connection:
        return await consume_evaluation_connection(connection, evaluation_run_id)


async def consume_evaluation_connection(
    connection: AsyncConnection,
    evaluation_run_id: str,
) -> dict[str, int]:
    run = await _lock_evaluation(connection, evaluation_run_id)
    if run is None:
        return _empty_delta()
    stream_key = str(run["stream_key"])
    inserted = await connection.execute(
        text(
            "INSERT INTO anomaly_episode_consumptions (evaluation_run_id, stream_key) "
            "VALUES (:evaluation_run_id, :stream_key) ON CONFLICT DO NOTHING "
            "RETURNING evaluation_run_id"
        ),
        {"evaluation_run_id": evaluation_run_id, "stream_key": stream_key},
    )
    if inserted.scalar_one_or_none() is None:
        return {**_empty_delta(), "skipped": 1}
    if run["status"] != "completed":
        frozen = await _freeze_unobserved_episodes(connection, run, "evaluation_failed")
        return {**_empty_delta(), "frozen": frozen}
    policy = await _load_policy(connection)
    rows = await connection.execute(
        text(
            "SELECT evaluation_result_id, evaluation_run_id, substation_uid, manufacturer_id, "
            "substation_id, source_card_id, priority_rank, freshness_status, priority_level, "
            "priority_score, anomaly_label, CAST(model_components AS text) AS model_components "
            "FROM priority_evaluation_results WHERE evaluation_run_id = :evaluation_run_id "
            "ORDER BY manufacturer_id, substation_id FOR UPDATE"
        ),
        {"evaluation_run_id": evaluation_run_id},
    )
    delta = _empty_delta()
    for row in rows.mappings().all():
        change = await _consume_result(connection, run, row, policy)
        for key, value in change.items():
            delta[key] += value
    delta["frozen"] += await _freeze_unobserved_episodes(connection, run, "missing")
    return delta


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
    source_filter = (
        "AND source_file = :source_file"
        if stream_key.startswith("replay:")
        else "AND (source_file IS NULL OR source_file NOT LIKE 'synthetic-replay:%')"
    )
    params: dict[str, JsonValue] = {
        "manufacturer_id": manufacturer_id,
        "substation_id": substation_id,
        "limit": limit,
    }
    if stream_key.startswith("replay:"):
        params["source_file"] = f"synthetic-replay:{stream_key.removeprefix('replay:')}"
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT reading_time, source_sensor, sensor_value, source_file "
                "FROM sensor_readings WHERE manufacturer_id = :manufacturer_id "
                f"AND substation_id = :substation_id {source_filter} "
                "ORDER BY reading_time DESC, source_sensor LIMIT :limit"
            ),
            params,
        )
    mapped_rows = result.mappings().all()
    rows: list[JsonValue] = [_telemetry_from_row(row) for row in mapped_rows]
    latest = None if not mapped_rows else mapped_rows[0]["reading_time"]
    data_age_seconds = None
    if isinstance(latest, datetime):
        data_age_seconds = 0.0 if stream_key.startswith("replay:") else max(
            0.0,
            (datetime.now(UTC) - latest).total_seconds(),
        )
    return {
        "stream_key": stream_key,
        "trust_state": "verified" if rows else "missing",
        "receipt_time": None if latest is None else latest.isoformat(),
        "data_age_seconds": data_age_seconds,
        "points": rows,
    }


async def mark_alert_read(
    engine: AsyncEngine,
    *,
    alert_id: str,
    read_by: str,
) -> dict[str, JsonValue] | None:
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
    return None if result.scalar_one_or_none() is None else None


def _empty_delta() -> dict[str, int]:
    return {"opened": 0, "resolved": 0, "escalated": 0, "preventive": 0, "frozen": 0, "skipped": 0}


async def _consume_result(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
    policy: EpisodePolicy,
) -> dict[str, int]:
    if row["freshness_status"] != "fresh" or row["anomaly_label"] is None:
        return await _freeze_active(connection, run, row)
    if row["anomaly_label"] is False:
        preventive = await _record_preventive(connection, run, row)
        normal = await _apply_observation(connection, run, row, Observation.normal(), policy)
        normal["preventive"] += preventive
        return normal
    return await _apply_observation(connection, run, row, Observation.anomaly(severity=_severity(row)), policy)


async def _apply_observation(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
    observation: Observation,
    policy: EpisodePolicy,
) -> dict[str, int]:
    active = await _active_episode(connection, run, row)
    snapshot = _snapshot(active)
    transition = transition_episode(
        snapshot,
        observation,
        anomaly_confirmations=policy.anomaly_confirmations,
        recovery_confirmations=policy.recovery_confirmations,
    )
    if active is None and transition.status == "none":
        return _empty_delta()
    episode_id, planned_alert_id = await _upsert_episode(
        connection,
        run,
        row,
        active,
        transition,
    )
    return await _apply_transition_side_effects(
        connection,
        run,
        row,
        episode_id,
        active,
        transition,
        planned_alert_id,
    )


async def _upsert_episode(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
    active: RowMapping | None,
    transition: EpisodeTransition,
) -> tuple[str, str | None]:
    planned_alert_id = str(uuid4()) if transition.opens_alert else None
    if active is not None:
        if active["alert_id"] is not None:
            planned_alert_id = str(active["alert_id"])
        await connection.execute(
            text(
                "UPDATE anomaly_episodes SET lifecycle_status = :status, severity = :severity, "
                "consecutive_anomaly_count = :anomaly_count, consecutive_normal_count = :normal_count, "
                "last_evaluation_run_id = :evaluation_run_id, updated_at = now(), "
                "alert_id = COALESCE(alert_id, :alert_id), "
                "opened_at = CASE WHEN :status = 'open' THEN COALESCE(opened_at, now()) ELSE opened_at END, "
                "resolved_at = CASE WHEN :status = 'resolved' THEN now() ELSE resolved_at END "
                "WHERE episode_id = :episode_id"
            ),
            _episode_params(run, row, transition, str(active["episode_id"]), planned_alert_id),
        )
        return str(active["episode_id"]), planned_alert_id
    result = await connection.execute(
        text(
            "INSERT INTO anomaly_episodes (stream_key, manufacturer_id, substation_id, "
            "lifecycle_status, severity, consecutive_anomaly_count, consecutive_normal_count, "
            "last_evaluation_run_id, alert_id, opened_at, resolved_at) VALUES (:stream_key, "
            ":manufacturer_id, :substation_id, :status, :severity, :anomaly_count, "
            ":normal_count, :evaluation_run_id, :alert_id, CASE WHEN :status = 'open' THEN now() END, "
            "CASE WHEN :status = 'resolved' THEN now() END) RETURNING episode_id"
        ),
        _episode_params(run, row, transition, str(uuid4()), planned_alert_id),
    )
    return str(result.scalar_one()), planned_alert_id


async def _apply_transition_side_effects(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
    episode_id: str,
    active: RowMapping | None,
    transition: EpisodeTransition,
    planned_alert_id: str | None,
) -> dict[str, int]:
    delta = _empty_delta()
    match transition.action:
        case "opened":
            if planned_alert_id is None:
                return delta
            await _open_alert(connection, run, row, episode_id, planned_alert_id)
            delta["opened"] = 1
        case "resolved":
            await _resolve_alert(connection, episode_id)
            delta["resolved"] = 1
        case "escalated":
            if active is None:
                return delta
            await _update_open_alert(connection, run, row, str(active["alert_id"]))
            delta["escalated"] = 1
        case "pending" | "unchanged":
            if active is not None and active["alert_id"] is not None:
                await _update_open_alert(connection, run, row, str(active["alert_id"]))
        case "frozen":
            delta["frozen"] = 1
        case unreachable:
            assert_never(unreachable)
    if transition.action in {"opened", "resolved", "escalated"}:
        await _record_event(connection, run, row, episode_id, transition.action, transition.snapshot.severity)
    return delta


async def _record_preventive(connection: AsyncConnection, run: RowMapping, row: RowMapping) -> int:
    level = str(row["priority_level"] or "").lower()
    if level not in {"urgent", "high"}:
        return 0
    inserted = await connection.execute(
        text(
            "INSERT INTO preventive_projections (stream_key, manufacturer_id, substation_id, "
            "evaluation_run_id, priority_level, priority_score, freshness_status, reason) "
            "VALUES (:stream_key, :manufacturer_id, :substation_id, :evaluation_run_id, "
            ":priority_level, :priority_score, 'fresh', CAST(:reason AS jsonb)) "
            "ON CONFLICT DO NOTHING RETURNING preventive_projection_id"
        ),
        {
            "stream_key": run["stream_key"],
            "manufacturer_id": row["manufacturer_id"],
            "substation_id": row["substation_id"],
            "evaluation_run_id": row["evaluation_run_id"],
            "priority_level": level,
            "priority_score": row["priority_score"],
            "reason": _json({"anomaly_label": False, "model_components": _json_object(row["model_components"])}),
        },
    )
    return int(inserted.scalar_one_or_none() is not None)


async def _freeze_active(connection: AsyncConnection, run: RowMapping, row: RowMapping) -> dict[str, int]:
    active = await _active_episode(connection, run, row)
    if active is None:
        return _empty_delta()
    await _record_event(connection, run, row, str(active["episode_id"]), "frozen", active["severity"])
    return {**_empty_delta(), "frozen": 1}


async def _freeze_unobserved_episodes(
    connection: AsyncConnection,
    run: RowMapping,
    reason: str,
) -> int:
    result = await connection.execute(
        text(
            "INSERT INTO anomaly_episode_events (episode_id, evaluation_run_id, stream_key, "
            "manufacturer_id, substation_id, event_type, severity, payload) "
            "SELECT episode.episode_id, CAST(:evaluation_run_id AS uuid), episode.stream_key, "
            "episode.manufacturer_id, episode.substation_id, 'frozen', episode.severity, "
            "jsonb_build_object('freshness_status', CAST(:reason AS text)) FROM anomaly_episodes episode "
            "WHERE episode.stream_key = :stream_key "
            "AND episode.lifecycle_status IN ('pending', 'open') "
            "AND NOT EXISTS (SELECT 1 FROM priority_evaluation_results result "
            "WHERE result.evaluation_run_id = CAST(:evaluation_run_id AS uuid) "
            "AND result.manufacturer_id = episode.manufacturer_id "
            "AND result.substation_id = episode.substation_id) "
            "RETURNING event_id"
        ),
        {
            "evaluation_run_id": str(run["evaluation_run_id"]),
            "stream_key": str(run["stream_key"]),
            "reason": reason,
        },
    )
    return len(result.scalars().all())


async def _open_alert(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
    episode_id: str,
    alert_id: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO ops_alert_queue (alert_id, card_id, evaluation_run_id, substation_uid, "
            "manufacturer_id, substation_id, priority_rank, freshness_status, priority_level, "
            "priority_score, status, enqueue_reason, stream_key, synthetic, replay_run_id, episode_id) "
            "VALUES (:alert_id, :card_id, :evaluation_run_id, :substation_uid, :manufacturer_id, "
            ":substation_id, :priority_rank, :freshness_status, :priority_level, :priority_score, "
            "'open', :reason, :stream_key, :synthetic, :replay_run_id, :episode_id)"
        ),
        _alert_params(run, row, alert_id, episode_id),
    )


async def _update_open_alert(connection: AsyncConnection, run: RowMapping, row: RowMapping, alert_id: str) -> None:
    await connection.execute(
        text(
            "UPDATE ops_alert_queue SET evaluation_run_id = :evaluation_run_id, card_id = :card_id, "
            "priority_rank = :priority_rank, freshness_status = :freshness_status, "
            "priority_level = :priority_level, priority_score = :priority_score, status = 'open' "
            "WHERE alert_id = :alert_id"
        ),
        _alert_params(run, row, alert_id, ""),
    )


async def _resolve_alert(connection: AsyncConnection, episode_id: str) -> None:
    await connection.execute(
        text(
            "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), "
            "acked_by = 'backend-anomaly-recovery' WHERE episode_id = :episode_id "
            "AND status = 'open'"
        ),
        {"episode_id": episode_id},
    )


async def _record_event(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
    episode_id: str,
    event_type: str,
    severity: str | None,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO anomaly_episode_events (episode_id, evaluation_run_id, stream_key, "
            "manufacturer_id, substation_id, event_type, severity, payload) VALUES "
            "(:episode_id, :evaluation_run_id, :stream_key, :manufacturer_id, :substation_id, "
            ":event_type, :severity, CAST(:payload AS jsonb))"
        ),
        {
            "episode_id": episode_id,
            "evaluation_run_id": row["evaluation_run_id"],
            "stream_key": run["stream_key"],
            "manufacturer_id": row["manufacturer_id"],
            "substation_id": row["substation_id"],
            "event_type": event_type,
            "severity": severity,
            "payload": _json({"freshness_status": row["freshness_status"]}),
        },
    )


async def _active_episode(
    connection: AsyncConnection,
    run: RowMapping,
    row: RowMapping,
) -> RowMapping | None:
    result = await connection.execute(
        text(
            "SELECT episode_id, lifecycle_status, severity, alert_id, "
            "consecutive_anomaly_count, consecutive_normal_count FROM anomaly_episodes "
            "WHERE stream_key = :stream_key AND manufacturer_id = :manufacturer_id "
            "AND substation_id = :substation_id AND lifecycle_status IN ('pending', 'open') "
            "FOR UPDATE"
        ),
        {
            "stream_key": run["stream_key"],
            "manufacturer_id": row["manufacturer_id"],
            "substation_id": row["substation_id"],
        },
    )
    return result.mappings().one_or_none()


async def _lock_evaluation(connection: AsyncConnection, evaluation_run_id: str) -> RowMapping | None:
    result = await connection.execute(
        text(
            "SELECT evaluation_run_id, status, stream_key, source_kind, source_run_id "
            "FROM priority_evaluation_runs WHERE evaluation_run_id = :evaluation_run_id FOR UPDATE"
        ),
        {"evaluation_run_id": evaluation_run_id},
    )
    return result.mappings().one_or_none()


async def _load_policy(connection: AsyncConnection) -> EpisodePolicy:
    result = await connection.execute(
        text(
            "SELECT anomaly_confirmations, recovery_confirmations "
            "FROM operations_policy WHERE policy_key = 'default'"
        )
    )
    row = result.mappings().one()
    return EpisodePolicy(
        anomaly_confirmations=int(row["anomaly_confirmations"]),
        recovery_confirmations=int(row["recovery_confirmations"]),
    )


def _snapshot(row: RowMapping | None) -> EpisodeSnapshot:
    if row is None:
        return EpisodeSnapshot.empty()
    return EpisodeSnapshot(
        status=row["lifecycle_status"],
        severity=row["severity"],
        anomaly_count=int(row["consecutive_anomaly_count"]),
        normal_count=int(row["consecutive_normal_count"]),
    )


def _episode_params(
    run: RowMapping,
    row: RowMapping,
    transition: EpisodeTransition,
    episode_id: str,
    alert_id: str | None,
) -> dict[str, JsonValue]:
    return {
        "episode_id": episode_id,
        "alert_id": alert_id,
        "stream_key": str(run["stream_key"]),
        "manufacturer_id": str(row["manufacturer_id"]),
        "substation_id": int(row["substation_id"]),
        "status": transition.snapshot.status,
        "severity": transition.snapshot.severity,
        "anomaly_count": transition.snapshot.anomaly_count,
        "normal_count": transition.snapshot.normal_count,
        "evaluation_run_id": str(row["evaluation_run_id"]),
    }


def _alert_params(run: RowMapping, row: RowMapping, alert_id: str, episode_id: str) -> dict[str, JsonValue]:
    return {
        "alert_id": alert_id,
        "episode_id": episode_id,
        "card_id": str(row["source_card_id"]),
        "evaluation_run_id": str(row["evaluation_run_id"]),
        "substation_uid": str(row["substation_uid"]),
        "manufacturer_id": str(row["manufacturer_id"]),
        "substation_id": int(row["substation_id"]),
        "priority_rank": _json_scalar(row["priority_rank"]),
        "freshness_status": str(row["freshness_status"]),
        "priority_level": "urgent" if _severity(row) == "critical" else "high",
        "priority_score": _json_scalar(row["priority_score"]),
        "reason": "anomaly episode lifecycle",
        "stream_key": str(run["stream_key"]),
        "synthetic": run["source_kind"] == "replay",
        "replay_run_id": None if run["source_run_id"] is None else str(run["source_run_id"]),
    }


def _severity(row: RowMapping) -> Severity:
    components = _json_object(row["model_components"])
    risk = components.get("risk")
    risk_level = risk.get("level") if isinstance(risk, dict) else None
    priority = str(row["priority_level"] or "").lower()
    return "critical" if risk_level == "critical" or priority == "urgent" else "high"


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
        "reason": _json_object(row["reason"]),
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


def _json(value: JsonValue) -> str:
    return orjson.dumps(value).decode("utf-8")


def _json_object(value: JsonValue | str | None) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = orjson.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value
