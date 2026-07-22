from __future__ import annotations

import asyncio
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from heatgrid_ops.priority.inference import PriorityInferenceRuntime
try:
    from .replay_dataset import CsvReplayDataset
    from .replay_repository import PostgresReplayStore
    from .replay_worker import ReplayWorker
    from .settings import Settings
except ImportError:
    from replay_dataset import CsvReplayDataset
    from replay_repository import PostgresReplayStore
    from replay_worker import ReplayWorker
    from settings import Settings


class ReplayWorkerProcess:
    def __init__(self, engine: AsyncEngine, *, owner: str) -> None:
        self.engine = engine
        self.owner = owner
        self.store = PostgresReplayStore(engine, lease_owner=owner)

    async def run_forever(self) -> None:
        while True:
            run = await self._claim_run()
            if run is None:
                await asyncio.sleep(0.5)
                continue
            try:
                await self._apply_commands(run)
                refreshed = await self._run(str(run["run_id"]))
            except Exception as error:
                await self._fail_run(str(run["run_id"]), error)
                await asyncio.sleep(0.1)
                continue
            if refreshed is None:
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(max(0.01, float(refreshed["tick_seconds"]) / float(refreshed["speed_multiplier"])))

    async def _claim_run(self) -> dict[str, Any] | None:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    "WITH recent_command AS ("
                    " SELECT run_id FROM replay_run_commands WHERE status = 'queued' "
                    " AND created_at >= now() - interval '5 minutes' "
                    " ORDER BY created_at DESC LIMIT 1"
                    ") SELECT r.run_id FROM replay_runs r LEFT JOIN recent_command c ON c.run_id = r.run_id "
                    "WHERE r.state IN ('ready', 'running', 'paused') "
                    "AND (r.lease_expires_at IS NULL OR r.lease_expires_at < now() OR r.lease_owner = :owner) "
                    "ORDER BY CASE WHEN c.run_id IS NOT NULL THEN 0 "
                    "WHEN r.state = 'running' AND r.lease_owner = :owner THEN 1 "
                    "WHEN r.state = 'running' THEN 2 ELSE 3 END, r.updated_at DESC "
                    "FOR UPDATE OF r SKIP LOCKED LIMIT 1"
                ),
                {"owner": self.owner},
            )
            run_id = result.scalar_one_or_none()
            if run_id is None:
                return None
            row = await connection.execute(
                text(
                    "UPDATE replay_runs SET lease_owner = :owner, lease_expires_at = now() + interval '15 seconds', "
                    "heartbeat_at = now(), updated_at = now() WHERE run_id = :run_id "
                    "RETURNING run_id, state, current_simulated_at, start_at, tick_seconds, speed_multiplier"
                ),
                {"owner": self.owner, "run_id": run_id},
            )
        return dict(row.mappings().one())

    async def _apply_commands(self, run: dict[str, Any]) -> None:
        async with self.engine.begin() as connection:
            commands = await connection.execute(
                text(
                    "SELECT command_id, command_type, expected_run_version, payload FROM replay_run_commands "
                    "WHERE run_id = :run_id AND status = 'queued' ORDER BY created_at FOR UPDATE SKIP LOCKED"
                ),
                {"run_id": run["run_id"]},
            )
            for command in commands.mappings().all():
                state = await connection.execute(
                    text("SELECT version FROM replay_runs WHERE run_id = :run_id FOR UPDATE"),
                    {"run_id": run["run_id"]},
                )
                version = state.scalar_one()
                if int(version) != int(command["expected_run_version"]):
                    await connection.execute(
                        text("UPDATE replay_run_commands SET status = 'rejected', error = 'run version conflict', applied_at = now() WHERE command_id = :command_id"),
                        {"command_id": command["command_id"]},
                    )
                    continue
                updates = _command_updates(str(command["command_type"]), command["payload"])
                await connection.execute(
                    text(
                        "UPDATE replay_runs SET state = :state, start_at = COALESCE(:start_at, start_at), "
                        "current_simulated_at = CASE WHEN :reset_cursor THEN NULL ELSE current_simulated_at END, "
                        "cursor = CASE WHEN :reset_cursor THEN 0 ELSE cursor END, version = version + 1, "
                        "speed_multiplier = COALESCE(:speed_multiplier, speed_multiplier), "
                        "updated_at = now() WHERE run_id = :run_id"
                    ),
                    {"run_id": run["run_id"], **updates},
                )
                await connection.execute(
                    text("UPDATE replay_run_commands SET status = 'applied', claimed_by = :owner, applied_at = now() WHERE command_id = :command_id"),
                    {"owner": self.owner, "command_id": command["command_id"]},
                )

    async def _run(self, run_id: str) -> dict[str, Any] | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT r.run_id, r.state, r.start_at, r.current_simulated_at, r.tick_seconds, "
                    "r.speed_multiplier, d.extracted_root, d.replay_end FROM replay_runs r "
                    "JOIN replay_datasets d ON d.dataset_id = r.dataset_id WHERE r.run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            row = result.mappings().one()
        if row["state"] != "running":
            return None
        dataset = CsvReplayDataset(row["extracted_root"])
        next_at = row["start_at"] if row["current_simulated_at"] is None else row["current_simulated_at"] + dataset.manifest.source_interval
        iterator = dataset.iter_raw_ticks(start=next_at, end=dataset.manifest.replay_end)
        tick = next(iterator, None)
        if tick is None:
            await self._complete(run_id)
            return None
        runtime = PriorityInferenceRuntime(deployment_version="active-priority-contract-v1")
        await ReplayWorker(run_id=run_id, dataset=dataset, runtime=runtime, store=self.store).advance_tick(tick)
        return dict(row)

    async def _complete(self, run_id: str) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text("UPDATE replay_runs SET state = 'completed', completed_at = now(), updated_at = now() WHERE run_id = :run_id"),
                {"run_id": run_id},
            )

    async def _fail_run(self, run_id: str, error: Exception) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE replay_runs SET state = 'error', error_code = :error_code, "
                    "error_detail = :error_detail, lease_owner = NULL, lease_expires_at = NULL, "
                    "updated_at = now() WHERE run_id = :run_id"
                ),
                {
                    "run_id": run_id,
                    "error_code": type(error).__name__,
                    "error_detail": str(error)[:4000],
                },
            )


def _command_updates(command_type: str, payload: object) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    if command_type in {"start", "resume"}:
        return {"state": "running", "start_at": None, "reset_cursor": False, "speed_multiplier": None}
    if command_type == "pause":
        return {"state": "paused", "start_at": None, "reset_cursor": False, "speed_multiplier": None}
    if command_type == "cancel":
        return {"state": "cancelled", "start_at": None, "reset_cursor": False, "speed_multiplier": None}
    if command_type == "reset":
        return {"state": "ready", "start_at": None, "reset_cursor": True, "speed_multiplier": None}
    if command_type == "seek":
        target = body.get("simulated_at")
        if not isinstance(target, str):
            raise ValueError("seek requires payload.simulated_at")
        return {"state": "ready", "start_at": target, "reset_cursor": True, "speed_multiplier": None}
    if command_type == "set_speed":
        speed = body.get("speed_multiplier")
        if not isinstance(speed, (int, float)) or speed <= 0:
            raise ValueError("set_speed requires a positive payload.speed_multiplier")
        return {"state": "paused", "start_at": None, "reset_cursor": False, "speed_multiplier": float(speed)}
    raise ValueError(f"unsupported replay command: {command_type}")


def main() -> None:
    settings = Settings()
    worker_id = os.environ.get("HEATGRID_REPLAY_WORKER_ID", "heatgrid-replay-worker")
    asyncio.run(
        ReplayWorkerProcess(
            create_async_engine(settings.database_url, pool_pre_ping=True),
            owner=worker_id,
        ).run_forever()
    )


if __name__ == "__main__":
    main()
