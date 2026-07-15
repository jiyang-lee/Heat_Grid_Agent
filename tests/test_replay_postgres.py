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
async def test_replay_window_creates_scoped_synthetic_alerts() -> None:
    from replay_dataset import WindowBatch
    from replay_repository import PostgresReplayStore

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
            results=[{"usable": True, "model_version": "test-model", "priority_score": 0.9, "priority_level": "high", "risk_score": 0.8} for _ in range(31)],
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
        assert completed["alert_delta"] == {"opened": 31, "resolved": 0}
        assert alerts == 31
    finally:
        async with cleanup_engine.begin() as connection:
            await connection.execute(text("DELETE FROM ops_alert_queue WHERE replay_run_id = :run_id"), {"run_id": run_id})
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
