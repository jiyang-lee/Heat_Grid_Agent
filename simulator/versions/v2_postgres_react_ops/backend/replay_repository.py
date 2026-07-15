from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.priority.evaluation import INSERT_RESULT_SQL, build_evaluation_results

try:
    from .replay_dataset import ImportedReplayPackage, ReplayManifest, SensorTick, WindowBatch
except ImportError:
    from replay_dataset import ImportedReplayPackage, ReplayManifest, SensorTick, WindowBatch


class ReplayConflictError(RuntimeError):
    pass


class PostgresReplayStore:
    def __init__(self, engine: AsyncEngine, *, lease_owner: str) -> None:
        self.engine = engine
        self.lease_owner = lease_owner

    async def persist_tick(self, *, run_id: str, tick: SensorTick) -> int:
        readings = [
            {
                "manufacturer_id": item["manufacturer_id"],
                "substation_id": item["substation_id"],
                "values": item["values"],
                "quality": item["quality"],
                "scenario_id": item.get("scenario_id"),
            }
            for item in tick.readings
        ]
        payload_hash = _hash(readings)
        async with self.engine.begin() as connection:
            inserted = await connection.execute(
                text(
                    "INSERT INTO replay_tick_batches (run_id, sequence, phase, simulated_at, "
                    "readings, scenario_ids, payload_hash) VALUES (:run_id, :sequence, :phase, "
                    ":simulated_at, CAST(:readings AS jsonb), CAST(:scenario_ids AS jsonb), "
                    ":payload_hash) ON CONFLICT (run_id, sequence) DO NOTHING RETURNING sequence"
                ),
                {
                    "run_id": run_id,
                    "sequence": tick.sequence,
                    "phase": tick.phase,
                    "simulated_at": tick.simulated_at,
                    "readings": _json(readings),
                    "scenario_ids": _json(sorted({item["scenario_id"] for item in readings if item["scenario_id"]})),
                    "payload_hash": payload_hash,
                },
            )
            if inserted.scalar_one_or_none() is None:
                event = await connection.execute(
                    text(
                        "SELECT event_id FROM replay_stream_events WHERE run_id = :run_id "
                        "AND operation_key = :operation_key"
                    ),
                    {"run_id": run_id, "operation_key": f"tick:{run_id}:{tick.sequence}"},
                )
                return int(event.scalar_one())
            for item in readings:
                substation = await connection.execute(
                    text(
                        "INSERT INTO substations (manufacturer_id, substation_id) "
                        "VALUES (:manufacturer_id, :substation_id) "
                        "ON CONFLICT (manufacturer_id, substation_id) DO UPDATE SET "
                        "manufacturer_id = EXCLUDED.manufacturer_id "
                        "RETURNING substation_uid"
                    ),
                    {"manufacturer_id": item["manufacturer_id"], "substation_id": item["substation_id"]},
                )
                substation_uid = str(substation.scalar_one())
                await connection.execute(
                    text(
                        "INSERT INTO replay_latest_readings (run_id, manufacturer_id, substation_id, "
                        "sequence, simulated_at, values, quality) VALUES (:run_id, :manufacturer_id, "
                        ":substation_id, :sequence, :simulated_at, CAST(:values AS jsonb), "
                        "CAST(:quality AS jsonb)) ON CONFLICT (run_id, manufacturer_id, substation_id) "
                        "DO UPDATE SET sequence = EXCLUDED.sequence, simulated_at = EXCLUDED.simulated_at, "
                        "values = EXCLUDED.values, quality = EXCLUDED.quality, updated_at = now()"
                    ),
                    {
                        "run_id": run_id,
                        "manufacturer_id": item["manufacturer_id"],
                        "substation_id": item["substation_id"],
                        "sequence": tick.sequence,
                        "simulated_at": tick.simulated_at,
                        "values": _json(item["values"]),
                        "quality": _json(item["quality"]),
                    },
                )
                operational_rows = [
                    {
                        "sensor_reading_id": str(
                            uuid5(
                                NAMESPACE_URL,
                                "|".join(
                                    (
                                        "heatgrid-replay-sensor",
                                        run_id,
                                        str(tick.sequence),
                                        str(item["manufacturer_id"]),
                                        str(item["substation_id"]),
                                        source_sensor,
                                    )
                                ),
                            )
                        ),
                        "manufacturer_id": item["manufacturer_id"],
                        "substation_id": item["substation_id"],
                        "substation_uid": substation_uid,
                        "reading_time": tick.simulated_at,
                        "source_sensor": source_sensor,
                        "sensor_value": sensor_value,
                        "source_file": f"synthetic-replay:{run_id}",
                    }
                    for source_sensor, sensor_value in item["values"].items()
                    if isinstance(sensor_value, int | float) and not isinstance(sensor_value, bool)
                ]
                if operational_rows:
                    await connection.execute(
                        text(
                            "INSERT INTO sensor_readings (sensor_reading_id, manufacturer_id, "
                            "substation_id, substation_uid, reading_time, source_sensor, "
                            "sensor_value, source_file) VALUES (:sensor_reading_id, :manufacturer_id, "
                            ":substation_id, :substation_uid, :reading_time, :source_sensor, "
                            ":sensor_value, :source_file) ON CONFLICT (sensor_reading_id) DO UPDATE "
                            "SET sensor_value = EXCLUDED.sensor_value, source_file = EXCLUDED.source_file"
                        ),
                        operational_rows,
                    )
            event = await connection.execute(
                text(
                    "INSERT INTO replay_stream_events (run_id, event_type, sequence, simulated_at, "
                    "payload, operation_key) VALUES (:run_id, 'replay.sensor_tick.v1', :sequence, "
                    ":simulated_at, CAST(:payload AS jsonb), :operation_key) RETURNING event_id"
                ),
                {
                    "run_id": run_id,
                    "sequence": tick.sequence,
                    "simulated_at": tick.simulated_at,
                    "payload": _json({"readings": readings, "window_progress": (tick.sequence + 1) % 36}),
                    "operation_key": f"tick:{run_id}:{tick.sequence}",
                },
            )
            await connection.execute(
                text(
                    "UPDATE replay_runs SET cursor = GREATEST(cursor, :cursor), "
                    "current_simulated_at = :simulated_at, last_emitted_sequence = :sequence, "
                    "version = version + 1, heartbeat_at = now(), updated_at = now() "
                    "WHERE run_id = :run_id AND lease_owner = :lease_owner"
                ),
                {"run_id": run_id, "cursor": tick.sequence + 1, "simulated_at": tick.simulated_at, "sequence": tick.sequence, "lease_owner": self.lease_owner},
            )
            return int(event.scalar_one())

    async def begin_window(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        model_version: str,
        input_hash: str,
    ) -> bool:
        evaluation_run_id = str(uuid4())
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO priority_evaluation_runs (evaluation_run_id, as_of_time, "
                    "stale_after_seconds, model_version, status, target_count, stream_key, "
                    "source_kind, source_run_id) VALUES (:evaluation_run_id, :as_of_time, 21600, "
                    ":model_version, 'running', 31, :stream_key, 'replay', :run_id)"
                ),
                {"evaluation_run_id": evaluation_run_id, "as_of_time": batch.window_end, "model_version": model_version, "stream_key": f"replay:{run_id}", "run_id": run_id},
            )
            result = await connection.execute(
                text(
                    "INSERT INTO replay_window_evaluations (run_id, window_start, window_end, "
                    "evaluation_run_id, model_version, input_hash, result_hash, status) "
                    "VALUES (:run_id, :window_start, :window_end, :evaluation_run_id, :model_version, "
                    ":input_hash, :result_hash, 'running') ON CONFLICT (run_id, window_end) DO NOTHING "
                    "RETURNING replay_window_evaluation_id"
                ),
                {"run_id": run_id, "window_start": batch.window_start, "window_end": batch.window_end, "evaluation_run_id": evaluation_run_id, "model_version": model_version, "input_hash": input_hash, "result_hash": _hash([])},
            )
            if result.scalar_one_or_none() is None:
                await connection.execute(
                    text("DELETE FROM priority_evaluation_runs WHERE evaluation_run_id = :evaluation_run_id"),
                    {"evaluation_run_id": evaluation_run_id},
                )
                return False
        return True

    async def complete_window(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        model_version: str,
        input_hash: str,
        results: list[dict[str, Any]],
        inference_duration_ms: int,
    ) -> dict[str, Any]:
        result_hash = _hash(results)
        async with self.engine.begin() as connection:
            evaluation = await connection.execute(
                text(
                    "SELECT evaluation_run_id FROM replay_window_evaluations "
                    "WHERE run_id = :run_id AND window_end = :window_end FOR UPDATE"
                ),
                {"run_id": run_id, "window_end": batch.window_end},
            )
            evaluation_run_id = evaluation.scalar_one()
            candidates: list[dict[str, Any]] = []
            persisted: list[dict[str, Any]] = []
            for record, inference in zip(batch.records, results, strict=True):
                manufacturer_id = str(record["manufacturer_id"])
                substation_id = int(record["substation_id"])
                substation = await connection.execute(
                    text(
                        "INSERT INTO substations (manufacturer_id, substation_id, configuration_type) "
                        "VALUES (:manufacturer_id, :substation_id, :configuration_type) "
                        "ON CONFLICT (manufacturer_id, substation_id) DO UPDATE SET "
                        "configuration_type = COALESCE(EXCLUDED.configuration_type, substations.configuration_type) "
                        "RETURNING substation_uid"
                    ),
                    {"manufacturer_id": manufacturer_id, "substation_id": substation_id, "configuration_type": record.get("configuration_type")},
                )
                substation_uid = str(substation.scalar_one())
                identity = "|".join((run_id, manufacturer_id, str(substation_id), batch.window_end.isoformat()))
                window_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-window|{identity}"))
                decision_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-decision|{identity}"))
                card_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-card|{identity}"))
                normalized = {"usable": True, "priority_source": "synthetic_replay", **inference}
                candidates.append(
                    {
                        "substation_uid": substation_uid,
                        "manufacturer_id": manufacturer_id,
                        "substation_id": substation_id,
                        "source_window_id": window_id,
                        "source_window_start": batch.window_start,
                        "source_window_end": batch.window_end,
                        "source_card_id": card_id,
                        "source_priority_decision_id": decision_id,
                        "feature_set_version": record.get("feature_set_version") or "replay.v1",
                        "operational_label": "synthetic replay priority",
                        "primary_state": _primary_state(normalized),
                        "review_required": True,
                        "trust_level": "synthetic",
                        "why_reason": "Priority was inferred from a synthetic replay window.",
                        "recommended_action": "Operator review is required before action.",
                    }
                )
                persisted.append({"record": record, "inference": normalized, "window_id": window_id, "decision_id": decision_id, "card_id": card_id})
            evaluation_rows = build_evaluation_results(
                candidates,
                inferences=[item["inference"] for item in persisted],
                evaluation_run_id=str(evaluation_run_id),
                as_of_time=batch.window_end,
                stale_after_seconds=21600,
            )
            for item in persisted:
                await self._persist_synthetic_contract(connection, run_id=run_id, **item)
            if evaluation_rows:
                await connection.execute(text(INSERT_RESULT_SQL), evaluation_rows)
            await connection.execute(
                text(
                    "UPDATE priority_evaluation_runs SET is_active = false "
                    "WHERE stream_key = :stream_key AND is_active"
                ),
                {"stream_key": f"replay:{run_id}"},
            )
            await connection.execute(
                text(
                    "UPDATE priority_evaluation_runs SET status = 'completed', is_active = true, "
                    "success_count = :success_count, ranked_count = :ranked_count, completed_at = now() "
                    "WHERE evaluation_run_id = :evaluation_run_id"
                ),
                {"evaluation_run_id": evaluation_run_id, "success_count": sum(row["freshness_status"] == "fresh" for row in evaluation_rows), "ranked_count": sum(bool(row["rank_included"]) for row in evaluation_rows)},
            )
            await connection.execute(
                text(
                    "UPDATE replay_window_evaluations SET status = 'completed', result_hash = :result_hash, "
                    "inference_duration_ms = :inference_duration_ms, completed_at = now() "
                    "WHERE run_id = :run_id AND window_end = :window_end"
                ),
                {"run_id": run_id, "window_end": batch.window_end, "result_hash": result_hash, "inference_duration_ms": inference_duration_ms},
            )
            event = await connection.execute(
                text(
                    "INSERT INTO replay_stream_events (run_id, event_type, simulated_at, payload, operation_key) "
                    "VALUES (:run_id, 'replay.window_scored.v1', :simulated_at, CAST(:payload AS jsonb), "
                    ":operation_key) RETURNING event_id"
                ),
                {"run_id": run_id, "simulated_at": batch.window_end, "payload": _json({"evaluation_run_id": str(evaluation_run_id), "window_start": batch.window_start.isoformat(), "window_end": batch.window_end.isoformat(), "result_count": len(results)}), "operation_key": f"window:{run_id}:{batch.window_end.isoformat()}"},
            )
            await connection.execute(
                text(
                    "UPDATE replay_runs SET last_scored_window_end = :window_end, "
                    "last_evaluation_run_id = :evaluation_run_id, updated_at = now() WHERE run_id = :run_id"
                ),
                {"run_id": run_id, "window_end": batch.window_end, "evaluation_run_id": evaluation_run_id},
            )
            alert_delta = await self._replace_stream_alerts(
                connection,
                run_id=run_id,
                evaluation_run_id=str(evaluation_run_id),
                rows=evaluation_rows,
            )
        return {"event_id": int(event.scalar_one()), "evaluation_run_id": str(evaluation_run_id), "window_start": batch.window_start.isoformat(), "window_end": batch.window_end.isoformat(), "result_count": len(results), "alert_delta": alert_delta}

    async def fail_window(self, *, run_id: str, window_end: datetime, error: str) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(text("UPDATE replay_window_evaluations SET status = 'failed' WHERE run_id = :run_id AND window_end = :window_end"), {"run_id": run_id, "window_end": window_end})

    async def _persist_synthetic_contract(self, connection: Any, *, run_id: str, record: dict[str, Any], inference: dict[str, Any], window_id: str, decision_id: str, card_id: str) -> None:
        await connection.execute(
            text(
                "INSERT INTO windows (window_id, manufacturer_id, substation_id, substation_uid, window_start, window_end, source_file, season_bucket, label, fault_event_id) "
                "SELECT :window_id, :manufacturer_id, :substation_id, substation_uid, :window_start, :window_end, :source_file, :season_bucket, :label, :fault_event_id "
                "FROM substations WHERE manufacturer_id = :manufacturer_id AND substation_id = :substation_id "
                "ON CONFLICT (window_id) DO NOTHING"
            ),
            {"window_id": window_id, "manufacturer_id": record["manufacturer_id"], "substation_id": record["substation_id"], "window_start": _timestamp(record["window_start"]), "window_end": _timestamp(record["window_end"]), "source_file": f"synthetic-replay:{run_id}", "season_bucket": record.get("season_bucket"), "label": record.get("label"), "fault_event_id": record.get("fault_event_id")},
        )
        await connection.execute(
            text(
                "INSERT INTO model_feature_snapshots (window_id, feature_set_version, features, source_artifacts) VALUES "
                "(:window_id, :feature_set_version, CAST(:features AS jsonb), CAST(:source_artifacts AS jsonb)) "
                "ON CONFLICT (window_id) DO UPDATE SET features = EXCLUDED.features, updated_at = now()"
            ),
            {"window_id": window_id, "feature_set_version": record.get("feature_set_version") or "replay.v1", "features": _json(record["feature_values"]), "source_artifacts": _json([{"kind": "synthetic_replay", "run_id": run_id, "feature_hash": record.get("feature_hash")}])},
        )
        await connection.execute(
            text(
                "INSERT INTO priority_decisions (priority_decision_id, window_id, priority_score, priority_level, priority_source, policy_version, decision_basis, m1_specialist_primary_state) VALUES "
                "(:decision_id, :window_id, :priority_score, :priority_level, 'synthetic_replay', :model_version, 'synthetic replay inference', :primary_state) "
                "ON CONFLICT (priority_decision_id) DO UPDATE SET priority_score = EXCLUDED.priority_score, priority_level = EXCLUDED.priority_level"
            ),
            {"decision_id": decision_id, "window_id": window_id, "priority_score": inference.get("priority_score"), "priority_level": inference.get("priority_level"), "model_version": inference.get("model_version") or "replay", "primary_state": _primary_state(inference)},
        )
        await connection.execute(
            text(
                "INSERT INTO priority_cards (card_id, priority_decision_id, operational_label, primary_state, review_required, trust_level, why_reason, recommended_action, raw_card) VALUES "
                "(:card_id, :decision_id, 'synthetic replay priority', :primary_state, true, 'synthetic', :why_reason, :recommended_action, CAST(:raw_card AS jsonb)) "
                "ON CONFLICT (card_id) DO UPDATE SET raw_card = EXCLUDED.raw_card"
            ),
            {"card_id": card_id, "decision_id": decision_id, "primary_state": _primary_state(inference), "why_reason": "Priority was inferred from a synthetic replay window.", "recommended_action": "Operator review is required before action.", "raw_card": _json({"synthetic": True, "replay_run_id": run_id, "manufacturer_id": record["manufacturer_id"], "substation_id": record["substation_id"], "priority_score": inference.get("priority_score")})},
        )

    async def _replace_stream_alerts(self, connection: Any, *, run_id: str, evaluation_run_id: str, rows: list[dict[str, Any]]) -> dict[str, int]:
        resolved = await connection.execute(
            text(
                "UPDATE ops_alert_queue SET status = 'resolved', acked_at = now(), acked_by = 'replay-stream-rollover' "
                "WHERE stream_key = :stream_key AND status = 'open' AND evaluation_run_id <> :evaluation_run_id"
            ),
            {"stream_key": f"replay:{run_id}", "evaluation_run_id": evaluation_run_id},
        )
        opened = 0
        for row in rows:
            if str(row.get("priority_level") or "").lower() not in {"urgent", "high"}:
                continue
            alert_id = str(uuid5(NAMESPACE_URL, f"heatgrid-replay-alert|{evaluation_run_id}|{row['substation_uid']}"))
            result = await connection.execute(
                text(
                    "INSERT INTO ops_alert_queue (alert_id, card_id, evaluation_run_id, substation_uid, manufacturer_id, substation_id, priority_rank, freshness_status, priority_level, priority_score, enqueue_reason, stream_key, synthetic, replay_run_id) VALUES "
                    "(:alert_id, :card_id, :evaluation_run_id, :substation_uid, :manufacturer_id, :substation_id, :priority_rank, :freshness_status, :priority_level, :priority_score, 'synthetic replay priority', :stream_key, true, :run_id) "
                    "ON CONFLICT DO NOTHING RETURNING alert_id"
                ),
                {"alert_id": alert_id, "card_id": row["source_card_id"], "evaluation_run_id": evaluation_run_id, "substation_uid": row["substation_uid"], "manufacturer_id": row["manufacturer_id"], "substation_id": row["substation_id"], "priority_rank": row["priority_rank"], "freshness_status": row["freshness_status"], "priority_level": str(row["priority_level"]).lower(), "priority_score": row["priority_score"], "stream_key": f"replay:{run_id}", "run_id": run_id},
            )
            opened += int(result.scalar_one_or_none() is not None)
        return {"opened": opened, "resolved": int(resolved.rowcount or 0)}


async def register_imported_dataset(
    engine: AsyncEngine, package: ImportedReplayPackage, *, package_uri: str, imported_by: str
) -> dict[str, Any]:
    manifest = package.manifest
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO replay_datasets (dataset_version, package_sha256, package_uri, extracted_root, "
                "manifest, status, expected_substations, source_interval_seconds, window_ticks, replay_start, "
                "replay_end, imported_by, validated_at) VALUES (:dataset_version, :package_sha256, :package_uri, "
                ":extracted_root, CAST(:manifest AS jsonb), 'available', 31, 600, 36, :replay_start, :replay_end, "
                ":imported_by, now()) ON CONFLICT (dataset_version) DO UPDATE SET package_uri = EXCLUDED.package_uri "
                "RETURNING dataset_id, dataset_version, status"
            ),
            {"dataset_version": manifest.dataset_version, "package_sha256": package.package_sha256, "package_uri": package_uri, "extracted_root": str(package.root), "manifest": _json(_manifest_json(manifest)), "replay_start": manifest.replay_start, "replay_end": manifest.replay_end, "imported_by": imported_by},
        )
        row = result.mappings().one()
    return {"dataset_id": str(row["dataset_id"]), "dataset_version": row["dataset_version"], "status": row["status"]}


def _manifest_json(manifest: ReplayManifest) -> dict[str, Any]:
    return {
        "dataset_version": manifest.dataset_version,
        "warmup_start": manifest.warmup_start.isoformat(),
        "replay_start": manifest.replay_start.isoformat(),
        "replay_end": manifest.replay_end.isoformat(),
        "expected_substations": manifest.expected_substations,
        "source_interval_seconds": int(manifest.source_interval.total_seconds()),
        "window_ticks": manifest.window_ticks,
        "tick_seconds": manifest.tick_seconds,
    }


def _hash(value: object) -> str:
    return hashlib.sha256(orjson.dumps(value, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _primary_state(inference: dict[str, Any]) -> str:
    components = inference.get("components")
    if isinstance(components, dict):
        specialist = components.get("m1_specialist")
        if isinstance(specialist, dict) and specialist.get("primary_state"):
            return str(specialist["primary_state"])
    return str(inference.get("risk_level") or "unknown")


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed
    raise ValueError("replay window timestamps must be timezone-aware")


def _json(value: object) -> str:
    return orjson.dumps(value).decode()
