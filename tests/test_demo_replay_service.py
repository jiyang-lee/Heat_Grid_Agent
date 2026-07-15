from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import csv
import json
import sys
from typing import Any, Iterator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

from replay_dataset import (  # noqa: E402
    CsvReplayDataset,
    ReplayManifest,
    ReplayShard,
    SensorDefinition,
    SensorReading,
    SensorTick,
    WindowBatch,
    WindowRecord,
    SEOUL,
)
from replay_service import (  # noqa: E402
    MemoryReplayStore,
    ReplayControlError,
    ReplayService,
)
from replay_routes import _event_stream, _sse, make_replay_router  # noqa: E402
from replay_repository import (  # noqa: E402
    DEMO_REPLAY_RUNS_DDL,
    PostgresReplayStore,
)


class FakeDataset:
    def __init__(self) -> None:
        self.manifest = ReplayManifest(
            dataset_version="pytest-replay-v1",
            warmup_start=datetime(2023, 1, 1, tzinfo=SEOUL),
            replay_start=datetime(2023, 1, 8, tzinfo=SEOUL),
            replay_end=datetime(2026, 1, 8, tzinfo=SEOUL),
            expected_substations=31,
            source_interval_minutes=10,
            window_ticks=36,
            tick_seconds=1.0,
            raw_shards=(),
            window_shards=(),
        )
        self.sensors = tuple(
            SensorDefinition(
                sensor_key=f"sensor_{index}",
                source_column=f"sensor_{index}",
                label_ko=f"sensor {index}",
                unit="unit",
                display_order=index,
                sensor_type="temperature",
                model_feature_prefix=f"sensor_{index}",
                nullable=False,
            )
            for index in range(1, 5)
        )

    def warmup_ticks(self, target: datetime) -> list[SensorTick]:
        start = target - timedelta(days=7)
        return [
            self._tick(start + index * self.manifest.source_interval)
            for index in range(1008)
        ]

    def iter_raw_ticks(
        self,
        *,
        start: datetime,
        end: datetime | None = None,
    ) -> Iterator[SensorTick]:
        at = start
        while end is None or at < end:
            yield self._tick(at)
            at += self.manifest.source_interval

    def iter_window_batches(self, *, minimum_end: datetime) -> Iterator[WindowBatch]:
        window_end = minimum_end
        while window_end <= self.manifest.replay_end:
            window_start = window_end - self.manifest.window_duration
            records = tuple(
                WindowRecord(
                    dataset_version=self.manifest.dataset_version,
                    sequence_end=self._sequence(window_end),
                    manufacturer_id="manufacturer 1",
                    substation_id=substation_id,
                    window_start=window_start,
                    window_end=window_end,
                    expected_count=36,
                    observed_count=36,
                    feature_set_version="pytest-features-v1",
                    feature_hash=f"hash-{substation_id}",
                    feature_values={"feature": float(substation_id)},
                    context={"configuration_type": "space_heating"},
                    source_file="pytest-window.csv",
                )
                for substation_id in range(1, 32)
            )
            yield WindowBatch(window_start, window_end, records)
            window_end += self.manifest.window_duration

    def _tick(self, at: datetime) -> SensorTick:
        sequence = self._sequence(at)
        phase = "warmup" if at < self.manifest.replay_start else "replay"
        readings = tuple(
            SensorReading(
                dataset_version=self.manifest.dataset_version,
                sequence=sequence,
                phase=phase,
                simulated_at=at,
                manufacturer_id="manufacturer 1",
                substation_id=substation_id,
                values={
                    sensor.sensor_key: float(substation_id + sensor.display_order)
                    for sensor in self.sensors
                },
                quality={sensor.sensor_key: "synthetic" for sensor in self.sensors},
                is_synthetic=True,
                scenario_id=None,
            )
            for substation_id in range(1, 32)
        )
        return SensorTick(sequence, phase, at, readings)

    def _sequence(self, at: datetime) -> int:
        return int(
            (at - self.manifest.warmup_start).total_seconds()
            // self.manifest.source_interval.total_seconds()
        )


class FakeRuntime:
    model_version = "pytest-priority-runtime-v1"

    def __init__(self) -> None:
        self.call_count = 0
        self.batch_sizes: list[int] = []

    def infer_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.call_count += 1
        self.batch_sizes.append(len(rows))
        return [
            {
                "usable": True,
                "model_version": self.model_version,
                "priority_score": float(row["substation_id"]),
                "priority_level": "high" if row["substation_id"] == 31 else "medium",
                "risk_score": 0.5,
                "risk_probability": 0.5,
                "risk_level": "medium",
                "anomaly_score": 0.4,
                "anomaly_label": False,
                "leadtime_bucket": "1-3d",
                "leadtime_urgency_score": 0.5,
                "leadtime_hours": 48.0,
                "current_best_priority_score": float(row["substation_id"]),
                "current_best_priority_level": "medium",
                "m1_specialist_priority_score": 0.0,
                "m1_specialist_priority_level": "low",
                "feature_coverage": {
                    "anomaly": 1.0,
                    "risk": 1.0,
                    "leadtime": 1.0,
                    "m1_specialist": 1.0,
                },
                "components": {},
                "inference_status": "completed",
            }
            for row in rows
        ]


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.calls.append((str(statement), params))


class RecordingBegin:
    def __init__(self, connection: RecordingConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> RecordingConnection:
        return self.connection

    async def __aexit__(self, *_args: Any) -> None:
        return None


class RecordingEngine:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    def begin(self) -> RecordingBegin:
        return RecordingBegin(self.connection)


@pytest.mark.anyio
async def test_warmup_is_hidden_and_inference_runs_once_on_tick_36() -> None:
    dataset = FakeDataset()
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    service = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )

    assert service.status()["state"] == "paused"
    await service.start()

    assert len(service._history) == 1008
    assert store.ticks == []
    assert not any(event["type"] == "sensor_tick" for event in service.events.event_log)

    for _ in range(35):
        assert await service.advance_one_tick()

    assert runtime.call_count == 0
    assert service.window_progress == 35
    assert len(store.ticks) == 35
    assert all(len(tick.readings) == 31 for tick in store.ticks)

    assert await service.advance_one_tick()

    assert runtime.call_count == 1
    assert runtime.batch_sizes == [31]
    assert service.window_progress == 0
    assert service.has_scored_window is True
    assert len(store.scored_batches) == 1
    tick_events = [
        event for event in service.events.event_log if event["type"] == "sensor_tick"
    ]
    scored_events = [
        event for event in service.events.event_log if event["type"] == "window_scored"
    ]
    assert len(tick_events) == 36
    assert len(tick_events[-1]["readings"]) == 31
    assert tick_events[-1]["window_progress"] == 36
    assert scored_events[0]["result_count"] == 31


@pytest.mark.anyio
async def test_replay_http_contract_starts_paused_and_returns_dynamic_snapshot() -> None:
    dataset = FakeDataset()
    service = ReplayService(
        dataset=dataset,
        runtime=FakeRuntime(),
        store=MemoryReplayStore(),
        run_background=False,
    )
    app = FastAPI()
    app.include_router(make_replay_router(lambda: service))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        initial = await client.get("/api/demo-replay/status")
        started = await client.post(
            "/api/demo-replay/control",
            json={"action": "start"},
        )
        await service.advance_one_tick()
        snapshot = await client.get("/api/demo-replay/snapshot")

    assert initial.status_code == 200
    assert initial.json()["state"] == "paused"
    assert len(initial.json()["sensors"]) == 4
    assert started.json()["state"] == "running"
    assert len(snapshot.json()["readings"]) == 31
    assert snapshot.json()["window_progress"] == 1
    assert _sse({"type": "sensor_tick"}).startswith("data: ")
    assert "event:" not in _sse({"type": "sensor_tick"})


@pytest.mark.anyio
async def test_pause_resume_reset_preserves_previous_run_audit_cursor() -> None:
    store = MemoryReplayStore()
    service = ReplayService(
        dataset=FakeDataset(),
        runtime=FakeRuntime(),
        store=store,
        run_background=False,
    )
    await service.start()
    for _ in range(2):
        await service.advance_one_tick()
    await service.pause()
    assert service.state == "paused"
    with pytest.raises(ReplayControlError, match="not running"):
        await service.advance_one_tick()

    await service.resume()
    await service.advance_one_tick()
    previous_run_id = service.run_id
    previous_at = service.current_simulated_at
    await service.reset()

    assert service.state == "paused"
    assert service.current_simulated_at is None
    assert service.snapshot()["readings"] == []
    previous = next(run for run in store.runs if run["run_id"] == previous_run_id)
    assert previous["state"] == "reset"
    assert previous["cursor"] == 3
    assert previous["current_simulated_at"] == previous_at
    with pytest.raises(ReplayControlError, match="has not been started"):
        await service.resume()


@pytest.mark.anyio
async def test_sse_reconnect_sends_state_then_latest_31_reading_snapshot() -> None:
    service = ReplayService(
        dataset=FakeDataset(),
        runtime=FakeRuntime(),
        store=MemoryReplayStore(),
        run_background=False,
    )
    await service.start()
    await service.advance_one_tick()

    stream = _event_stream(service)
    state_event = await anext(stream)
    snapshot_event = await anext(stream)
    await stream.aclose()
    state_payload = json.loads(state_event.removeprefix("data: ").strip())
    snapshot_payload = json.loads(snapshot_event.removeprefix("data: ").strip())

    assert state_payload["type"] == "replay_state"
    assert state_payload["state"] == "running"
    assert snapshot_payload["type"] == "sensor_tick"
    assert len(snapshot_payload["readings"]) == 31
    assert snapshot_payload["simulated_at"] == service.current_simulated_at.isoformat()

    heartbeat = service.events.subscribe(heartbeat_seconds=0.001)
    assert await anext(heartbeat) is None
    await heartbeat.aclose()


@pytest.mark.anyio
async def test_prepare_failure_becomes_control_error_and_error_state() -> None:
    class MissingWarmupDataset(FakeDataset):
        def warmup_ticks(self, target: datetime) -> list[SensorTick]:
            del target
            return []

    service = ReplayService(
        dataset=MissingWarmupDataset(),
        runtime=FakeRuntime(),
        store=MemoryReplayStore(),
        run_background=False,
    )
    with pytest.raises(ReplayControlError, match="expected 1008"):
        await service.start()
    assert service.state == "error"
    assert service.error is not None
    assert any(event["type"] == "error" for event in service.events.event_log)


@pytest.mark.anyio
async def test_postgres_store_persists_one_inference_into_all_model_contracts() -> None:
    dataset = FakeDataset()
    batch = next(
        dataset.iter_window_batches(
            minimum_end=datetime(2023, 1, 8, 6, 0, tzinfo=SEOUL)
        )
    )
    runtime = FakeRuntime()
    inferences = runtime.infer_batch(
        [record.inference_input() for record in batch.records]
    )
    engine = RecordingEngine()
    store = PostgresReplayStore(engine)  # type: ignore[arg-type]
    result = await store.persist_scored_batch(
        run_id="00000000-0000-0000-0000-000000000001",
        batch=batch,
        inferences=inferences,
        model_version=runtime.model_version,
    )

    sql = "\n".join(statement for statement, _ in engine.connection.calls)
    assert "INSERT INTO windows" in sql
    assert "INSERT INTO model_feature_snapshots" in sql
    assert "INSERT INTO priority_decisions" in sql
    assert "INSERT INTO priority_cards" in sql
    assert "INSERT INTO priority_evaluation_runs" in sql
    assert "INSERT INTO priority_evaluation_results" in sql
    assert "last_evaluation_run_id =" in sql
    assert "UPDATE ops_alert_queue SET status = 'resolved'" in sql
    assert "INSERT INTO ops_alert_queue" in sql
    evaluation_call = next(
        params
        for statement, params in engine.connection.calls
        if "INSERT INTO priority_evaluation_runs" in statement
    )
    assert evaluation_call["success_count"] == 31
    assert evaluation_call["stale_count"] == 0
    assert evaluation_call["missing_count"] == 0
    assert result["evaluation_run_id"]
    assert len(result["results"]) == 31
    assert "has_scored_window boolean" in DEMO_REPLAY_RUNS_DDL


@pytest.mark.anyio
async def test_seek_warms_previous_week_without_events_and_starts_new_run() -> None:
    dataset = FakeDataset()
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    service = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    await service.start()
    await service.advance_one_tick()
    first_run_id = service.run_id
    sensor_events_before = sum(
        event["type"] == "sensor_tick" for event in service.events.event_log
    )

    target = datetime(2024, 7, 1, 3, 0, tzinfo=SEOUL)
    await service.seek(target)

    assert service.run_id != first_run_id
    assert store.runs[0]["state"] == "superseded"
    assert len(service._history) == 1008
    assert service.current_simulated_at is None
    assert service.window_progress == 18
    assert sum(
        event["type"] == "sensor_tick" for event in service.events.event_log
    ) == sensor_events_before

    await service.advance_one_tick()
    assert service.current_simulated_at == target
    assert service.window_progress == 19
    assert runtime.call_count == 0
    for _ in range(17):
        await service.advance_one_tick()
    assert runtime.call_count == 1
    assert store.scored_batches[-1].window_end == datetime(
        2024, 7, 1, 6, 0, tzinfo=SEOUL
    )


@pytest.mark.anyio
async def test_restore_marks_interrupted_run_paused_and_resumes_at_next_tick() -> None:
    dataset = FakeDataset()
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    first = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    await first.start()
    await first.advance_one_tick()
    previous_at = first.current_simulated_at
    run_id = first.run_id
    # Simulate a crash after sensor_readings committed but before run cursor update.
    store.runs[0]["cursor"] = 0
    store.runs[0]["current_simulated_at"] = None

    restored = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    assert await restored.restore() is True

    assert restored.state == "paused"
    assert restored.run_id == run_id
    assert restored.current_simulated_at == previous_at
    assert len(restored.snapshot()["readings"]) == 31
    assert store.runs[0]["state"] == "paused"
    await restored.resume()
    await restored.advance_one_tick()
    assert restored.current_simulated_at == previous_at + timedelta(minutes=10)


@pytest.mark.anyio
async def test_restore_scores_boundary_tick_committed_before_evaluation_once() -> None:
    dataset = FakeDataset()
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    first = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    await first.start()
    for _ in range(35):
        await first.advance_one_tick()

    run_id = first.run_id
    boundary_tick = dataset._tick(datetime(2023, 1, 8, 5, 50, tzinfo=SEOUL))
    await store.persist_tick(run_id=str(run_id), tick=boundary_tick)

    restored = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    assert await restored.restore() is True

    expected_end = datetime(2023, 1, 8, 6, 0, tzinfo=SEOUL)
    assert runtime.call_count == 1
    assert len(store.scored_batches) == 1
    assert store.scored_batches[0].window_end == expected_end
    assert await store.has_evaluation_for_window(
        run_id=str(run_id),
        window_end=expected_end,
    )
    assert restored.current_simulated_at == boundary_tick.simulated_at
    assert restored.window_progress == 0
    assert restored.has_scored_window is True

    assert await restored.restore() is True
    assert runtime.call_count == 1
    assert len(store.scored_batches) == 1

    await restored.resume()
    await restored.advance_one_tick()
    assert restored.current_simulated_at == expected_end
    assert restored.window_progress == 1
    assert runtime.call_count == 1


@pytest.mark.anyio
async def test_restore_scores_final_boundary_before_marking_run_completed() -> None:
    dataset = FakeDataset()
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    first = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    await first.start()
    run_id = str(first.run_id)
    final_tick = dataset._tick(
        dataset.manifest.replay_end - dataset.manifest.source_interval
    )
    await store.persist_tick(run_id=run_id, tick=final_tick)

    restored = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    assert await restored.restore() is False

    assert runtime.call_count == 1
    assert store.scored_batches[-1].window_end == dataset.manifest.replay_end
    assert store.runs[0]["state"] == "completed"
    assert restored.state == "completed"
    assert restored.has_scored_window is True


@pytest.mark.anyio
async def test_restore_preserves_midwindow_scored_state() -> None:
    dataset = FakeDataset()
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    first = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    await first.seek(datetime(2024, 7, 1, 3, 0, tzinfo=SEOUL))
    for _ in range(18):
        await first.advance_one_tick()

    assert runtime.call_count == 1
    assert store.runs[0]["cursor"] == 18
    assert store.runs[0]["has_scored_window"] is True

    restored = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    assert await restored.restore() is True
    assert restored.has_scored_window is True
    assert len(restored.snapshot()["readings"]) == 31
    assert runtime.call_count == 1


def test_csv_reader_prunes_shards_and_excludes_window_phase_from_features(
    tmp_path: Path,
) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "windows").mkdir()
    (tmp_path / "raw" / "2023-01-unused.csv").write_text(
        "this shard must never be opened\n",
        encoding="utf-8",
    )
    sensor_fields = [
        "sensor_key",
        "source_column",
        "label_ko",
        "unit",
        "display_order",
        "sensor_type",
        "model_feature_prefix",
        "nullable",
        "enabled",
    ]
    with (tmp_path / "sensor_manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=sensor_fields)
        writer.writeheader()
        for index in range(1, 5):
            writer.writerow(
                {
                    "sensor_key": f"sensor_{index}",
                    "source_column": f"sensor_{index}",
                    "label_ko": f"sensor {index}",
                    "unit": "unit",
                    "display_order": index,
                    "sensor_type": "temperature",
                    "model_feature_prefix": f"sensor_{index}__",
                    "nullable": "false",
                    "enabled": "true",
                }
            )

    raw_fields = [
        "dataset_version",
        "sequence",
        "phase",
        "simulated_at",
        "manufacturer_id",
        "substation_id",
        "sensor_1",
        "sensor_2",
        "sensor_3",
        "sensor_4",
        "quality_flag",
        "is_synthetic",
        "scenario_id",
    ]
    with (tmp_path / "raw" / "2023-02.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=raw_fields)
        writer.writeheader()
        for station in range(1, 32):
            writer.writerow(
                {
                    "dataset_version": "pytest-replay-v1",
                    "sequence": 1008,
                    "phase": "replay",
                    "simulated_at": "2023-01-08T00:00:00+09:00",
                    "manufacturer_id": "manufacturer 1",
                    "substation_id": station,
                    "sensor_1": "" if station == 1 else station,
                    "sensor_2": station + 1,
                    "sensor_3": station + 2,
                    "sensor_4": station + 3,
                    "quality_flag": "synthetic_missing"
                    if station == 1
                    else "synthetic",
                    "is_synthetic": "true",
                    "scenario_id": "",
                }
            )

    window_fields = [
        "dataset_version",
        "sequence_end",
        "phase",
        "manufacturer_id",
        "substation_id",
        "configuration_type",
        "window_start",
        "window_end",
        "expected_count",
        "observed_count",
        "feature_set_version",
        "feature_hash",
        "scenario_id",
        "sensor_1__mean",
        "sensor_2__mean",
        "sensor_3__mean",
        "sensor_4__mean",
        "has_buffer_tank",
    ]
    with (tmp_path / "windows" / "2023-01.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=window_fields)
        writer.writeheader()
        for station in range(1, 32):
            writer.writerow(
                {
                    "dataset_version": "pytest-replay-v1",
                    "sequence_end": 1043,
                    "phase": "replay",
                    "manufacturer_id": "manufacturer 1",
                    "substation_id": station,
                    "configuration_type": "space_heating",
                    "window_start": "2023-01-08T00:00:00+09:00",
                    "window_end": "2023-01-08T06:00:00+09:00",
                    "expected_count": 36,
                    "observed_count": 36,
                    "feature_set_version": "pytest-features-v1",
                    "feature_hash": f"hash-{station}",
                    "scenario_id": "",
                    "sensor_1__mean": station / 10,
                    "sensor_2__mean": station / 10 + 1,
                    "sensor_3__mean": station / 10 + 2,
                    "sensor_4__mean": station / 10 + 3,
                    "has_buffer_tank": False,
                }
            )

    manifest = {
        "dataset_version": "pytest-replay-v1",
        "warmup_start": "2023-01-01T00:00:00+09:00",
        "replay_start": "2023-01-08T00:00:00+09:00",
        "replay_end": "2026-01-08T00:00:00+09:00",
        "expected_substations": 31,
        "source_interval_minutes": 10,
        "window_ticks": 36,
        "tick_seconds": 1,
        "sensor_manifest": "sensor_manifest.csv",
        "raw_shards": [
            {
                "path": "raw/2023-01-unused.csv",
                "start": "2023-01-01T00:00:00+09:00",
                "end": "2023-01-02T00:00:00+09:00",
            },
            {
                "path": "raw/2023-02.csv",
                "start": "2023-01-08T00:00:00+09:00",
                "end": "2023-01-08T00:10:00+09:00",
            },
        ],
        "window_shards": [
            {
                "path": "windows/2023-01.csv",
                "start": "2023-01-08T06:00:00+09:00",
                "end": "2023-01-08T12:00:00+09:00",
            }
        ],
    }
    (tmp_path / "dataset_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    dataset = CsvReplayDataset(tmp_path)
    tick = next(
        dataset.iter_raw_ticks(
            start=datetime(2023, 1, 8, tzinfo=SEOUL),
            end=datetime(2023, 1, 8, 0, 10, tzinfo=SEOUL),
        )
    )
    batch = next(
        dataset.iter_window_batches(
            minimum_end=datetime(2023, 1, 8, 6, 0, tzinfo=SEOUL)
        )
    )

    assert len(tick.readings) == 31
    assert tick.readings[0].values["sensor_1"] is None
    assert batch.records[0].context["configuration_type"] == "space_heating"
    assert batch.records[0].feature_values == {
        "sensor_1__mean": 0.1,
        "sensor_2__mean": 1.1,
        "sensor_3__mean": 2.1,
        "sensor_4__mean": 3.1,
        "has_buffer_tank": 0.0,
    }


@pytest.mark.anyio
async def test_csv_dataset_and_service_integrate_through_first_scored_window(
    tmp_path: Path,
) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "windows").mkdir()
    sensor_fields = [
        "sensor_key",
        "source_column",
        "label_ko",
        "unit",
        "display_order",
        "sensor_type",
        "model_feature_prefix",
        "nullable",
        "enabled",
    ]
    with (tmp_path / "sensor_manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=sensor_fields)
        writer.writeheader()
        for index in range(1, 5):
            writer.writerow(
                {
                    "sensor_key": f"sensor_{index}",
                    "source_column": f"sensor_{index}",
                    "label_ko": f"sensor {index}",
                    "unit": "unit",
                    "display_order": index,
                    "sensor_type": "temperature",
                    "model_feature_prefix": f"sensor_{index}__",
                    "nullable": "false",
                    "enabled": "true",
                }
            )

    raw_fields = [
        "dataset_version",
        "sequence",
        "phase",
        "simulated_at",
        "manufacturer_id",
        "substation_id",
        "sensor_1",
        "sensor_2",
        "sensor_3",
        "sensor_4",
        "quality_flag",
        "is_synthetic",
        "scenario_id",
    ]
    warmup_start = datetime(2023, 1, 1, tzinfo=SEOUL)
    with (tmp_path / "raw" / "2023-01.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=raw_fields)
        writer.writeheader()
        for sequence in range(1008 + 36):
            at = warmup_start + timedelta(minutes=10 * sequence)
            for station in range(1, 32):
                writer.writerow(
                    {
                        "dataset_version": "pytest-integration-v1",
                        "sequence": sequence,
                        "phase": "warmup" if sequence < 1008 else "replay",
                        "simulated_at": at.isoformat(),
                        "manufacturer_id": "manufacturer 1",
                        "substation_id": station,
                        "sensor_1": station + sequence / 1000,
                        "sensor_2": station + 1 + sequence / 1000,
                        "sensor_3": station + 2 + sequence / 1000,
                        "sensor_4": station + 3 + sequence / 1000,
                        "quality_flag": "synthetic",
                        "is_synthetic": "true",
                        "scenario_id": "",
                    }
                )

    window_fields = [
        "dataset_version",
        "sequence_end",
        "phase",
        "manufacturer_id",
        "substation_id",
        "configuration_type",
        "window_start",
        "window_end",
        "expected_count",
        "observed_count",
        "feature_set_version",
        "feature_hash",
        "scenario_id",
        "sensor_1__mean",
        "sensor_2__mean",
        "sensor_3__mean",
        "sensor_4__mean",
    ]
    with (tmp_path / "windows" / "2023-01.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=window_fields)
        writer.writeheader()
        for station in range(1, 32):
            writer.writerow(
                {
                    "dataset_version": "pytest-integration-v1",
                    "sequence_end": 1043,
                    "phase": "replay",
                    "manufacturer_id": "manufacturer 1",
                    "substation_id": station,
                    "configuration_type": "space_heating",
                    "window_start": "2023-01-08T00:00:00+09:00",
                    "window_end": "2023-01-08T06:00:00+09:00",
                    "expected_count": 36,
                    "observed_count": 36,
                    "feature_set_version": "pytest-features-v1",
                    "feature_hash": f"hash-{station}",
                    "scenario_id": "",
                    "sensor_1__mean": station / 10,
                    "sensor_2__mean": station / 10 + 1,
                    "sensor_3__mean": station / 10 + 2,
                    "sensor_4__mean": station / 10 + 3,
                }
            )

    manifest = {
        "dataset_version": "pytest-integration-v1",
        "warmup_start": "2023-01-01T00:00:00+09:00",
        "replay_start": "2023-01-08T00:00:00+09:00",
        "replay_end": "2026-01-08T00:00:00+09:00",
        "expected_substations": 31,
        "source_interval_minutes": 10,
        "window_ticks": 36,
        "tick_seconds": 1,
        "sensor_manifest": "sensor_manifest.csv",
        "raw_shards": [
            {
                "path": "raw/2023-01.csv",
                "start": "2023-01-01T00:00:00+09:00",
                "end": "2023-01-08T06:00:00+09:00",
            }
        ],
        "window_shards": [
            {
                "path": "windows/2023-01.csv",
                "start": "2023-01-08T06:00:00+09:00",
                "end": "2023-01-08T12:00:00+09:00",
            }
        ],
    }
    (tmp_path / "dataset_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    dataset = CsvReplayDataset(tmp_path)
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    service = ReplayService(
        dataset=dataset,
        runtime=runtime,
        store=store,
        run_background=False,
    )
    await service.start()
    for _ in range(36):
        await service.advance_one_tick()

    assert len(service._history) == 1008
    assert runtime.call_count == 1
    assert runtime.batch_sizes == [31]
    assert service.current_simulated_at == datetime(2023, 1, 8, 5, 50, tzinfo=SEOUL)
    assert service.has_scored_window is True


def test_csv_reader_keeps_ten_minute_continuity_across_leap_month_boundary(
    tmp_path: Path,
) -> None:
    sensors = tuple(
        SensorDefinition(
            sensor_key=f"sensor_{index}",
            source_column=f"sensor_{index}",
            label_ko=f"sensor {index}",
            unit="unit",
            display_order=index,
            sensor_type="temperature",
            model_feature_prefix=f"sensor_{index}__",
            nullable=False,
        )
        for index in range(1, 5)
    )
    fields = [
        "dataset_version",
        "sequence",
        "phase",
        "simulated_at",
        "manufacturer_id",
        "substation_id",
        "sensor_1",
        "sensor_2",
        "sensor_3",
        "sensor_4",
        "quality_flag",
        "is_synthetic",
        "scenario_id",
    ]
    moments = (
        datetime(2024, 2, 29, 23, 50, tzinfo=SEOUL),
        datetime(2024, 3, 1, 0, 0, tzinfo=SEOUL),
    )
    shards: list[ReplayShard] = []
    for sequence, at in enumerate(moments, start=200_000):
        path = tmp_path / f"{at:%Y-%m}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for station in range(1, 32):
                writer.writerow(
                    {
                        "dataset_version": "pytest-leap-v1",
                        "sequence": sequence,
                        "phase": "replay",
                        "simulated_at": at.isoformat(),
                        "manufacturer_id": "manufacturer 1",
                        "substation_id": station,
                        "sensor_1": station,
                        "sensor_2": station + 1,
                        "sensor_3": station + 2,
                        "sensor_4": station + 3,
                        "quality_flag": "synthetic",
                        "is_synthetic": "true",
                        "scenario_id": "",
                    }
                )
        shards.append(
            ReplayShard(
                path=path,
                start=at,
                end=at + timedelta(minutes=10),
            )
        )

    dataset = object.__new__(CsvReplayDataset)
    dataset.root = tmp_path
    dataset.sensors = sensors
    dataset.manifest = ReplayManifest(
        dataset_version="pytest-leap-v1",
        warmup_start=datetime(2023, 1, 1, tzinfo=SEOUL),
        replay_start=datetime(2023, 1, 8, tzinfo=SEOUL),
        replay_end=datetime(2026, 1, 8, tzinfo=SEOUL),
        expected_substations=31,
        source_interval_minutes=10,
        window_ticks=36,
        tick_seconds=1,
        raw_shards=tuple(shards),
        window_shards=(),
    )

    ticks = list(
        dataset.iter_raw_ticks(
            start=moments[0],
            end=moments[1] + timedelta(minutes=10),
        )
    )
    assert [tick.simulated_at for tick in ticks] == list(moments)
    assert all(len(tick.readings) == 31 for tick in ticks)
