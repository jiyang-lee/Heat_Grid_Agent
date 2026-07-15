from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from uuid import NAMESPACE_URL, uuid4, uuid5

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from alert_repository import ENQUEUE_ALERTS_SQL, ensure_alert_queue
from heatgrid_ops.priority.evaluation import (
    INSERT_RESULT_SQL,
    build_evaluation_results,
    ensure_priority_evaluation_tables,
)
from replay_dataset import ReplayManifest, SensorTick, WindowBatch
from replay_service import _public_inference_results

DEMO_REPLAY_RUNS_DDL: Final = """
CREATE TABLE IF NOT EXISTS demo_replay_runs (
    run_id uuid PRIMARY KEY,
    dataset_version text NOT NULL,
    state text NOT NULL CHECK (
        state IN ('running', 'paused', 'completed', 'error', 'reset', 'superseded')
    ),
    cursor bigint NOT NULL DEFAULT 0 CHECK (cursor >= 0),
    start_at timestamptz NOT NULL,
    replay_start timestamptz NOT NULL,
    replay_end timestamptz NOT NULL,
    current_simulated_at timestamptz,
    has_scored_window boolean NOT NULL DEFAULT false,
    last_evaluation_run_id uuid,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
)
"""

SENSOR_READINGS_DDL: Final = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES demo_replay_runs(run_id) ON DELETE CASCADE,
    dataset_version text NOT NULL,
    sequence bigint NOT NULL,
    phase text NOT NULL CHECK (phase IN ('warmup', 'replay')),
    simulated_at timestamptz NOT NULL,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    values jsonb NOT NULL,
    quality jsonb NOT NULL,
    is_synthetic boolean NOT NULL DEFAULT true,
    scenario_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, sequence, manufacturer_id, substation_id)
)
"""

REPLAY_INDEX_DDL: Final = (
    "CREATE INDEX IF NOT EXISTS demo_replay_runs_state_idx "
    "ON demo_replay_runs(state, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS sensor_readings_time_idx "
    "ON sensor_readings(run_id, simulated_at, substation_id)",
    "CREATE INDEX IF NOT EXISTS sensor_readings_substation_idx "
    "ON sensor_readings(substation_id, simulated_at DESC)",
)
REPLAY_COMPATIBILITY_DDL: Final = (
    "ALTER TABLE demo_replay_runs ADD COLUMN IF NOT EXISTS "
    "has_scored_window boolean NOT NULL DEFAULT false",
    "ALTER TABLE demo_replay_runs ADD COLUMN IF NOT EXISTS last_evaluation_run_id uuid",
)


async def ensure_replay_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(DEMO_REPLAY_RUNS_DDL))
        await connection.execute(text(SENSOR_READINGS_DDL))
        for statement in REPLAY_COMPATIBILITY_DDL:
            await connection.execute(text(statement))
        for statement in REPLAY_INDEX_DDL:
            await connection.execute(text(statement))


class PostgresReplayStore:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        expected_substations: int = 31,
    ) -> None:
        self.engine = engine
        self.expected_substations = expected_substations

    async def load_recoverable_run(
        self,
        *,
        dataset_version: str,
    ) -> dict[str, Any] | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT run_id, dataset_version, state, cursor, start_at, "
                    "current_simulated_at, has_scored_window, last_evaluation_run_id "
                    "FROM demo_replay_runs "
                    "WHERE dataset_version = :dataset_version "
                    "AND state IN ('running', 'paused') "
                    "ORDER BY updated_at DESC, created_at DESC LIMIT 1"
                ),
                {"dataset_version": dataset_version},
            )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        async with self.engine.connect() as connection:
            reading_result = await connection.execute(
                text(
                    "SELECT manufacturer_id, substation_id, simulated_at, "
                    "CAST(values AS text) AS values, CAST(quality AS text) AS quality "
                    "FROM sensor_readings WHERE run_id = :run_id "
                    "AND simulated_at = (SELECT max(simulated_at) FROM sensor_readings "
                    "WHERE run_id = :run_id) ORDER BY substation_id"
                ),
                {"run_id": row["run_id"]},
            )
        latest_readings = [
            {
                "manufacturer_id": str(reading["manufacturer_id"]),
                "substation_id": int(reading["substation_id"]),
                "simulated_at": reading["simulated_at"].isoformat(),
                "values": orjson.loads(reading["values"]),
                "quality": orjson.loads(reading["quality"]),
            }
            for reading in reading_result.mappings().all()
        ]
        return {
            "run_id": str(row["run_id"]),
            "dataset_version": str(row["dataset_version"]),
            "state": str(row["state"]),
            "cursor": int(row["cursor"]),
            "start_at": row["start_at"],
            "current_simulated_at": row["current_simulated_at"],
            "has_scored_window": bool(row["has_scored_window"]),
            "last_evaluation_run_id": None
            if row["last_evaluation_run_id"] is None
            else str(row["last_evaluation_run_id"]),
            "latest_readings": latest_readings,
        }

    async def create_run(
        self,
        *,
        run_id: str,
        manifest: ReplayManifest,
        start_at: datetime,
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO demo_replay_runs ("
                    "run_id, dataset_version, state, cursor, start_at, replay_start, replay_end"
                    ") VALUES ("
                    ":run_id, :dataset_version, 'running', 0, :start_at, "
                    ":replay_start, :replay_end)"
                ),
                {
                    "run_id": run_id,
                    "dataset_version": manifest.dataset_version,
                    "start_at": start_at,
                    "replay_start": manifest.replay_start,
                    "replay_end": manifest.replay_end,
                },
            )

    async def update_run(
        self,
        *,
        run_id: str,
        state: str,
        cursor: int,
        current_simulated_at: datetime | None,
        error: str | None = None,
    ) -> None:
        terminal = state in {"completed", "error", "reset", "superseded"}
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE demo_replay_runs SET state = :state, cursor = :cursor, "
                    "current_simulated_at = :current_simulated_at, error = :error, "
                    "updated_at = now(), completed_at = CASE WHEN :terminal "
                    "THEN COALESCE(completed_at, now()) ELSE NULL END "
                    "WHERE run_id = :run_id"
                ),
                {
                    "run_id": run_id,
                    "state": state,
                    "cursor": cursor,
                    "current_simulated_at": current_simulated_at,
                    "error": error,
                    "terminal": terminal,
                },
            )
            if state in {"reset", "superseded"}:
                await connection.execute(
                    text(
                        "UPDATE priority_evaluation_runs SET is_active = false "
                        "WHERE evaluation_run_id = (SELECT last_evaluation_run_id "
                        "FROM demo_replay_runs WHERE run_id = :run_id)"
                    ),
                    {"run_id": run_id},
                )
                await connection.execute(
                    text(
                        "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), "
                        "acked_by = 'replay-reset' WHERE status = 'open' "
                        "AND evaluation_run_id = (SELECT last_evaluation_run_id "
                        "FROM demo_replay_runs WHERE run_id = :run_id)"
                    ),
                    {"run_id": run_id},
                )
            elif state == "paused":
                await connection.execute(
                    text(
                        "UPDATE priority_evaluation_runs SET is_active = false "
                        "WHERE is_active AND EXISTS (SELECT 1 FROM demo_replay_runs "
                        "WHERE run_id = :run_id AND last_evaluation_run_id IS NOT NULL)"
                    ),
                    {"run_id": run_id},
                )
                await connection.execute(
                    text(
                        "UPDATE priority_evaluation_runs SET is_active = true "
                        "WHERE evaluation_run_id = (SELECT last_evaluation_run_id "
                        "FROM demo_replay_runs WHERE run_id = :run_id)"
                    ),
                    {"run_id": run_id},
                )

    async def persist_tick(self, *, run_id: str, tick: SensorTick) -> None:
        rows = [
            {
                "run_id": run_id,
                "dataset_version": reading.dataset_version,
                "sequence": reading.sequence,
                "phase": reading.phase,
                "simulated_at": reading.simulated_at,
                "manufacturer_id": reading.manufacturer_id,
                "substation_id": reading.substation_id,
                "values": _json(reading.values),
                "quality": _json(reading.quality),
                "is_synthetic": reading.is_synthetic,
                "scenario_id": reading.scenario_id,
            }
            for reading in tick.readings
        ]
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO sensor_readings ("
                    "run_id, dataset_version, sequence, phase, simulated_at, "
                    "manufacturer_id, substation_id, values, quality, is_synthetic, "
                    "scenario_id) VALUES ("
                    ":run_id, :dataset_version, :sequence, :phase, :simulated_at, "
                    ":manufacturer_id, :substation_id, CAST(:values AS jsonb), "
                    "CAST(:quality AS jsonb), :is_synthetic, :scenario_id) "
                    "ON CONFLICT (run_id, sequence, manufacturer_id, substation_id) "
                    "DO UPDATE SET values = EXCLUDED.values, quality = EXCLUDED.quality, "
                    "scenario_id = EXCLUDED.scenario_id"
                ),
                rows,
            )

    async def has_evaluation_for_window(
        self,
        *,
        run_id: str,
        window_end: datetime,
    ) -> bool:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM demo_replay_runs AS replay "
                    "JOIN priority_evaluation_runs AS evaluation "
                    "ON evaluation.evaluation_run_id = replay.last_evaluation_run_id "
                    "WHERE replay.run_id = :run_id "
                    "AND evaluation.status = 'completed' "
                    "AND evaluation.as_of_time = :window_end)"
                ),
                {"run_id": run_id, "window_end": window_end},
            )
        return bool(result.scalar_one())

    async def persist_scored_batch(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        inferences: list[dict[str, Any]],
        model_version: str,
    ) -> dict[str, Any]:
        if len(batch.records) != self.expected_substations:
            raise ValueError(
                f"scored batch has {len(batch.records)} substations; "
                f"expected {self.expected_substations}"
            )
        evaluation_run_id = str(uuid4())
        candidates: list[dict[str, Any]] = []
        persisted: list[dict[str, Any]] = []
        for record, inference in zip(batch.records, inferences, strict=True):
            key = (
                f"{record.dataset_version}|{record.manufacturer_id}|"
                f"{record.substation_id}|{record.window_start.isoformat()}|"
                f"{record.window_end.isoformat()}"
            )
            window_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-window|{key}"))
            decision_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-decision|{key}"))
            card_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-card|{key}"))
            candidates.append(
                {
                    "manufacturer_id": record.manufacturer_id,
                    "substation_id": record.substation_id,
                    "source_window_id": window_id,
                    "source_window_start": record.window_start,
                    "source_window_end": record.window_end,
                    "source_card_id": card_id,
                    "source_priority_decision_id": decision_id,
                    "feature_set_version": record.feature_set_version,
                    "configuration_type": record.context.get("configuration_type"),
                    "operational_label": "synthetic replay priority",
                    "primary_state": _primary_state(inference),
                    "review_required": True,
                    "trust_level": "synthetic",
                    "why_reason": "Priority was inferred from a synthetic replay window.",
                    "recommended_action": "Operator review is required before action.",
                }
            )
            persisted.append(
                {
                    "record": record,
                    "inference": inference,
                    "window_id": window_id,
                    "decision_id": decision_id,
                    "card_id": card_id,
                }
            )

        evaluation_rows = build_evaluation_results(
            candidates,
            inferences=inferences,
            evaluation_run_id=evaluation_run_id,
            as_of_time=batch.window_end,
            stale_after_seconds=6 * 3600,
        )
        await ensure_alert_queue(self.engine)
        async with self.engine.begin() as connection:
            for item in persisted:
                await self._persist_model_contract(connection, run_id=run_id, **item)
            await connection.execute(
                text("UPDATE priority_evaluation_runs SET is_active = false WHERE is_active")
            )
            await connection.execute(
                text(
                    "INSERT INTO priority_evaluation_runs ("
                    "evaluation_run_id, as_of_time, stale_after_seconds, model_version, "
                    "status, is_active, target_count, success_count, stale_count, "
                    "missing_count, ranked_count, completed_at) VALUES ("
                    ":evaluation_run_id, :as_of_time, :stale_after_seconds, "
                    ":model_version, 'completed', true, :target_count, :success_count, "
                    ":stale_count, :missing_count, :ranked_count, now())"
                ),
                {
                    "evaluation_run_id": evaluation_run_id,
                    "as_of_time": batch.window_end,
                    "stale_after_seconds": 6 * 3600,
                    "model_version": model_version,
                    "target_count": len(evaluation_rows),
                    "success_count": sum(
                        row["freshness_status"] == "fresh" for row in evaluation_rows
                    ),
                    "stale_count": sum(
                        row["freshness_status"] == "stale" for row in evaluation_rows
                    ),
                    "missing_count": sum(
                        row["freshness_status"] == "missing" for row in evaluation_rows
                    ),
                    "ranked_count": sum(bool(row["rank_included"]) for row in evaluation_rows),
                },
            )
            if evaluation_rows:
                await connection.execute(text(INSERT_RESULT_SQL), evaluation_rows)
            await connection.execute(
                text(
                    "UPDATE demo_replay_runs SET has_scored_window = true, "
                    "last_evaluation_run_id = :evaluation_run_id, updated_at = now() "
                    "WHERE run_id = :run_id"
                ),
                {
                    "run_id": run_id,
                    "evaluation_run_id": evaluation_run_id,
                },
            )
            await connection.execute(
                text(
                    "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), "
                    "acked_by = 'snapshot-rollover' WHERE status = 'open' "
                    "AND evaluation_run_id IS DISTINCT FROM ("
                    "SELECT evaluation_run_id FROM priority_evaluation_runs "
                    "WHERE is_active ORDER BY completed_at DESC LIMIT 1)"
                )
            )
            await connection.execute(text(ENQUEUE_ALERTS_SQL))
        return {
            "evaluation_run_id": evaluation_run_id,
            "results": _public_inference_results(batch, inferences),
        }

    async def _persist_model_contract(
        self,
        connection: Any,
        *,
        run_id: str,
        record: Any,
        inference: dict[str, Any],
        window_id: str,
        decision_id: str,
        card_id: str,
    ) -> None:
        await connection.execute(
            text(
                "INSERT INTO substations (manufacturer_id, substation_id, configuration_type) "
                "VALUES (:manufacturer_id, :substation_id, :configuration_type) "
                "ON CONFLICT (manufacturer_id, substation_id) DO UPDATE SET "
                "configuration_type = COALESCE(EXCLUDED.configuration_type, "
                "substations.configuration_type)"
            ),
            {
                "manufacturer_id": record.manufacturer_id,
                "substation_id": record.substation_id,
                "configuration_type": record.context.get("configuration_type"),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO windows ("
                "window_id, manufacturer_id, substation_id, window_start, window_end, "
                "source_file, season_bucket, label, fault_event_id) VALUES ("
                ":window_id, :manufacturer_id, :substation_id, :window_start, :window_end, "
                ":source_file, :season_bucket, :label, :fault_event_id) "
                "ON CONFLICT (window_id) DO UPDATE SET source_file = EXCLUDED.source_file"
            ),
            {
                "window_id": window_id,
                "manufacturer_id": record.manufacturer_id,
                "substation_id": record.substation_id,
                "window_start": record.window_start,
                "window_end": record.window_end,
                "source_file": record.source_file,
                "season_bucket": record.context.get("season_bucket"),
                "label": record.context.get("label"),
                "fault_event_id": record.context.get("fault_event_id"),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO model_feature_snapshots ("
                "window_id, feature_set_version, features, source_artifacts) VALUES ("
                ":window_id, :feature_set_version, CAST(:features AS jsonb), "
                "CAST(:source_artifacts AS jsonb)) ON CONFLICT (window_id) DO UPDATE SET "
                "feature_set_version = EXCLUDED.feature_set_version, "
                "features = EXCLUDED.features, source_artifacts = EXCLUDED.source_artifacts, "
                "updated_at = now()"
            ),
            {
                "window_id": window_id,
                "feature_set_version": record.feature_set_version,
                "features": _json(record.feature_values),
                "source_artifacts": _json(
                    [
                        {
                            "kind": "demo_replay_window_csv",
                            "path": record.source_file,
                            "feature_hash": record.feature_hash,
                            "run_id": run_id,
                        }
                    ]
                ),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO priority_decisions ("
                "priority_decision_id, window_id, current_best_priority_score, "
                "current_best_priority_level, m1_specialist_priority_score, "
                "m1_specialist_priority_level, priority_score, priority_level, "
                "priority_source, m1_priority_agreement, policy_version, "
                "current_best_weight, m1_specialist_weight, decision_basis, "
                "m1_specialist_primary_state, m1_specialist_fault_group) VALUES ("
                ":decision_id, :window_id, :current_best_score, :current_best_level, "
                ":m1_score, :m1_level, :priority_score, :priority_level, "
                ":priority_source, :agreement, :policy_version, 0.65, 0.35, "
                ":decision_basis, :primary_state, :fault_group) "
                "ON CONFLICT (priority_decision_id) DO UPDATE SET "
                "current_best_priority_score = EXCLUDED.current_best_priority_score, "
                "current_best_priority_level = EXCLUDED.current_best_priority_level, "
                "m1_specialist_priority_score = EXCLUDED.m1_specialist_priority_score, "
                "m1_specialist_priority_level = EXCLUDED.m1_specialist_priority_level, "
                "priority_score = EXCLUDED.priority_score, "
                "priority_level = EXCLUDED.priority_level, "
                "priority_source = EXCLUDED.priority_source, "
                "m1_priority_agreement = EXCLUDED.m1_priority_agreement, "
                "policy_version = EXCLUDED.policy_version, "
                "decision_basis = EXCLUDED.decision_basis, "
                "m1_specialist_primary_state = EXCLUDED.m1_specialist_primary_state, "
                "m1_specialist_fault_group = EXCLUDED.m1_specialist_fault_group"
            ),
            {
                "decision_id": decision_id,
                "window_id": window_id,
                "current_best_score": inference.get("current_best_priority_score"),
                "current_best_level": inference.get("current_best_priority_level"),
                "m1_score": inference.get("m1_specialist_priority_score"),
                "m1_level": inference.get("m1_specialist_priority_level"),
                "priority_score": inference.get("priority_score"),
                "priority_level": inference.get("priority_level"),
                "priority_source": inference.get("priority_source") or "demo_replay",
                "agreement": inference.get("m1_priority_agreement"),
                "policy_version": inference.get("model_version"),
                "decision_basis": "same-run synthetic replay batch inference",
                "primary_state": _primary_state(inference),
                "fault_group": _fault_group(inference),
            },
        )
        raw_card = {
            "dataset_version": record.dataset_version,
            "synthetic": True,
            "manufacturer_id": record.manufacturer_id,
            "substation_id": record.substation_id,
            "window_start": record.window_start.isoformat(),
            "window_end": record.window_end.isoformat(),
            "feature_hash": record.feature_hash,
            "priority_score": inference.get("priority_score"),
            "priority_level": inference.get("priority_level"),
            "risk_score": inference.get("risk_score"),
            "anomaly_score": inference.get("anomaly_score"),
            "leadtime_bucket": inference.get("leadtime_bucket"),
        }
        await connection.execute(
            text(
                "INSERT INTO priority_cards ("
                "card_id, priority_decision_id, operational_label, primary_state, "
                "review_required, trust_level, why_reason, recommended_action, raw_card) "
                "VALUES (:card_id, :decision_id, :operational_label, :primary_state, "
                "true, 'synthetic', :why_reason, :recommended_action, "
                "CAST(:raw_card AS jsonb)) ON CONFLICT (card_id) DO UPDATE SET "
                "operational_label = EXCLUDED.operational_label, "
                "primary_state = EXCLUDED.primary_state, raw_card = EXCLUDED.raw_card"
            ),
            {
                "card_id": card_id,
                "decision_id": decision_id,
                "operational_label": "synthetic replay priority",
                "primary_state": _primary_state(inference),
                "why_reason": "Priority was inferred from a synthetic replay window.",
                "recommended_action": "Operator review is required before action.",
                "raw_card": _json(raw_card),
            },
        )

async def prepare_replay_database(engine: AsyncEngine) -> None:
    await ensure_replay_tables(engine)
    await ensure_priority_evaluation_tables(engine)
    await ensure_alert_queue(engine)


def _primary_state(inference: dict[str, Any]) -> str:
    components = inference.get("components")
    if isinstance(components, dict):
        specialist = components.get("m1_specialist")
        if isinstance(specialist, dict) and specialist.get("primary_state"):
            return str(specialist["primary_state"])
    return str(inference.get("risk_level") or "unknown")


def _fault_group(inference: dict[str, Any]) -> str | None:
    components = inference.get("components")
    if isinstance(components, dict):
        specialist = components.get("m1_specialist")
        if isinstance(specialist, dict) and specialist.get("fault_group"):
            return str(specialist["fault_group"])
    return None


def _json(value: Any) -> str:
    return orjson.dumps(value).decode("utf-8")
