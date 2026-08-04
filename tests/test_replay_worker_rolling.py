from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

BACKEND = (
    Path(__file__).resolve().parents[1]
    / "simulator"
    / "versions"
    / "v2_postgres_react_ops"
    / "backend"
)
sys.path.insert(0, str(BACKEND))

from replay_dataset import ReplayDatasetError, SensorTick, WindowBatch  # noqa: E402
from replay_worker import MemoryReplayStore, ReplayWorker, ReplayWorkerError  # noqa: E402


@dataclass(frozen=True, slots=True)
class ModelUnavailableError(Exception):
    def __str__(self) -> str:
        return "model unavailable"


@dataclass(frozen=True, slots=True)
class RollingManifest:
    expected_substations: int = 31
    window_ticks: int = 36
    source_interval: timedelta = timedelta(minutes=10)


class RollingDataset:
    def __init__(self, *, incomplete_at: datetime | None = None) -> None:
        self.manifest = RollingManifest()
        self.incomplete_at = incomplete_at

    def window_batch(self, window_end: datetime) -> WindowBatch:
        if window_end == self.incomplete_at:
            raise ReplayDatasetError("rolling window is incomplete")
        window_start = window_end - timedelta(hours=6)
        return WindowBatch(
            window_start,
            window_end,
            tuple(
                {
                    "manufacturer_id": "manufacturer 1",
                    "substation_id": substation_id,
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "feature_set_version": "test",
                    "feature_values": {"outdoor_temperature__mean": 1.0},
                }
                for substation_id in range(1, 32)
            ),
        )


class RecordingRuntime:
    model_version = "test-model"

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call

    def infer_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise ModelUnavailableError
        return [
            {"priority_score": 0.5, "priority_level": "high"}
            for _ in rows
        ]


def _tick(sequence: int) -> SensorTick:
    simulated_at = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=10 * sequence)
    return SensorTick(
        sequence=sequence,
        phase="replay",
        simulated_at=simulated_at,
        readings=tuple(
            {
                "manufacturer_id": "manufacturer 1",
                "substation_id": substation_id,
                "values": {"outdoor_temperature": 1.0},
                "quality": {"outdoor_temperature": "synthetic"},
            }
            for substation_id in range(1, 32)
        ),
    )


@pytest.mark.anyio
async def test_scores_each_unique_tick_after_35_tick_warmup() -> None:
    # Given
    runtime = RecordingRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker("run-1", RollingDataset(), runtime, store)

    # When
    events = await worker.replay([_tick(sequence) for sequence in range(40)])

    # Then
    assert runtime.calls == 5
    assert len(store.ticks) == 40
    assert len(store.scored) == 5
    assert [event["type"] for event in events[:35]] == ["replay.sensor_tick.v1"] * 35
    assert [event["type"] for event in events[35:]] == ["replay.window_scored.v1"] * 5


@pytest.mark.anyio
async def test_duplicate_tick_and_restart_do_not_repeat_persistence_or_inference() -> None:
    # Given
    runtime = RecordingRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker("run-1", RollingDataset(), runtime, store)
    await worker.replay([_tick(sequence) for sequence in range(40)])
    original_events = tuple(store.events)

    # When
    duplicate = await worker.advance_tick(_tick(39))
    restarted_worker = ReplayWorker("run-1", RollingDataset(), runtime, store)
    restarted_duplicate = await restarted_worker.advance_tick(_tick(39))

    # Then
    assert duplicate is None
    assert restarted_duplicate is None
    assert runtime.calls == 5
    assert len(store.scored) == 5
    assert tuple(store.events) == original_events


@pytest.mark.anyio
async def test_warmup_duplicate_and_restart_return_no_event() -> None:
    # Given
    runtime = RecordingRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker("run-1", RollingDataset(), runtime, store)
    await worker.replay([_tick(sequence) for sequence in range(11)])
    original_events = tuple(store.events)

    # When
    duplicate = await worker.advance_tick(_tick(10))
    restarted_duplicate = await ReplayWorker(
        "run-1", RollingDataset(), runtime, store
    ).advance_tick(_tick(10))

    # Then
    assert duplicate is None
    assert restarted_duplicate is None
    assert tuple(store.events) == original_events
    assert len(store.ticks) == 11
    assert runtime.calls == 0


@pytest.mark.anyio
async def test_failed_window_is_persisted_and_next_unique_tick_resumes_cadence() -> None:
    # Given
    runtime = RecordingRuntime(fail_on_call=1)
    store = MemoryReplayStore()
    worker = ReplayWorker("run-1", RollingDataset(), runtime, store)
    await worker.replay([_tick(sequence) for sequence in range(35)])

    # When
    with pytest.raises(ModelUnavailableError, match="model unavailable"):
        await worker.advance_tick(_tick(35))
    restarted_worker = ReplayWorker("run-1", RollingDataset(), runtime, store)
    duplicate = await restarted_worker.advance_tick(_tick(35))
    resumed = await restarted_worker.advance_tick(_tick(36))

    # Then
    failed_window_end = _tick(35).simulated_at + timedelta(minutes=10)
    assert store.scored[("run-1", failed_window_end)]["status"] == "failed"
    assert duplicate is None
    assert resumed is not None and resumed["type"] == "replay.window_scored.v1"
    assert runtime.calls == 2
    assert len(
        [event for event in store.events if event["event_type"] == "replay.window_scored.v1"]
    ) == 1


@pytest.mark.anyio
async def test_incomplete_warm_window_is_not_scored() -> None:
    # Given
    window_end = _tick(35).simulated_at + timedelta(minutes=10)
    runtime = RecordingRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker(
        "run-1",
        RollingDataset(incomplete_at=window_end),
        runtime,
        store,
    )
    await worker.replay([_tick(sequence) for sequence in range(35)])

    # When
    with pytest.raises(ReplayWorkerError, match="rolling window is incomplete"):
        await worker.advance_tick(_tick(35))

    # Then
    assert runtime.calls == 0
    assert store.scored == {}
    assert len(store.ticks) == 36
