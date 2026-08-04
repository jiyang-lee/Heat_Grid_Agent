from __future__ import annotations

import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
DATABASE_URL = os.getenv("HEATGRID_REPLAY_TEST_DATABASE_URL")
ADMIN_DATABASE_URL = os.getenv("HEATGRID_REPLAY_ADMIN_TEST_DATABASE_URL")
sys.path.insert(0, str(BACKEND))

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None or ADMIN_DATABASE_URL is None,
    reason="HEATGRID_REPLAY_TEST_DATABASE_URL and HEATGRID_REPLAY_ADMIN_TEST_DATABASE_URL are required",
)


@pytest.mark.anyio
async def test_replay_tick_projects_into_operational_sensor_readings() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.replay_dataset import SensorTick
    from simulator.versions.v2_postgres_react_ops.backend.replay_repository import (
        PostgresReplayStore,
    )

    engine = create_async_engine(str(DATABASE_URL))
    cleanup_engine = create_async_engine(str(ADMIN_DATABASE_URL))
    dataset_id = str(uuid4())
    run_id = str(uuid4())
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    package_sha = hashlib.sha256(dataset_id.encode()).hexdigest()
    try:
        async with cleanup_engine.begin() as connection:
            await connection.execute(text("DROP INDEX IF EXISTS public.priority_evaluation_one_active_idx"))
            legacy_index = await connection.scalar(text("SELECT to_regclass('public.priority_evaluation_one_active_idx')::text"))
            assert legacy_index is None
        async with engine.begin() as connection:
            manufacturer_id = await connection.scalar(
                text("SELECT manufacturer_id FROM substations ORDER BY manufacturer_id, substation_id LIMIT 1")
            )
            assert isinstance(manufacturer_id, str)
            await connection.execute(
                text(
                    "INSERT INTO replay_datasets (dataset_id, dataset_version, package_sha256, "
                    "package_uri, extracted_root, manifest, status, expected_substations, "
                    "source_interval_seconds, window_ticks, replay_start, replay_end, imported_by) "
                    "VALUES (:dataset_id, :dataset_version, :package_sha256, 'test://replay', "
                    "'C:/test/replay', '{}'::jsonb, 'available', 31, 600, 36, :replay_start, "
                    ":replay_end, 'test')"
                ),
                {"dataset_id": dataset_id, "dataset_version": f"test-{dataset_id}", "package_sha256": package_sha, "replay_start": now - timedelta(days=1), "replay_end": now + timedelta(days=1)},
            )
            await connection.execute(
                text(
                    "INSERT INTO replay_runs (run_id, dataset_id, stream_key, state, start_at, "
                    "tick_seconds, lease_owner, requested_by) VALUES (:run_id, :dataset_id, :stream_key, "
                    "'running', :start_at, 1.0, 'test-worker', 'test')"
                ),
                {"run_id": run_id, "dataset_id": dataset_id, "stream_key": f"replay:{run_id}", "start_at": now},
            )
        tick = SensorTick(
            sequence=0,
            phase="replay",
            simulated_at=now,
            readings=tuple(
                {
                    "manufacturer_id": manufacturer_id,
                    "substation_id": substation_id,
                    "values": {"outdoor_temperature": 11.0, "s_hc1_supply_temperature": 44.5},
                    "quality": {"outdoor_temperature": "synthetic", "s_hc1_supply_temperature": "synthetic"},
                }
                for substation_id in range(1, 32)
            ),
        )

        store = PostgresReplayStore(engine, lease_owner="test-worker")
        first_event_id = await store.persist_tick(run_id=run_id, tick=tick)
        duplicate_event_id = await store.persist_tick(run_id=run_id, tick=tick)

        async with engine.connect() as connection:
            stream_events = await connection.scalar(
                text(
                    "SELECT count(*) FROM replay_stream_events WHERE run_id = :run_id "
                    "AND operation_key = :operation_key"
                ),
                {"run_id": run_id, "operation_key": f"tick:{run_id}:0"},
            )
            projected = await connection.scalar(
                text(
                    "SELECT count(*) FROM sensor_readings WHERE source_file = :source_file "
                    "AND reading_time = :reading_time"
                ),
                {"source_file": f"synthetic-replay:{run_id}", "reading_time": now},
            )
            latest_value = await connection.scalar(
                text(
                    "SELECT sensor_value FROM sensor_readings WHERE source_file = :source_file "
                    "AND substation_id = 1 AND source_sensor = 'outdoor_temperature'"
                ),
                {"source_file": f"synthetic-replay:{run_id}"},
            )
        assert isinstance(first_event_id, int)
        assert duplicate_event_id is None
        assert stream_events == 1
        assert projected == 62
        assert latest_value == 11.0
    finally:
        async with cleanup_engine.begin() as connection:
            await connection.execute(text("DELETE FROM sensor_readings WHERE source_file = :source_file"), {"source_file": f"synthetic-replay:{run_id}"})
            await connection.execute(text("DELETE FROM replay_stream_events WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_tick_batches WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_latest_readings WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_runs WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_datasets WHERE dataset_id = :dataset_id"), {"dataset_id": dataset_id})
        await cleanup_engine.dispose()
        await engine.dispose()


@pytest.mark.anyio
async def test_replay_window_creates_scoped_synthetic_alerts() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.replay_dataset import WindowBatch
    from simulator.versions.v2_postgres_react_ops.backend.replay_repository import (
        PostgresReplayStore,
    )

    engine = create_async_engine(str(DATABASE_URL))
    cleanup_engine = create_async_engine(str(ADMIN_DATABASE_URL))
    dataset_id = str(uuid4())
    run_id = str(uuid4())
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    package_sha = hashlib.sha256(dataset_id.encode()).hexdigest()
    try:
        async with cleanup_engine.begin() as connection:
            await connection.execute(text("DROP INDEX IF EXISTS public.priority_evaluation_one_active_idx"))
            legacy_index = await connection.scalar(text("SELECT to_regclass('public.priority_evaluation_one_active_idx')::text"))
            assert legacy_index is None
        async with engine.begin() as connection:
            manufacturer_id = await connection.scalar(
                text("SELECT manufacturer_id FROM substations ORDER BY manufacturer_id, substation_id LIMIT 1")
            )
            assert isinstance(manufacturer_id, str)
            default_before = await connection.scalar(
                text(
                    "SELECT evaluation_run_id::text FROM priority_evaluation_runs "
                    "WHERE stream_key = 'default' AND is_active"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO replay_datasets (dataset_id, dataset_version, package_sha256, "
                    "package_uri, extracted_root, manifest, status, expected_substations, "
                    "source_interval_seconds, window_ticks, replay_start, replay_end, imported_by) "
                    "VALUES (:dataset_id, :dataset_version, :package_sha256, 'test://replay', "
                    "'C:/test/replay', '{}'::jsonb, 'available', 31, 600, 36, :replay_start, "
                    ":replay_end, 'test')"
                ),
                {"dataset_id": dataset_id, "dataset_version": f"test-{dataset_id}", "package_sha256": package_sha, "replay_start": now - timedelta(days=1), "replay_end": now + timedelta(days=1)},
            )
            await connection.execute(
                text(
                    "INSERT INTO replay_runs (run_id, dataset_id, stream_key, state, start_at, "
                    "tick_seconds, lease_owner, requested_by) VALUES (:run_id, :dataset_id, :stream_key, "
                    "'running', :start_at, 1.0, 'test-worker', 'test')"
                ),
                {"run_id": run_id, "dataset_id": dataset_id, "stream_key": f"replay:{run_id}", "start_at": now},
            )
        batch = WindowBatch(
            now - timedelta(hours=6),
            now,
            tuple(
                {
                    "manufacturer_id": manufacturer_id,
                    "substation_id": substation_id,
                    "window_start": (now - timedelta(hours=6)).isoformat(),
                    "window_end": now.isoformat(),
                    "feature_set_version": "replay-test.v1",
                    "feature_values": {"outdoor_temperature__mean": 1.0},
                }
                for substation_id in range(1, 32)
            ),
        )
        store = PostgresReplayStore(engine, lease_owner="test-worker")
        assert await store.begin_window(
            run_id=run_id,
            batch=batch,
            model_version="test-model",
            input_hash="a" * 64,
        )
        completed = await store.complete_window(
            run_id=run_id,
            batch=batch,
            model_version="test-model",
            input_hash="a" * 64,
            results=[{"usable": True, "model_version": "test-model", "priority_score": 0.9, "priority_level": "urgent", "risk_score": 0.8, "anomaly_label": True} for _ in range(31)],
            inference_duration_ms=1,
        )
        async with engine.connect() as connection:
            default_after = await connection.scalar(
                text(
                    "SELECT evaluation_run_id::text FROM priority_evaluation_runs "
                    "WHERE stream_key = 'default' AND is_active"
                )
            )
            active = await connection.scalar(
                text(
                    "SELECT evaluation_run_id::text FROM priority_evaluation_runs "
                    "WHERE stream_key = :stream_key AND is_active"
                ),
                {"stream_key": f"replay:{run_id}"},
            )
            alerts = await connection.scalar(
                text(
                    "SELECT count(*) FROM ops_alert_queue WHERE replay_run_id = :run_id "
                    "AND synthetic AND status = 'open'"
                ),
                {"run_id": run_id},
            )
        assert default_after == default_before
        assert active == completed["evaluation_run_id"]
        assert completed["alert_delta"]["opened"] == 31
        assert completed["alert_delta"]["resolved"] == 0
        assert alerts == 31
    finally:
        async with cleanup_engine.begin() as connection:
            await connection.execute(text("DELETE FROM ops_alert_queue WHERE replay_run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM anomaly_episode_events WHERE stream_key = :stream_key"), {"stream_key": f"replay:{run_id}"})
            await connection.execute(text("DELETE FROM anomaly_episode_consumptions WHERE stream_key = :stream_key"), {"stream_key": f"replay:{run_id}"})
            await connection.execute(text("DELETE FROM anomaly_episodes WHERE stream_key = :stream_key"), {"stream_key": f"replay:{run_id}"})
            await connection.execute(text("DELETE FROM priority_evaluation_results WHERE evaluation_run_id IN (SELECT evaluation_run_id FROM priority_evaluation_runs WHERE source_run_id = :run_id)"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_stream_events WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_window_evaluations WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("UPDATE replay_runs SET last_evaluation_run_id = NULL WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM priority_evaluation_runs WHERE source_run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM priority_cards WHERE priority_decision_id IN (SELECT priority_decision_id FROM priority_decisions WHERE window_id IN (SELECT window_id FROM windows WHERE source_file = :source_file))"), {"source_file": f"synthetic-replay:{run_id}"})
            await connection.execute(text("DELETE FROM priority_decisions WHERE window_id IN (SELECT window_id FROM windows WHERE source_file = :source_file)"), {"source_file": f"synthetic-replay:{run_id}"})
            await connection.execute(text("DELETE FROM model_feature_snapshots WHERE window_id IN (SELECT window_id FROM windows WHERE source_file = :source_file)"), {"source_file": f"synthetic-replay:{run_id}"})
            await connection.execute(text("DELETE FROM windows WHERE source_file = :source_file"), {"source_file": f"synthetic-replay:{run_id}"})
            await connection.execute(text("DELETE FROM replay_runs WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_datasets WHERE dataset_id = :dataset_id"), {"dataset_id": dataset_id})
        await cleanup_engine.dispose()
        await engine.dispose()


@pytest.mark.anyio
async def test_replay_window_failure_marks_priority_evaluation_failed() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.replay_dataset import WindowBatch
    from simulator.versions.v2_postgres_react_ops.backend.replay_repository import (
        PostgresReplayStore,
    )

    engine = create_async_engine(str(DATABASE_URL))
    cleanup_engine = create_async_engine(str(ADMIN_DATABASE_URL))
    dataset_id = str(uuid4())
    run_id = str(uuid4())
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    package_sha = hashlib.sha256(dataset_id.encode()).hexdigest()
    try:
        async with engine.begin() as connection:
            manufacturer_id = await connection.scalar(
                text("SELECT manufacturer_id FROM substations ORDER BY manufacturer_id, substation_id LIMIT 1")
            )
            assert isinstance(manufacturer_id, str)
            await connection.execute(
                text(
                    "INSERT INTO replay_datasets (dataset_id, dataset_version, package_sha256, "
                    "package_uri, extracted_root, manifest, status, expected_substations, "
                    "source_interval_seconds, window_ticks, replay_start, replay_end, imported_by) "
                    "VALUES (:dataset_id, :dataset_version, :package_sha256, 'test://replay', "
                    "'C:/test/replay', '{}'::jsonb, 'available', 31, 600, 36, :replay_start, "
                    ":replay_end, 'test')"
                ),
                {"dataset_id": dataset_id, "dataset_version": f"test-{dataset_id}", "package_sha256": package_sha, "replay_start": now - timedelta(days=1), "replay_end": now + timedelta(days=1)},
            )
            await connection.execute(
                text(
                    "INSERT INTO replay_runs (run_id, dataset_id, stream_key, state, start_at, "
                    "tick_seconds, lease_owner, requested_by) VALUES (:run_id, :dataset_id, :stream_key, "
                    "'running', :start_at, 1.0, 'test-worker', 'test')"
                ),
                {"run_id": run_id, "dataset_id": dataset_id, "stream_key": f"replay:{run_id}", "start_at": now},
            )
        batch = WindowBatch(
            now - timedelta(hours=6),
            now,
            tuple(
                {
                    "manufacturer_id": manufacturer_id,
                    "substation_id": substation_id,
                    "window_start": (now - timedelta(hours=6)).isoformat(),
                    "window_end": now.isoformat(),
                    "feature_set_version": "replay-test.v1",
                    "feature_values": {"outdoor_temperature__mean": 1.0},
                }
                for substation_id in range(1, 32)
            ),
        )
        store = PostgresReplayStore(engine, lease_owner="test-worker")
        assert await store.begin_window(
            run_id=run_id,
            batch=batch,
            model_version="test-model",
            input_hash="b" * 64,
        )
        await store.fail_window(run_id=run_id, window_end=now, error="forced replay failure")

        async with engine.connect() as connection:
            row = (
                await connection.execute(
                        text(
                            "SELECT evaluation.status AS evaluation_status, evaluation.error, "
                            "replay_eval.status AS window_status FROM replay_window_evaluations replay_eval "
                            "JOIN priority_evaluation_runs evaluation USING (evaluation_run_id) "
                            "WHERE replay_eval.run_id = :run_id AND replay_eval.window_end = :window_end"
                        ),
                    {"run_id": run_id, "window_end": now},
                )
            ).mappings().one()
            open_alerts = await connection.scalar(
                text("SELECT count(*) FROM ops_alert_queue WHERE replay_run_id = :run_id"),
                {"run_id": run_id},
            )

        assert row["window_status"] == "failed"
        assert row["evaluation_status"] == "failed"
        assert row["error"] == "forced replay failure"
        assert open_alerts == 0
    finally:
        async with cleanup_engine.begin() as connection:
            await connection.execute(text("DELETE FROM replay_window_evaluations WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("UPDATE replay_runs SET last_evaluation_run_id = NULL WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM priority_evaluation_runs WHERE source_run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_runs WHERE run_id = :run_id"), {"run_id": run_id})
            await connection.execute(text("DELETE FROM replay_datasets WHERE dataset_id = :dataset_id"), {"dataset_id": dataset_id})
        await cleanup_engine.dispose()
        await engine.dispose()
