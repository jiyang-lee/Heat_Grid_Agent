from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import count
from typing import Any, Protocol

import orjson
from anyio import sleep
from anyio.to_thread import run_sync

try:
    from .replay_dataset import ReplayDatasetError, SensorTick, WindowBatch
except ImportError:
    from replay_dataset import ReplayDatasetError, SensorTick, WindowBatch


class ReplayWorkerError(RuntimeError):
    pass


class ReplayStore(Protocol):
    async def persist_tick(self, *, run_id: str, tick: SensorTick) -> int | None: ...

    async def begin_window(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        model_version: str,
        input_hash: str,
    ) -> bool: ...

    async def complete_window(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        model_version: str,
        input_hash: str,
        results: list[dict[str, Any]],
        inference_duration_ms: int,
    ) -> dict[str, Any]: ...

    async def fail_window(self, *, run_id: str, window_end: datetime, error: str) -> None: ...


class InferenceRuntime(Protocol):
    model_version: str

    def infer_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class ReplayManifestView(Protocol):
    @property
    def expected_substations(self) -> int: ...

    @property
    def source_interval(self) -> timedelta: ...

    @property
    def window_ticks(self) -> int: ...


class ReplayDataset(Protocol):
    @property
    def manifest(self) -> ReplayManifestView: ...

    def window_batch(self, window_end: datetime) -> WindowBatch: ...


@dataclass(frozen=True, slots=True)
class ReplayWorker:
    run_id: str
    dataset: ReplayDataset
    runtime: InferenceRuntime
    store: ReplayStore

    async def advance_tick(self, tick: SensorTick) -> dict[str, Any] | None:
        if len(tick.readings) != self.dataset.manifest.expected_substations:
            raise ReplayWorkerError("a replay tick must contain 31 substations")
        event_id = await self.store.persist_tick(run_id=self.run_id, tick=tick)
        if event_id is None:
            return None
        if tick.sequence < self.dataset.manifest.window_ticks - 1:
            return {"event_id": event_id, "type": "replay.sensor_tick.v1"}
        window_end = tick.simulated_at + self.dataset.manifest.source_interval
        try:
            batch = self.dataset.window_batch(window_end)
        except ReplayDatasetError as exc:
            raise ReplayWorkerError(str(exc)) from exc
        if len(batch.records) != self.dataset.manifest.expected_substations:
            raise ReplayWorkerError("a replay score window must contain 31 substations")
        inputs = [_inference_input(record) for record in batch.records]
        input_hash = _hash(inputs)
        started = await self.store.begin_window(
            run_id=self.run_id,
            batch=batch,
            model_version=self.runtime.model_version,
            input_hash=input_hash,
        )
        if not started:
            return None
        started_at = time.perf_counter()
        try:
            results = await run_sync(self.runtime.infer_batch, inputs)
            if len(results) != len(inputs):
                raise ReplayWorkerError(
                    f"inference returned {len(results)} records for {len(inputs)} substations"
                )
            completed = await self.store.complete_window(
                run_id=self.run_id,
                batch=batch,
                model_version=self.runtime.model_version,
                input_hash=input_hash,
                results=results,
                inference_duration_ms=round((time.perf_counter() - started_at) * 1000),
            )
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            await self.store.fail_window(
                run_id=self.run_id,
                window_end=window_end,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        return {"event_id": event_id, "type": "replay.window_scored.v1", **completed}

    async def replay(self, ticks: list[SensorTick]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for tick in ticks:
            event = await self.advance_tick(tick)
            if event is not None:
                events.append(event)
        return events


@dataclass(frozen=True, slots=True)
class MemoryReplayStore:
    ticks: list[SensorTick] = field(default_factory=list)
    scored: dict[tuple[str, datetime], dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    _event_ids: count[int] = field(default_factory=count)
    _tick_event_ids: dict[tuple[str, int], int] = field(default_factory=dict)

    async def persist_tick(self, *, run_id: str, tick: SensorTick) -> int | None:
        key = (run_id, tick.sequence)
        existing_event_id = self._tick_event_ids.get(key)
        if existing_event_id is not None:
            return None
        self.ticks.append(tick)
        event_id = self._append_event(
            {
                "run_id": run_id,
                "event_type": "replay.sensor_tick.v1",
                "sequence": tick.sequence,
                "simulated_at": tick.simulated_at.isoformat(),
            }
        )
        self._tick_event_ids[key] = event_id
        return event_id

    async def begin_window(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        model_version: str,
        input_hash: str,
    ) -> bool:
        del model_version, input_hash
        key = (run_id, batch.window_end)
        if key in self.scored:
            return False
        self.scored[key] = {"status": "running"}
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
        payload = {
            "run_id": run_id,
            "window_start": batch.window_start.isoformat(),
            "window_end": batch.window_end.isoformat(),
            "model_version": model_version,
            "input_hash": input_hash,
            "result_hash": _hash(results),
            "result_count": len(results),
            "inference_duration_ms": inference_duration_ms,
        }
        self.scored[(run_id, batch.window_end)] = {"status": "completed", **payload}
        self._append_event({"event_type": "replay.window_scored.v1", **payload})
        return payload

    async def fail_window(self, *, run_id: str, window_end: datetime, error: str) -> None:
        self.scored[(run_id, window_end)] = {"status": "failed", "error": error}

    def _append_event(self, payload: dict[str, Any]) -> int:
        event_id = next(self._event_ids) + 1
        self.events.append({"event_id": event_id, **payload})
        return event_id


def _inference_input(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "manufacturer_id": record["manufacturer_id"],
        "substation_id": int(record["substation_id"]),
        "source_window_start": record["window_start"],
        "source_window_end": record["window_end"],
        "feature_set_version": record.get("feature_set_version"),
        "feature_values": record["feature_values"],
        "configuration_type": record.get("configuration_type"),
    }


def _hash(value: list[dict[str, Any]]) -> str:
    return hashlib.sha256(orjson.dumps(value, option=orjson.OPT_SORT_KEYS)).hexdigest()


async def run_worker_loop(
    *,
    claim_next: Callable[[], Awaitable[ReplayWorker | None]],
    heartbeat_seconds: float = 1.0,
) -> None:
    while True:
        worker = await claim_next()
        if worker is None:
            await sleep(heartbeat_seconds)
            continue
        await sleep(0)
