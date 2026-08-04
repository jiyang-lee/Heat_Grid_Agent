from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

try:
    from .alert_episode_policy import EpisodeSnapshot, EpisodeTransition, Severity
except ImportError:
    from alert_episode_policy import EpisodeSnapshot, EpisodeTransition, Severity

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class EpisodeWrite:
    run: RowMapping
    result: RowMapping
    transition: EpisodeTransition
    episode_id: str
    alert_id: str | None


@dataclass(frozen=True, slots=True)
class AlertWrite:
    run: RowMapping
    result: RowMapping
    alert_id: str
    episode_id: str


@dataclass(frozen=True, slots=True)
class EpisodeEvent:
    run: RowMapping
    result: RowMapping
    episode_id: str
    event_type: str
    severity: str | None


def empty_delta() -> dict[str, int]:
    return {
        "opened": 0,
        "resolved": 0,
        "escalated": 0,
        "preventive": 0,
        "frozen": 0,
        "skipped": 0,
    }


async def active_episode(
    connection: AsyncConnection,
    run: RowMapping,
    result: RowMapping,
) -> RowMapping | None:
    query_result = await connection.execute(
        text(
            "SELECT episode_id, lifecycle_status, severity, alert_id, "
            "consecutive_anomaly_count, consecutive_normal_count FROM anomaly_episodes "
            "WHERE stream_key = :stream_key AND manufacturer_id = :manufacturer_id "
            "AND substation_id = :substation_id AND lifecycle_status IN ('pending', 'open') "
            "FOR UPDATE"
        ),
        {
            "stream_key": run["stream_key"],
            "manufacturer_id": result["manufacturer_id"],
            "substation_id": result["substation_id"],
        },
    )
    return query_result.mappings().one_or_none()


def snapshot_from_row(row: RowMapping | None) -> EpisodeSnapshot:
    if row is None:
        return EpisodeSnapshot.empty()
    return EpisodeSnapshot(
        status=row["lifecycle_status"],
        severity=row["severity"],
        anomaly_count=int(row["consecutive_anomaly_count"]),
        normal_count=int(row["consecutive_normal_count"]),
    )


async def upsert_episode(
    connection: AsyncConnection,
    run: RowMapping,
    result: RowMapping,
    active: RowMapping | None,
    transition: EpisodeTransition,
) -> EpisodeWrite:
    alert_id = str(uuid4()) if transition.opens_alert else None
    if active is not None:
        if active["alert_id"] is not None:
            alert_id = str(active["alert_id"])
        episode_id = str(active["episode_id"])
        write = EpisodeWrite(run, result, transition, episode_id, alert_id)
        await connection.execute(
            text(
                "UPDATE anomaly_episodes SET lifecycle_status = :status, severity = :severity, "
                "consecutive_anomaly_count = :anomaly_count, "
                "consecutive_normal_count = :normal_count, "
                "last_evaluation_run_id = :evaluation_run_id, updated_at = now(), "
                "alert_id = COALESCE(alert_id, :alert_id), opened_at = CASE WHEN :status = 'open' "
                "THEN COALESCE(opened_at, now()) ELSE opened_at END, resolved_at = CASE WHEN "
                ":status = 'resolved' THEN now() ELSE resolved_at END WHERE episode_id = :episode_id"
            ),
            _episode_params(write),
        )
        return write
    episode_id = str(uuid4())
    write = EpisodeWrite(run, result, transition, episode_id, alert_id)
    inserted = await connection.execute(
        text(
            "INSERT INTO anomaly_episodes (episode_id, stream_key, manufacturer_id, substation_id, "
            "lifecycle_status, severity, consecutive_anomaly_count, consecutive_normal_count, "
            "last_evaluation_run_id, alert_id, opened_at, resolved_at) VALUES (:episode_id, "
            ":stream_key, :manufacturer_id, :substation_id, :status, :severity, :anomaly_count, "
            ":normal_count, :evaluation_run_id, :alert_id, CASE WHEN :status = 'open' THEN now() END, "
            "CASE WHEN :status = 'resolved' THEN now() END) RETURNING episode_id"
        ),
        _episode_params(write),
    )
    return EpisodeWrite(run, result, transition, str(inserted.scalar_one()), alert_id)


async def apply_transition_side_effects(
    connection: AsyncConnection,
    write: EpisodeWrite,
    active: RowMapping | None,
) -> dict[str, int]:
    delta = empty_delta()
    match write.transition.action:
        case "opened":
            if write.alert_id is not None:
                await _open_alert(connection, AlertWrite(write.run, write.result, write.alert_id, write.episode_id))
                delta["opened"] = 1
        case "resolved":
            await _resolve_alert(connection, write.episode_id)
            delta["resolved"] = 1
        case "escalated":
            if active is not None and active["alert_id"] is not None:
                await _update_open_alert(
                    connection,
                    AlertWrite(write.run, write.result, str(active["alert_id"]), write.episode_id),
                )
                delta["escalated"] = 1
        case "pending" | "unchanged":
            if active is not None and active["alert_id"] is not None:
                await _update_open_alert(
                    connection,
                    AlertWrite(write.run, write.result, str(active["alert_id"]), write.episode_id),
                )
        case "frozen":
            delta["frozen"] = 1
    if write.transition.action in {"opened", "resolved", "escalated"}:
        await _record_event(
            connection,
            EpisodeEvent(
                write.run,
                write.result,
                write.episode_id,
                write.transition.action,
                write.transition.snapshot.severity,
            ),
        )
    return delta


async def record_preventive(
    connection: AsyncConnection,
    run: RowMapping,
    result: RowMapping,
) -> int:
    level = str(result["priority_level"] or "").lower()
    if level not in {"urgent", "high"}:
        return 0
    inserted = await connection.execute(
        text(
            "INSERT INTO preventive_projections (stream_key, manufacturer_id, substation_id, "
            "evaluation_run_id, priority_level, priority_score, freshness_status, reason) VALUES "
            "(:stream_key, :manufacturer_id, :substation_id, :evaluation_run_id, :priority_level, "
            ":priority_score, 'fresh', CAST(:reason AS jsonb)) ON CONFLICT DO NOTHING "
            "RETURNING preventive_projection_id"
        ),
        {
            "stream_key": run["stream_key"],
            "manufacturer_id": result["manufacturer_id"],
            "substation_id": result["substation_id"],
            "evaluation_run_id": result["evaluation_run_id"],
            "priority_level": level,
            "priority_score": result["priority_score"],
            "reason": _json({"anomaly_label": False}),
        },
    )
    return int(inserted.scalar_one_or_none() is not None)


async def freeze_active(
    connection: AsyncConnection,
    run: RowMapping,
    result: RowMapping,
) -> int:
    active = await active_episode(connection, run, result)
    if active is None:
        return 0
    await _record_event(
        connection,
        EpisodeEvent(run, result, str(active["episode_id"]), "frozen", active["severity"]),
    )
    return 1


async def freeze_unobserved(
    connection: AsyncConnection,
    run: RowMapping,
    evaluation_run_id: str,
) -> int:
    inserted = await connection.execute(
        text(
            "INSERT INTO anomaly_episode_events (episode_id, evaluation_run_id, stream_key, "
            "manufacturer_id, substation_id, event_type, severity, payload) SELECT e.episode_id, "
            ":evaluation_run_id, e.stream_key, e.manufacturer_id, e.substation_id, 'frozen', "
            "e.severity, '{\"reason\":\"missing_or_failed_evaluation\"}'::jsonb "
            "FROM anomaly_episodes e WHERE e.stream_key = :stream_key "
            "AND e.lifecycle_status IN ('pending', 'open') AND NOT EXISTS (SELECT 1 FROM "
            "priority_evaluation_results r WHERE r.evaluation_run_id = :evaluation_run_id "
            "AND r.manufacturer_id = e.manufacturer_id AND r.substation_id = e.substation_id) "
            "RETURNING event_id"
        ),
        {"evaluation_run_id": evaluation_run_id, "stream_key": run["stream_key"]},
    )
    return len(inserted.scalars().all())


def severity_for_result(result: RowMapping) -> Severity:
    components = _json_object(result["model_components"])
    risk = components.get("risk")
    risk_level = risk.get("level") if isinstance(risk, dict) else None
    priority = str(result["priority_level"] or "").lower()
    return "critical" if risk_level == "critical" or priority == "urgent" else "high"


async def _open_alert(connection: AsyncConnection, write: AlertWrite) -> None:
    await connection.execute(
        text(
            "INSERT INTO ops_alert_queue (alert_id, card_id, evaluation_run_id, substation_uid, "
            "manufacturer_id, substation_id, priority_rank, freshness_status, priority_level, "
            "priority_score, status, enqueue_reason, stream_key, synthetic, replay_run_id, episode_id) "
            "VALUES (:alert_id, :card_id, :evaluation_run_id, :substation_uid, :manufacturer_id, "
            ":substation_id, :priority_rank, :freshness_status, :priority_level, :priority_score, "
            "'open', :reason, :stream_key, :synthetic, :replay_run_id, :episode_id)"
        ),
        _alert_params(write),
    )


async def _update_open_alert(connection: AsyncConnection, write: AlertWrite) -> None:
    await connection.execute(
        text(
            "UPDATE ops_alert_queue SET evaluation_run_id = :evaluation_run_id, card_id = :card_id, "
            "priority_rank = :priority_rank, freshness_status = :freshness_status, "
            "priority_level = :priority_level, priority_score = :priority_score, status = 'open' "
            "WHERE alert_id = :alert_id"
        ),
        _alert_params(write),
    )


async def _resolve_alert(connection: AsyncConnection, episode_id: str) -> None:
    await connection.execute(
        text(
            "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), "
            "acked_by = 'backend-anomaly-recovery' WHERE episode_id = :episode_id AND status = 'open'"
        ),
        {"episode_id": episode_id},
    )


async def _record_event(connection: AsyncConnection, event: EpisodeEvent) -> None:
    await connection.execute(
        text(
            "INSERT INTO anomaly_episode_events (episode_id, evaluation_run_id, stream_key, "
            "manufacturer_id, substation_id, event_type, severity, payload) VALUES (:episode_id, "
            ":evaluation_run_id, :stream_key, :manufacturer_id, :substation_id, :event_type, "
            ":severity, CAST(:payload AS jsonb))"
        ),
        {
            "episode_id": event.episode_id,
            "evaluation_run_id": event.result["evaluation_run_id"],
            "stream_key": event.run["stream_key"],
            "manufacturer_id": event.result["manufacturer_id"],
            "substation_id": event.result["substation_id"],
            "event_type": event.event_type,
            "severity": event.severity,
            "payload": _json({"source_kind": str(event.run["source_kind"])}),
        },
    )


def _episode_params(write: EpisodeWrite) -> dict[str, JsonValue]:
    return {
        "episode_id": write.episode_id,
        "alert_id": write.alert_id,
        "stream_key": str(write.run["stream_key"]),
        "manufacturer_id": str(write.result["manufacturer_id"]),
        "substation_id": int(write.result["substation_id"]),
        "status": write.transition.snapshot.status,
        "severity": write.transition.snapshot.severity,
        "anomaly_count": write.transition.snapshot.anomaly_count,
        "normal_count": write.transition.snapshot.normal_count,
        "evaluation_run_id": str(write.result["evaluation_run_id"]),
    }


def _alert_params(write: AlertWrite) -> dict[str, JsonValue]:
    return {
        "alert_id": write.alert_id,
        "episode_id": write.episode_id,
        "card_id": str(write.result["source_card_id"]),
        "evaluation_run_id": str(write.result["evaluation_run_id"]),
        "substation_uid": str(write.result["substation_uid"]),
        "manufacturer_id": str(write.result["manufacturer_id"]),
        "substation_id": int(write.result["substation_id"]),
        "priority_rank": _json_scalar(write.result["priority_rank"]),
        "freshness_status": str(write.result["freshness_status"]),
        "priority_level": "urgent" if severity_for_result(write.result) == "critical" else "high",
        "priority_score": _json_scalar(write.result["priority_score"]),
        "reason": "anomaly episode lifecycle",
        "stream_key": str(write.run["stream_key"]),
        "synthetic": write.run["source_kind"] == "replay",
        "replay_run_id": None if write.run["source_run_id"] is None else str(write.run["source_run_id"]),
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
