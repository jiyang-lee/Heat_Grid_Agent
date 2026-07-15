from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import orjson
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

try:
    from .replay_dataset import ReplayDatasetError, import_replay_package
    from .replay_repository import ReplayConflictError, register_imported_dataset
except ImportError:
    from replay_dataset import ReplayDatasetError, import_replay_package
    from replay_repository import ReplayConflictError, register_imported_dataset


class ReplayImportRequest(BaseModel):
    package_path: str
    imported_by: str = Field(min_length=1, max_length=200)


class ReplayRunRequest(BaseModel):
    dataset_id: str
    start_at: datetime
    tick_seconds: float = Field(default=1.0, gt=0)
    requested_by: str = Field(min_length=1, max_length=200)


class ReplayCommandRequest(BaseModel):
    command_type: str
    expected_run_version: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


def make_replay_router(
    engine: AsyncEngine,
    *,
    storage_root: str,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["replay"])

    @router.get("/replay-datasets")
    async def list_datasets() -> list[dict[str, Any]]:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT dataset_id, dataset_version, status, expected_substations, "
                    "source_interval_seconds, window_ticks, replay_start, replay_end, validated_at "
                    "FROM replay_datasets ORDER BY created_at DESC"
                )
            )
        return [_row(row) for row in result.mappings().all()]

    @router.post("/replay-datasets/import", status_code=201)
    async def import_dataset(request: ReplayImportRequest) -> dict[str, Any]:
        try:
            package = await asyncio.to_thread(
                import_replay_package,
                request.package_path,
                destination_root=storage_root,
            )
            return await register_imported_dataset(
                engine,
                package,
                package_uri=str(Path(request.package_path).expanduser().resolve()),
                imported_by=request.imported_by,
            )
        except ReplayDatasetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/replay-runs", status_code=201)
    async def create_run(request: ReplayRunRequest) -> dict[str, Any]:
        run_id = str(uuid4())
        async with engine.begin() as connection:
            dataset = await connection.execute(
                text(
                    "SELECT dataset_version, replay_start, replay_end, window_ticks FROM replay_datasets "
                    "WHERE dataset_id = :dataset_id AND status = 'available' FOR SHARE"
                ),
                {"dataset_id": request.dataset_id},
            )
            row = dataset.mappings().one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="available replay dataset not found")
            if not row["replay_start"] <= request.start_at < row["replay_end"]:
                raise HTTPException(status_code=422, detail="start_at is outside the replay range")
            await connection.execute(
                text(
                    "INSERT INTO replay_runs (run_id, dataset_id, stream_key, state, start_at, "
                    "tick_seconds, requested_by) VALUES (:run_id, :dataset_id, :stream_key, 'ready', "
                    ":start_at, :tick_seconds, :requested_by)"
                ),
                {"run_id": run_id, "dataset_id": request.dataset_id, "stream_key": f"replay:{run_id}", "start_at": request.start_at, "tick_seconds": request.tick_seconds, "requested_by": request.requested_by},
            )
        return {"run_id": run_id, "stream_key": f"replay:{run_id}", "state": "ready", "version": 1}

    @router.get("/replay-runs/{run_id}/snapshot")
    async def snapshot(run_id: str) -> dict[str, Any]:
        async with engine.connect() as connection:
            run = await connection.execute(
                text(
                    "SELECT r.run_id, r.stream_key, r.state, r.version, r.current_simulated_at, "
                    "r.last_emitted_sequence, r.last_scored_window_end, r.last_evaluation_run_id, "
                    "r.speed_multiplier, r.tick_seconds, d.dataset_version, d.window_ticks "
                    "FROM replay_runs r JOIN replay_datasets d ON d.dataset_id = r.dataset_id "
                    "WHERE r.run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            row = run.mappings().one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="replay run not found")
            readings = await connection.execute(
                text(
                    "SELECT manufacturer_id, substation_id, sequence, simulated_at, values, quality "
                    "FROM replay_latest_readings WHERE run_id = :run_id ORDER BY substation_id"
                ),
                {"run_id": run_id},
            )
            last_event = await connection.execute(
                text("SELECT COALESCE(max(event_id), 0) FROM replay_stream_events WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        data = _row(row)
        sequence = data.get("last_emitted_sequence")
        data.update(
            {
                "last_event_id": int(last_event.scalar_one()),
                "window_progress": 0 if sequence is None else (int(sequence) + 1) % int(data["window_ticks"]),
                "synthetic": True,
                "readings": [_row(item) for item in readings.mappings().all()],
            }
        )
        return data

    @router.post("/replay-runs/{run_id}/commands", status_code=202)
    async def enqueue_command(run_id: str, request: ReplayCommandRequest) -> dict[str, Any]:
        valid = {"start", "pause", "resume", "reset", "seek", "set_speed", "cancel"}
        if request.command_type not in valid:
            raise HTTPException(status_code=422, detail="unsupported replay command")
        try:
            async with engine.begin() as connection:
                current = await connection.execute(
                    text("SELECT version FROM replay_runs WHERE run_id = :run_id FOR UPDATE"),
                    {"run_id": run_id},
                )
                version = current.scalar_one_or_none()
                if version is None:
                    raise HTTPException(status_code=404, detail="replay run not found")
                if int(version) != request.expected_run_version:
                    raise ReplayConflictError("replay run version conflict")
                result = await connection.execute(
                    text(
                        "INSERT INTO replay_run_commands (run_id, command_type, expected_run_version, "
                        "payload, status, idempotency_key, requested_by) VALUES (:run_id, :command_type, "
                        ":expected_run_version, CAST(:payload AS jsonb), 'queued', :idempotency_key, "
                        ":requested_by) ON CONFLICT (idempotency_key) DO UPDATE SET idempotency_key = "
                        "EXCLUDED.idempotency_key RETURNING command_id, status"
                    ),
                    {"run_id": run_id, "command_type": request.command_type, "expected_run_version": request.expected_run_version, "payload": orjson.dumps(request.payload).decode(), "idempotency_key": request.idempotency_key, "requested_by": request.requested_by},
                )
                row = result.mappings().one()
        except ReplayConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"command_id": str(row["command_id"]), "status": row["status"]}

    @router.get("/replay-runs/{run_id}/events", include_in_schema=False)
    async def events(
        run_id: str,
        request: Request,
        last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(engine, run_id, request, last_event_id or 0),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


async def _event_stream(
    engine: AsyncEngine, run_id: str, request: Request, event_id: int
) -> AsyncIterator[str]:
    current = event_id
    while not await request.is_disconnected():
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT event_id, event_type, sequence, simulated_at, payload, created_at "
                    "FROM replay_stream_events WHERE run_id = :run_id AND event_id > :event_id "
                    "ORDER BY event_id LIMIT 100"
                ),
                {"run_id": run_id, "event_id": current},
            )
            rows = result.mappings().all()
        if not rows:
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)
            continue
        for row in rows:
            current = int(row["event_id"])
            payload = {"type": row["event_type"], "event_id": current, **_row(row)}
            yield f"id: {current}\nevent: {row['event_type']}\ndata: {orjson.dumps(payload).decode()}\n\n"


def _row(row: Any) -> dict[str, Any]:
    return {
        key: value.isoformat() if isinstance(value, datetime) else str(value) if key.endswith("_id") and value is not None else value
        for key, value in dict(row).items()
    }
