from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from replay_dataset import (
    ReplayManifest,
    SensorDefinition,
    SensorTick,
    WindowBatch,
    _aware,
)

ReplayState = str


class ReplayControlError(RuntimeError):
    pass


class ReplayDatasetPort(Protocol):
    manifest: ReplayManifest
    sensors: tuple[SensorDefinition, ...]

    def warmup_ticks(self, target: datetime) -> list[SensorTick]: ...

    def iter_raw_ticks(
        self,
        *,
        start: datetime,
        end: datetime | None = None,
    ) -> Iterator[SensorTick]: ...

    def iter_window_batches(self, *, minimum_end: datetime) -> Iterator[WindowBatch]: ...


class InferenceRuntimePort(Protocol):
    model_version: str

    def infer_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class ReplayStorePort(Protocol):
    async def load_recoverable_run(
        self,
        *,
        dataset_version: str,
    ) -> dict[str, Any] | None: ...

    async def create_run(
        self,
        *,
        run_id: str,
        manifest: ReplayManifest,
        start_at: datetime,
    ) -> None: ...

    async def update_run(
        self,
        *,
        run_id: str,
        state: ReplayState,
        cursor: int,
        current_simulated_at: datetime | None,
        error: str | None = None,
    ) -> None: ...

    async def persist_tick(self, *, run_id: str, tick: SensorTick) -> None: ...

    async def has_evaluation_for_window(
        self,
        *,
        run_id: str,
        window_end: datetime,
    ) -> bool: ...

    async def persist_scored_batch(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        inferences: list[dict[str, Any]],
        model_version: str,
    ) -> dict[str, Any]: ...


class MemoryReplayStore:
    """Test adapter and safe fallback when no PostgreSQL persistence is desired."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.ticks: list[SensorTick] = []
        self.scored_batches: list[WindowBatch] = []
        self.scored_window_ends: set[tuple[str, datetime]] = set()

    async def create_run(
        self,
        *,
        run_id: str,
        manifest: ReplayManifest,
        start_at: datetime,
    ) -> None:
        self.runs.append(
            {
                "run_id": run_id,
                "dataset_version": manifest.dataset_version,
                "start_at": start_at,
                "state": "running",
            }
        )

    async def load_recoverable_run(
        self,
        *,
        dataset_version: str,
    ) -> dict[str, Any] | None:
        for run in reversed(self.runs):
            if (
                run.get("dataset_version") == dataset_version
                and run.get("state") in {"running", "paused"}
            ):
                return dict(run)
        return None

    async def update_run(
        self,
        *,
        run_id: str,
        state: ReplayState,
        cursor: int,
        current_simulated_at: datetime | None,
        error: str | None = None,
    ) -> None:
        for run in reversed(self.runs):
            if run["run_id"] == run_id:
                run.update(
                    state=state,
                    cursor=cursor,
                    current_simulated_at=current_simulated_at,
                    error=error,
                )
                break

    async def persist_tick(self, *, run_id: str, tick: SensorTick) -> None:
        self.ticks.append(tick)
        for run in reversed(self.runs):
            if run["run_id"] == run_id:
                run["latest_readings"] = [
                    {
                        "manufacturer_id": reading.manufacturer_id,
                        "substation_id": reading.substation_id,
                        "simulated_at": reading.simulated_at.isoformat(),
                        "values": reading.values,
                        "quality": reading.quality,
                    }
                    for reading in tick.readings
                ]
                break

    async def has_evaluation_for_window(
        self,
        *,
        run_id: str,
        window_end: datetime,
    ) -> bool:
        return (run_id, window_end) in self.scored_window_ends

    async def persist_scored_batch(
        self,
        *,
        run_id: str,
        batch: WindowBatch,
        inferences: list[dict[str, Any]],
        model_version: str,
    ) -> dict[str, Any]:
        del model_version
        self.scored_batches.append(batch)
        self.scored_window_ends.add((run_id, batch.window_end))
        for run in reversed(self.runs):
            if run["run_id"] == run_id:
                run["has_scored_window"] = True
                break
        return {
            "evaluation_run_id": str(uuid4()),
            "results": _public_inference_results(batch, inferences),
        }


class ReplayEventBus:
    def __init__(self, *, queue_size: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._queue_size = queue_size
        self.event_log: deque[dict[str, Any]] = deque(maxlen=512)

    def publish(self, event: dict[str, Any]) -> None:
        self.event_log.append(event)
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    def open_subscription(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self._queue_size)
        self._subscribers.add(queue)
        return queue

    def close_subscription(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def subscribe(
        self,
        *,
        heartbeat_seconds: float = 15.0,
    ) -> AsyncIterator[dict[str, Any] | None]:
        queue = self.open_subscription()
        try:
            while True:
                try:
                    yield await asyncio.wait_for(
                        queue.get(),
                        timeout=heartbeat_seconds,
                    )
                except TimeoutError:
                    yield None
        finally:
            self.close_subscription(queue)


class ReplayService:
    def __init__(
        self,
        *,
        dataset: ReplayDatasetPort | None = None,
        runtime: InferenceRuntimePort | None = None,
        store: ReplayStorePort | None = None,
        tick_seconds: float | None = None,
        run_background: bool = True,
    ) -> None:
        self.dataset = dataset
        self.runtime = runtime
        self.store = store or MemoryReplayStore()
        self.tick_seconds = tick_seconds
        self.run_background = run_background
        self.events = ReplayEventBus()
        self.state: ReplayState = "disabled" if dataset is None else "paused"
        self.error: str | None = None
        self.run_id: str | None = None
        self.current_simulated_at: datetime | None = None
        self.window_progress = 0
        self.has_scored_window = False
        self._cursor = 0
        self._latest_readings: tuple[dict[str, Any], ...] = ()
        self._history: deque[SensorTick] = deque(maxlen=self._warmup_tick_count())
        self._raw_iterator: Iterator[SensorTick] | None = None
        self._window_iterator: Iterator[WindowBatch] | None = None
        self._next_window: WindowBatch | None = None
        self._task: asyncio.Task[None] | None = None
        self._resume = asyncio.Event()
        self._control_lock = asyncio.Lock()

    @classmethod
    def disabled(cls, error: str | None = None) -> ReplayService:
        service = cls()
        service.error = error
        return service

    def presets(self) -> list[dict[str, Any]]:
        if self.dataset is None:
            return []
        presets = list(getattr(self.dataset, "presets", ()))
        ranked = sorted(
            presets,
            key=lambda preset: (
                preset.fleet_high_count * 5 + preset.fleet_medium_count,
                preset.fleet_high_count,
                preset.fleet_max_priority_score,
            ),
            reverse=True,
        )
        selected = [
            preset
            for label in ("pre_fault_demo", "medium_warning_demo")
            for preset in [item for item in ranked if item.label == label][:6]
        ]
        return [preset.as_dict() for preset in selected]

    def configure(
        self,
        *,
        dataset: ReplayDatasetPort,
        runtime: InferenceRuntimePort,
        store: ReplayStorePort,
        tick_seconds: float | None = None,
    ) -> None:
        if self._task is not None and not self._task.done():
            raise ReplayControlError("cannot configure replay while it is running")
        self.dataset = dataset
        self.runtime = runtime
        self.store = store
        self.tick_seconds = tick_seconds
        self.state = "paused"
        self.error = None
        self._history = deque(maxlen=self._warmup_tick_count())

    async def shutdown(self) -> None:
        await self._cancel_task()

    async def restore(self) -> bool:
        """Restore an interrupted run at its next tick and keep it paused."""
        self._require_configured()
        candidate = await self.store.load_recoverable_run(
            dataset_version=self.dataset.manifest.dataset_version,
        )
        if candidate is None:
            return False
        current = candidate.get("current_simulated_at")
        if isinstance(current, str):
            current = datetime.fromisoformat(current.replace("Z", "+00:00"))
        current = None if current is None else _aware(current)
        start_at = candidate["start_at"]
        if isinstance(start_at, str):
            start_at = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        start_at = _aware(start_at)
        recovered_cursor = int(candidate.get("cursor") or 0)
        latest_readings = candidate.get("latest_readings") or []
        if latest_readings:
            latest_at = latest_readings[0].get("simulated_at")
            if isinstance(latest_at, str):
                latest_at = datetime.fromisoformat(latest_at.replace("Z", "+00:00"))
            if isinstance(latest_at, datetime):
                latest_at = _aware(latest_at)
                if current is None or latest_at > current:
                    current = latest_at
                    recovered_cursor = max(
                        recovered_cursor,
                        int(
                            (latest_at - start_at)
                            / self.dataset.manifest.source_interval
                        )
                        + 1,
                    )
        target = (
            start_at
            if current is None
            else current + self.dataset.manifest.source_interval
        )
        run_id = str(candidate["run_id"])
        recovery_window_end = await self._missing_recovery_window_end(
            run_id=run_id,
            current=current,
        )
        try:
            await self._prepare(
                target,
                existing_run={
                    "run_id": run_id,
                    "cursor": recovered_cursor,
                    "current_simulated_at": current,
                    "has_scored_window": bool(candidate.get("has_scored_window")),
                    "latest_readings": candidate.get("latest_readings") or [],
                },
            )
            if recovery_window_end is not None:
                await self._recover_window_score(recovery_window_end)
        except Exception as exc:
            await self.store.update_run(
                run_id=run_id,
                state="error",
                cursor=recovered_cursor,
                current_simulated_at=current,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        if target >= self.dataset.manifest.replay_end:
            self.state = "completed"
            await self._persist_state()
            return False
        self.state = "paused"
        await self._persist_state()
        return True

    async def control(
        self,
        action: str,
        *,
        simulated_at: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = action.strip().lower()
        if normalized == "start":
            await self.start()
        elif normalized == "pause":
            await self.pause()
        elif normalized == "resume":
            await self.resume()
        elif normalized == "reset":
            await self.reset()
        elif normalized == "seek":
            if simulated_at is None:
                raise ReplayControlError("seek requires simulated_at")
            await self.seek(simulated_at)
        else:
            raise ReplayControlError(f"unsupported replay action: {action}")
        return self.status()

    async def start(self) -> None:
        self._require_configured()
        async with self._control_lock:
            if self.state == "running":
                return
            if self.current_simulated_at is None or self._raw_iterator is None:
                await self._prepare_for_control(self.dataset.manifest.replay_start)
            self.state = "running"
            self.error = None
            self._resume.set()
            await self._persist_state()
            self._publish_state()
            self._spawn_task()

    async def pause(self) -> None:
        self._require_configured()
        async with self._control_lock:
            if self.state != "running":
                raise ReplayControlError("replay can only be paused while running")
            self.state = "paused"
            self._resume.clear()
            await self._persist_state()
            self._publish_state()

    async def resume(self) -> None:
        self._require_configured()
        async with self._control_lock:
            if self.state != "paused" or self._raw_iterator is None:
                raise ReplayControlError("paused replay has not been started")
            self.state = "running"
            self._resume.set()
            await self._persist_state()
            self._publish_state()
            self._spawn_task()

    async def reset(self) -> None:
        self._require_configured()
        async with self._control_lock:
            await self._cancel_task()
            previous_run = self.run_id
            previous_cursor = self._cursor
            previous_at = self.current_simulated_at
            self._clear_cursor()
            self.state = "paused"
            if previous_run is not None:
                await self.store.update_run(
                    run_id=previous_run,
                    state="reset",
                    cursor=previous_cursor,
                    current_simulated_at=previous_at,
                )
            self._publish_state()

    async def seek(self, simulated_at: datetime) -> None:
        self._require_configured()
        target = _aware(simulated_at)
        self._validate_seek(target)
        async with self._control_lock:
            await self._cancel_task()
            previous_run = self.run_id
            if previous_run is not None:
                await self.store.update_run(
                    run_id=previous_run,
                    state="superseded",
                    cursor=self._cursor,
                    current_simulated_at=self.current_simulated_at,
                )
            await self._prepare_for_control(target)
            self.state = "running"
            self._resume.set()
            await self._persist_state()
            self._publish_state()
            self._spawn_task()

    async def advance_one_tick(self) -> bool:
        """Advance once; public to support deterministic service tests."""
        self._require_configured()
        if self.state != "running":
            raise ReplayControlError("replay is not running")
        if self._raw_iterator is None:
            raise ReplayControlError("replay cursor is not prepared")
        try:
            tick = next(self._raw_iterator)
        except StopIteration:
            await self._complete()
            return False
        if tick.simulated_at >= self.dataset.manifest.replay_end:
            await self._complete()
            return False
        try:
            await self.store.persist_tick(run_id=self._required_run_id(), tick=tick)
            self._cursor += 1
            self.window_progress += 1
            self.current_simulated_at = tick.simulated_at
            self._history.append(tick)
            self._latest_readings = tuple(
                {
                    "manufacturer_id": reading.manufacturer_id,
                    "substation_id": reading.substation_id,
                    "simulated_at": tick.simulated_at.isoformat(),
                    "values": reading.values,
                    "quality": reading.quality,
                }
                for reading in tick.readings
            )
            self.events.publish(self._sensor_tick_event(tick))
            if self.window_progress == self.dataset.manifest.window_ticks:
                await self._score_window(tick.simulated_at + self.dataset.manifest.source_interval)
                self.window_progress = 0
            await self._persist_state()
            return True
        except Exception as exc:
            await self._fail(exc)
            raise

    def status(self) -> dict[str, Any]:
        sensors = [] if self.dataset is None else [item.as_dict() for item in self.dataset.sensors]
        return {
            "state": self.state,
            "dataset_version": None
            if self.dataset is None
            else self.dataset.manifest.dataset_version,
            "current_simulated_at": None
            if self.current_simulated_at is None
            else self.current_simulated_at.isoformat(),
            "window_progress": self.window_progress,
            "total_progress": self._total_progress(),
            "sensors": sensors,
            "has_scored_window": self.has_scored_window,
            "error": self.error,
        }

    def snapshot(self) -> dict[str, Any]:
        return {**self.status(), "readings": list(self._latest_readings)}

    async def _prepare(
        self,
        target: datetime,
        *,
        existing_run: dict[str, Any] | None = None,
    ) -> None:
        warmup = await asyncio.to_thread(self.dataset.warmup_ticks, target)
        required = self._warmup_tick_count()
        if len(warmup) != required:
            raise ReplayControlError(
                f"seek warmup has {len(warmup)} ticks; expected {required}"
            )
        if any(tick.phase not in {"warmup", "replay"} for tick in warmup):
            raise ReplayControlError("warmup contains an unsupported phase")
        self._clear_cursor()
        self._history.extend(warmup)
        self.window_progress = self._window_progress_before(target)
        self._raw_iterator = self.dataset.iter_raw_ticks(
            start=target,
            end=self.dataset.manifest.replay_end,
        )
        next_end = self._next_window_end(target)
        self._window_iterator = self.dataset.iter_window_batches(minimum_end=next_end)
        self._next_window = None
        if existing_run is None:
            self.run_id = str(uuid4())
            await self.store.create_run(
                run_id=self.run_id,
                manifest=self.dataset.manifest,
                start_at=target,
            )
        else:
            self.run_id = str(existing_run["run_id"])
            self._cursor = int(existing_run.get("cursor") or 0)
            self.current_simulated_at = existing_run.get("current_simulated_at")
            self.has_scored_window = bool(existing_run.get("has_scored_window"))
            self._latest_readings = tuple(existing_run.get("latest_readings") or ())

    async def _prepare_for_control(self, target: datetime) -> None:
        try:
            await self._prepare(target)
        except Exception as exc:
            self._clear_cursor()
            self.state = "error"
            self.error = f"{type(exc).__name__}: {exc}"
            self.events.publish({"type": "error", "message": self.error})
            self._publish_state()
            raise ReplayControlError(self.error) from exc

    async def _score_window(self, expected_end: datetime) -> None:
        batch = self._take_window_batch(expected_end)
        await self._score_batch(batch)

    async def _score_batch(self, batch: WindowBatch) -> None:
        inputs = [record.inference_input() for record in batch.records]
        inferences = await asyncio.to_thread(self.runtime.infer_batch, inputs)
        if len(inferences) != len(batch.records):
            raise ReplayControlError(
                f"inference returned {len(inferences)} results for {len(batch.records)} rows"
            )
        stored = await self.store.persist_scored_batch(
            run_id=self._required_run_id(),
            batch=batch,
            inferences=inferences,
            model_version=self.runtime.model_version,
        )
        self.has_scored_window = True
        self.events.publish(
            {
                "type": "window_scored",
                "run_id": self.run_id,
                "dataset_version": self.dataset.manifest.dataset_version,
                "evaluation_run_id": stored.get("evaluation_run_id"),
                "window_start": batch.window_start.isoformat(),
                "window_end": batch.window_end.isoformat(),
                "result_count": len(inferences),
                "results": stored.get("results")
                or _public_inference_results(batch, inferences),
            }
        )

    async def _missing_recovery_window_end(
        self,
        *,
        run_id: str,
        current: datetime | None,
    ) -> datetime | None:
        if current is None:
            return None
        expected_end = current + self.dataset.manifest.source_interval
        if self._window_progress_before(expected_end) != 0:
            return None
        if not self.dataset.manifest.replay_start < expected_end <= self.dataset.manifest.replay_end:
            return None
        if await self.store.has_evaluation_for_window(
            run_id=run_id,
            window_end=expected_end,
        ):
            return None
        return expected_end

    async def _recover_window_score(self, expected_end: datetime) -> None:
        iterator = self.dataset.iter_window_batches(minimum_end=expected_end)
        try:
            batch = next(iterator)
        except StopIteration as exc:
            raise ReplayControlError(
                f"window CSV has no recovery batch ending at {expected_end.isoformat()}"
            ) from exc
        if batch.window_end != expected_end:
            raise ReplayControlError(
                f"window CSV recovery expected end {expected_end.isoformat()}, got "
                f"{batch.window_end.isoformat()}"
            )
        await self._score_batch(batch)

    def _take_window_batch(self, expected_end: datetime) -> WindowBatch:
        if self._window_iterator is None:
            raise ReplayControlError("window cursor is not prepared")
        batch = self._next_window
        if batch is None:
            try:
                batch = next(self._window_iterator)
            except StopIteration as exc:
                raise ReplayControlError(
                    f"window CSV has no batch ending at {expected_end.isoformat()}"
                ) from exc
        while batch.window_end < expected_end:
            try:
                batch = next(self._window_iterator)
            except StopIteration as exc:
                raise ReplayControlError(
                    f"window CSV has no batch ending at {expected_end.isoformat()}"
                ) from exc
        self._next_window = None
        if batch.window_end != expected_end:
            self._next_window = batch
            raise ReplayControlError(
                f"window CSV expected end {expected_end.isoformat()}, got "
                f"{batch.window_end.isoformat()}"
            )
        return batch

    async def _run_loop(self) -> None:
        interval = self.tick_seconds or self.dataset.manifest.tick_seconds
        clock = asyncio.get_running_loop()
        next_deadline = clock.time() + interval
        try:
            while self.state in {"running", "paused"}:
                if self.state == "paused":
                    await self._resume.wait()
                    next_deadline = clock.time() + interval
                if self.state != "running":
                    continue
                await asyncio.sleep(max(0.0, next_deadline - clock.time()))
                if self.state != "running":
                    continue
                advanced = await self.advance_one_tick()
                if not advanced:
                    return
                next_deadline += interval
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    def _spawn_task(self) -> None:
        if not self.run_background:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop(), name="heatgrid-demo-replay")

    async def _cancel_task(self) -> None:
        task = self._task
        self._task = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _complete(self) -> None:
        self.state = "completed"
        self._resume.clear()
        await self._persist_state()
        self._publish_state()

    async def _fail(self, exc: Exception) -> None:
        self.state = "error"
        self.error = f"{type(exc).__name__}: {exc}"
        self._resume.clear()
        await self._persist_state()
        self.events.publish({"type": "error", "message": self.error})
        self._publish_state()

    async def _persist_state(self) -> None:
        if self.run_id is None:
            return
        await self.store.update_run(
            run_id=self.run_id,
            state=self.state,
            cursor=self._cursor,
            current_simulated_at=self.current_simulated_at,
            error=self.error,
        )

    def _publish_state(self) -> None:
        self.events.publish({"type": "replay_state", **self.status()})

    def _sensor_tick_event(self, tick: SensorTick) -> dict[str, Any]:
        return {
            "type": "sensor_tick",
            "run_id": self.run_id,
            "dataset_version": self.dataset.manifest.dataset_version,
            "simulated_at": tick.simulated_at.isoformat(),
            "window_progress": self.window_progress,
            "total_progress": self._total_progress(tick.simulated_at),
            "readings": list(self._latest_readings),
        }

    def _window_progress_before(self, target: datetime) -> int:
        interval = self.dataset.manifest.source_interval
        seconds = (
            target.hour * 3600 + target.minute * 60 + target.second
        ) % int(self.dataset.manifest.window_duration.total_seconds())
        return int(seconds // interval.total_seconds())

    def _next_window_end(self, target: datetime) -> datetime:
        progress = self._window_progress_before(target)
        remaining = self.dataset.manifest.window_ticks - progress
        return target + self.dataset.manifest.source_interval * remaining

    def _warmup_tick_count(self) -> int:
        if self.dataset is None:
            return 1008
        return int(timedelta(days=7) / self.dataset.manifest.source_interval)

    def _validate_seek(self, target: datetime) -> None:
        manifest = self.dataset.manifest
        if not manifest.replay_start <= target < manifest.replay_end:
            raise ReplayControlError(
                "seek target must be inside [replay_start, replay_end)"
            )
        offset = target - manifest.replay_start
        if offset % manifest.source_interval:
            raise ReplayControlError("seek target must align to a 10-minute source tick")

    def _total_progress(self, at: datetime | None = None) -> float:
        if self.dataset is None:
            return 0.0
        if self.state == "completed":
            return 1.0
        current = at or self.current_simulated_at
        if current is None:
            return 0.0
        manifest = self.dataset.manifest
        elapsed = max(0.0, (current - manifest.replay_start).total_seconds())
        total = (manifest.replay_end - manifest.replay_start).total_seconds()
        return round(min(1.0, elapsed / total), 8)

    def _clear_cursor(self) -> None:
        self.run_id = None
        self.current_simulated_at = None
        self.window_progress = 0
        self.has_scored_window = False
        self.error = None
        self._cursor = 0
        self._latest_readings = ()
        self._history.clear()
        self._raw_iterator = None
        self._window_iterator = None
        self._next_window = None
        self._resume.clear()

    def _require_configured(self) -> None:
        if self.dataset is None or self.runtime is None:
            raise ReplayControlError(self.error or "demo replay dataset is disabled")

    def _required_run_id(self) -> str:
        if self.run_id is None:
            raise ReplayControlError("replay run has not been created")
        return self.run_id


def _public_inference_results(
    batch: WindowBatch,
    inferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "manufacturer_id": record.manufacturer_id,
            "substation_id": record.substation_id,
            "priority_score": inference.get("priority_score"),
            "priority_level": inference.get("priority_level"),
            "risk_score": inference.get("risk_score"),
            "anomaly_score": inference.get("anomaly_score"),
            "anomaly_label": inference.get("anomaly_label"),
            "leadtime_bucket": inference.get("leadtime_bucket"),
        }
        for record, inference in zip(batch.records, inferences, strict=True)
    ]
