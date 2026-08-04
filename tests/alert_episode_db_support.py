from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class AssetFixture:
    manufacturer_id: str
    substation_id: int
    card_id: str


@dataclass(frozen=True, slots=True)
class EvaluationFixture:
    stream_key: str
    as_of_time: datetime
    anomaly_label: bool | None
    freshness_status: str = "fresh"
    priority_level: str = "high"
    status: str = "completed"
    include_result: bool = True
    risk_level: str | None = None


async def seed_asset(connection: AsyncConnection, asset: AssetFixture) -> None:
    window_id = str(uuid4())
    decision_id = str(uuid4())
    substation_uid = await connection.scalar(
        text(
            "INSERT INTO substations (manufacturer_id, substation_id) "
            "VALUES (:manufacturer_id, :substation_id) "
            "ON CONFLICT (manufacturer_id, substation_id) DO UPDATE SET "
            "manufacturer_id = EXCLUDED.manufacturer_id RETURNING substation_uid"
        ),
        {"manufacturer_id": asset.manufacturer_id, "substation_id": asset.substation_id},
    )
    await connection.execute(
        text(
            "INSERT INTO windows (window_id, manufacturer_id, substation_id, substation_uid, "
            "window_start, window_end, source_file) VALUES (:window_id, :manufacturer_id, "
            ":substation_id, :substation_uid, now(), now(), 'pytest-alert-episode')"
        ),
        {
            "window_id": window_id,
            "manufacturer_id": asset.manufacturer_id,
            "substation_id": asset.substation_id,
            "substation_uid": substation_uid,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO priority_decisions (priority_decision_id, window_id, priority_score, "
            "priority_level, priority_source, policy_version, decision_basis) VALUES "
            "(:decision_id, :window_id, 0.8, 'high', 'pytest', 'pytest', 'pytest')"
        ),
        {"decision_id": decision_id, "window_id": window_id},
    )
    await connection.execute(
        text(
            "INSERT INTO priority_cards (card_id, priority_decision_id, operational_label, "
            "primary_state, review_required, trust_level, why_reason, recommended_action) "
            "VALUES (:card_id, :decision_id, 'pytest', 'pytest', true, 'verified', "
            "'pytest', 'pytest')"
        ),
        {"card_id": asset.card_id, "decision_id": decision_id},
    )


async def insert_evaluation(
    connection: AsyncConnection,
    asset: AssetFixture,
    evaluation: EvaluationFixture,
) -> str:
    evaluation_run_id = str(uuid4())
    substation_uid = await connection.scalar(
        text(
            "SELECT substation_uid FROM substations WHERE manufacturer_id = :manufacturer_id "
            "AND substation_id = :substation_id"
        ),
        {"manufacturer_id": asset.manufacturer_id, "substation_id": asset.substation_id},
    )
    await connection.execute(
        text(
            "INSERT INTO priority_evaluation_runs (evaluation_run_id, as_of_time, "
            "stale_after_seconds, model_version, status, is_active, target_count, success_count, "
            "ranked_count, stream_key, source_kind, error) VALUES (:evaluation_run_id, "
            ":as_of_time, 1800, 'pytest', :status, false, 1, :success_count, :ranked_count, "
            ":stream_key, 'live', :error)"
        ),
        {
            "evaluation_run_id": evaluation_run_id,
            "as_of_time": evaluation.as_of_time,
            "status": evaluation.status,
            "success_count": 1 if evaluation.status == "completed" else 0,
            "ranked_count": 1 if evaluation.status == "completed" else 0,
            "stream_key": evaluation.stream_key,
            "error": None if evaluation.status == "completed" else "pytest failure",
        },
    )
    if evaluation.include_result:
        components = (
            "{}" if evaluation.risk_level is None else f'{{"risk":{{"level":"{evaluation.risk_level}"}}}}'
        )
        await connection.execute(
            text(
                "INSERT INTO priority_evaluation_results (evaluation_result_id, "
                "evaluation_run_id, substation_uid, manufacturer_id, substation_id, "
                "source_card_id, priority_score, priority_rank, rank_included, priority_level, "
                "risk_score, anomaly_score, anomaly_label, freshness_status, model_components) "
                "VALUES (:result_id, :evaluation_run_id, :substation_uid, :manufacturer_id, "
                ":substation_id, :card_id, 0.9, 1, true, :priority_level, 0.8, 0.95, "
                ":anomaly_label, :freshness_status, CAST(:components AS jsonb))"
            ),
            {
                "result_id": str(uuid4()),
                "evaluation_run_id": evaluation_run_id,
                "substation_uid": substation_uid,
                "manufacturer_id": asset.manufacturer_id,
                "substation_id": asset.substation_id,
                "card_id": asset.card_id,
                "priority_level": evaluation.priority_level,
                "anomaly_label": evaluation.anomaly_label,
                "freshness_status": evaluation.freshness_status,
                "components": components,
            },
        )
    return evaluation_run_id


async def cleanup_asset(
    connection: AsyncConnection,
    asset: AssetFixture,
    stream_key: str,
) -> None:
    await connection.execute(
        text("DELETE FROM preventive_projections WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM ops_alert_queue WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM anomaly_episode_events WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM anomaly_episode_consumptions WHERE stream_key = :stream_key"),
        {"stream_key": stream_key},
    )
    await connection.execute(
        text("DELETE FROM anomaly_episodes WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM priority_evaluation_results WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM priority_evaluation_runs WHERE stream_key = :stream_key"),
        {"stream_key": stream_key},
    )
    await connection.execute(
        text("DELETE FROM sensor_readings WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text(
            "DELETE FROM priority_cards WHERE priority_decision_id IN (SELECT priority_decision_id "
            "FROM priority_decisions WHERE window_id IN (SELECT window_id FROM windows "
            "WHERE manufacturer_id = :manufacturer_id))"
        ),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text(
            "DELETE FROM priority_decisions WHERE window_id IN (SELECT window_id FROM windows "
            "WHERE manufacturer_id = :manufacturer_id)"
        ),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM windows WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
    await connection.execute(
        text("DELETE FROM substations WHERE manufacturer_id = :manufacturer_id"),
        {"manufacturer_id": asset.manufacturer_id},
    )
