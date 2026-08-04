from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from simulator.versions.v2_postgres_react_ops.backend.replay_dataset import (
    SensorTick,
    WindowBatch,
)
from simulator.versions.v2_postgres_react_ops.backend.replay_worker import (
    MemoryReplayStore,
    ReplayWorker,
)


UTC = timezone.utc
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = (
    REPOSITORY_ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)


@pytest.mark.parametrize(
    ("mode", "probe"),
    [
        pytest.param(
            "package",
            "from simulator.versions.v2_postgres_react_ops.backend."
            "replay_worker_main import ReplayWorkerProcess; "
            "print(ReplayWorkerProcess.__name__)",
            id="package",
        ),
        pytest.param(
            "direct-backend-path",
            f"import sys; sys.path.insert(0, {str(BACKEND_PATH)!r}); "
            "from replay_worker_main import ReplayWorkerProcess; "
            "print(ReplayWorkerProcess.__name__)",
            id="direct-backend-path",
        ),
    ],
)
def test_replay_worker_main_supports_import_mode(mode: str, probe: str) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert (result.returncode, result.stdout.strip()) == (0, "ReplayWorkerProcess"), (
        f"{mode} import failed: {result.stderr}"
    )


@dataclass(frozen=True, slots=True)
class FakeManifest:
    expected_substations: int = 31
    window_ticks: int = 36
    source_interval: timedelta = timedelta(minutes=10)


class FakeDataset:
    def __init__(self) -> None:
        self.manifest = FakeManifest()

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

    def infer_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls += 1
        return [{"priority_score": 0.5, "priority_level": "high"} for _ in rows]


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
async def test_replay_persists_every_tick_during_warmup() -> None:
    # Given
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker(
        run_id="run-1",
        dataset=FakeDataset(),
        runtime=runtime,
        store=store,
    )

    # When
    events = await worker.replay([_tick(sequence) for sequence in range(3)])

    # Then
    assert [tick.sequence for tick in store.ticks] == [0, 1, 2]
    assert [event["type"] for event in events] == ["replay.sensor_tick.v1"] * 3
    assert runtime.calls == 0


@pytest.mark.anyio
async def test_replay_infers_once_for_every_warmed_tick() -> None:
    runtime = FakeRuntime()
    store = MemoryReplayStore()
    worker = ReplayWorker(
        run_id="run-1",
        dataset=FakeDataset(),
        runtime=runtime,
        store=store,
    )

    events = await worker.replay([_tick(sequence) for sequence in range(72)])

    assert runtime.calls == 37
    assert len(store.scored) == 37
    assert [event["type"] for event in events].count("replay.window_scored.v1") == 37
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
