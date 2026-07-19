from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import anyio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alert_episode_db_support import (
    AssetFixture,
    EvaluationFixture,
    cleanup_asset,
    insert_evaluation,
    seed_asset,
)

DATABASE_URL = os.getenv("HEATGRID_REPLAY_TEST_DATABASE_URL")
ADMIN_DATABASE_URL = os.getenv("HEATGRID_REPLAY_ADMIN_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None or ADMIN_DATABASE_URL is None,
    reason="HEATGRID_REPLAY_TEST_DATABASE_URL and HEATGRID_REPLAY_ADMIN_TEST_DATABASE_URL are required",
)


@pytest.mark.anyio
async def test_episode_keeps_alert_identity_escalates_once_and_reopens_with_new_id() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_repository import (
        consume_evaluation,
    )

    engine, cleanup_engine = _engines()
    stream_key = f"pytest:episode:{uuid4()}"
    asset = AssetFixture(f"pytest-{uuid4()}", 9101, str(uuid4()))
    base = datetime(2026, 7, 19, 1, 0, tzinfo=UTC)
    sequence = (
        EvaluationFixture(stream_key, base, True),
        EvaluationFixture(stream_key, base + timedelta(minutes=1), True),
        EvaluationFixture(stream_key, base + timedelta(minutes=2), True, priority_level="urgent"),
        EvaluationFixture(stream_key, base + timedelta(minutes=3), True, priority_level="urgent"),
        EvaluationFixture(stream_key, base + timedelta(minutes=4), False),
        EvaluationFixture(stream_key, base + timedelta(minutes=5), False),
        EvaluationFixture(stream_key, base + timedelta(minutes=6), False),
        EvaluationFixture(stream_key, base + timedelta(minutes=7), True),
        EvaluationFixture(stream_key, base + timedelta(minutes=8), True),
    )
    try:
        async with engine.begin() as connection:
            await seed_asset(connection, asset)
            evaluation_ids = [
                await insert_evaluation(connection, asset, evaluation) for evaluation in sequence
            ]

        for evaluation_id in evaluation_ids:
            await consume_evaluation(engine, evaluation_id)

        async with engine.connect() as connection:
            alerts = (
                await connection.execute(
                    text(
                        "SELECT alert_id::text, status FROM ops_alert_queue "
                        "WHERE manufacturer_id = :manufacturer_id ORDER BY created_at, alert_id"
                    ),
                    {"manufacturer_id": asset.manufacturer_id},
                )
            ).mappings().all()
            escalations = await connection.scalar(
                text(
                    "SELECT count(*) FROM anomaly_episode_events WHERE stream_key = :stream_key "
                    "AND event_type = 'escalated'"
                ),
                {"stream_key": stream_key},
            )

        assert len(alerts) == 2
        assert alerts[0]["alert_id"] != alerts[1]["alert_id"]
        assert [row["status"] for row in alerts] == ["resolved", "open"]
        assert escalations == 1
    finally:
        await _cleanup(cleanup_engine, engine, asset, stream_key)


@pytest.mark.anyio
async def test_stale_missing_and_failed_evaluations_freeze_active_episode() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_repository import (
        consume_evaluation,
    )

    engine, cleanup_engine = _engines()
    stream_key = f"pytest:freeze:{uuid4()}"
    asset = AssetFixture(f"pytest-{uuid4()}", 9102, str(uuid4()))
    base = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    sequence = (
        EvaluationFixture(stream_key, base, True, priority_level="urgent"),
        EvaluationFixture(stream_key, base + timedelta(minutes=1), True, freshness_status="stale"),
        EvaluationFixture(stream_key, base + timedelta(minutes=2), None, include_result=False),
        EvaluationFixture(
            stream_key,
            base + timedelta(minutes=3),
            None,
            status="failed",
            include_result=False,
        ),
    )
    try:
        async with engine.begin() as connection:
            await seed_asset(connection, asset)
            evaluation_ids = [
                await insert_evaluation(connection, asset, evaluation) for evaluation in sequence
            ]

        deltas = [await consume_evaluation(engine, evaluation_id) for evaluation_id in evaluation_ids]

        async with engine.connect() as connection:
            episode = (
                await connection.execute(
                    text(
                        "SELECT lifecycle_status, consecutive_anomaly_count, consecutive_normal_count "
                        "FROM anomaly_episodes WHERE stream_key = :stream_key"
                    ),
                    {"stream_key": stream_key},
                )
            ).mappings().one()
            frozen_events = await connection.scalar(
                text(
                    "SELECT count(*) FROM anomaly_episode_events WHERE stream_key = :stream_key "
                    "AND event_type = 'frozen'"
                ),
                {"stream_key": stream_key},
            )

        assert [delta["frozen"] for delta in deltas] == [0, 1, 1, 1]
        assert dict(episode) == {
            "lifecycle_status": "open",
            "consecutive_anomaly_count": 1,
            "consecutive_normal_count": 0,
        }
        assert frozen_events == 3
    finally:
        await _cleanup(cleanup_engine, engine, asset, stream_key)


@pytest.mark.anyio
async def test_concurrent_duplicate_consumption_advances_episode_once() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_repository import (
        consume_evaluation,
    )

    engine, cleanup_engine = _engines()
    stream_key = f"pytest:concurrent:{uuid4()}"
    asset = AssetFixture(f"pytest-{uuid4()}", 9103, str(uuid4()))
    base = datetime(2026, 7, 19, 3, 0, tzinfo=UTC)
    outcomes: list[dict[str, int]] = []
    try:
        async with engine.begin() as connection:
            await seed_asset(connection, asset)
            evaluation_id = await insert_evaluation(
                connection,
                asset,
                EvaluationFixture(stream_key, base, True),
            )

        async def consume_once() -> None:
            outcomes.append(await consume_evaluation(engine, evaluation_id))

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(consume_once)
            task_group.start_soon(consume_once)

        async with engine.connect() as connection:
            anomaly_count = await connection.scalar(
                text(
                    "SELECT consecutive_anomaly_count FROM anomaly_episodes "
                    "WHERE stream_key = :stream_key"
                ),
                {"stream_key": stream_key},
            )

        assert sorted(outcome["skipped"] for outcome in outcomes) == [0, 1]
        assert anomaly_count == 1
    finally:
        await _cleanup(cleanup_engine, engine, asset, stream_key)


@pytest.mark.anyio
async def test_telemetry_isolates_live_and_replay_and_reports_data_age() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_repository import (
        list_asset_telemetry,
    )

    engine, cleanup_engine = _engines()
    stream_key = f"replay:{uuid4()}"
    replay_run_id = stream_key.removeprefix("replay:")
    asset = AssetFixture(f"pytest-{uuid4()}", 9104, str(uuid4()))
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5)
    try:
        async with engine.begin() as connection:
            await seed_asset(connection, asset)
            substation_uid = await connection.scalar(
                text(
                    "SELECT substation_uid FROM substations WHERE manufacturer_id = :manufacturer_id "
                    "AND substation_id = :substation_id"
                ),
                {"manufacturer_id": asset.manufacturer_id, "substation_id": asset.substation_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO sensor_readings (sensor_reading_id, manufacturer_id, substation_id, "
                    "substation_uid, reading_time, source_sensor, sensor_value, source_file) VALUES "
                    "(:live_id, :manufacturer_id, :substation_id, :substation_uid, :reading_time, "
                    "'live-temperature', 41.0, NULL), (:replay_id, :manufacturer_id, :substation_id, "
                    ":substation_uid, :reading_time, 'replay-temperature', 42.0, :source_file)"
                ),
                {
                    "live_id": str(uuid4()),
                    "replay_id": str(uuid4()),
                    "manufacturer_id": asset.manufacturer_id,
                    "substation_id": asset.substation_id,
                    "substation_uid": substation_uid,
                    "reading_time": base,
                    "source_file": f"synthetic-replay:{replay_run_id}",
                },
            )

        live = await list_asset_telemetry(
            engine,
            manufacturer_id=asset.manufacturer_id,
            substation_id=asset.substation_id,
        )
        replay = await list_asset_telemetry(
            engine,
            manufacturer_id=asset.manufacturer_id,
            substation_id=asset.substation_id,
            stream_key=stream_key,
        )

        assert [point["source_sensor"] for point in live["points"]] == ["live-temperature"]
        assert [point["source_sensor"] for point in replay["points"]] == ["replay-temperature"]
        assert isinstance(live["receipt_time"], str)
        assert isinstance(live["data_age_seconds"], int | float)
        assert replay["trust_state"] == "verified"
    finally:
        await _cleanup(cleanup_engine, engine, asset, stream_key)


def _engines() -> tuple[AsyncEngine, AsyncEngine]:
    return create_async_engine(str(DATABASE_URL)), create_async_engine(str(ADMIN_DATABASE_URL))


async def _cleanup(
    cleanup_engine: AsyncEngine,
    engine: AsyncEngine,
    asset: AssetFixture,
    stream_key: str,
) -> None:
    async with cleanup_engine.begin() as connection:
        await cleanup_asset(connection, asset, stream_key)
    await cleanup_engine.dispose()
    await engine.dispose()
