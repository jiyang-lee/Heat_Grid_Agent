from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

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
                    "success_count = 31, ranked_count = 31, completed_at = now() "
                    "WHERE evaluation_run_id = :evaluation_run_id"
                ),
                {"evaluation_run_id": evaluation_run_id},
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
        return {"event_id": int(event.scalar_one()), "evaluation_run_id": str(evaluation_run_id), "window_start": batch.window_start.isoformat(), "window_end": batch.window_end.isoformat(), "result_count": len(results)}

    async def fail_window(self, *, run_id: str, window_end: datetime, error: str) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(text("UPDATE replay_window_evaluations SET status = 'failed' WHERE run_id = :run_id AND window_end = :window_end"), {"run_id": run_id, "window_end": window_end})


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


def _json(value: object) -> str:
    return orjson.dumps(value).decode()
