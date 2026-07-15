from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

from replay_dataset import SensorTick, WindowBatch  # noqa: E402
from replay_worker import MemoryReplayStore, ReplayWorker  # noqa: E402


UTC = timezone.utc


class FakeDataset:
    def __init__(self) -> None:
        self.manifest = SimpleNamespace(
            expected_substations=31,
            window_ticks=36,
            source_interval=timedelta(minutes=10),
        )

    def window_batch(self, window_end: datetime) -> WindowBatch:
        start = window_end - timedelta(hours=6)
        return WindowBatch(
            start,
            window_end,
            tuple(
                {
                    "manufacturer_id": "manufacturer 1",
                    "substation_id": substation_id,
                    "window_start": start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "feature_set_version": "test",
                    "feature_values": {"outdoor_temperature__mean": 1.0},
                }
                for substation_id in range(1, 32)
            ),
        )


class FakeRuntime:
    model_version = "test-model"

    def __init__(self) -> None:
        self.calls = 0

    def infer_batch(self, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls += 1
        return [{"priority_score": 0.5, "priority_level": "high"} for _ in inputs]


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
async def test_replay_infers_exactly_once_per_36_ticks() -> None:
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker(
        run_id="run-1",
        dataset=FakeDataset(),
        runtime=runtime,
        store=store,
    )

    events = await worker.replay([_tick(sequence) for sequence in range(72)])

    assert runtime.calls == 2
    assert len(store.scored) == 2
    assert [event["type"] for event in events].count("replay.window_scored.v1") == 2
    assert {event["window_end"] for event in store.events if event["event_type"] == "replay.window_scored.v1"}


@pytest.mark.anyio
async def test_replaying_a_boundary_tick_does_not_infer_again() -> None:
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker(
        run_id="run-1",
        dataset=FakeDataset(),
        runtime=runtime,
        store=store,
    )

    await worker.replay([_tick(sequence) for sequence in range(36)])
    await worker.advance_tick(_tick(35))

    assert runtime.calls == 1
    assert len(store.scored) == 1
