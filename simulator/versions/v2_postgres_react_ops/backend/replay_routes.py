from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from replay_service import ReplayControlError, ReplayService
from schemas import ReplayControlRequest, ReplaySnapshot, ReplayStatus


def make_replay_router(
    service_provider: Callable[[], ReplayService],
    *,
    prefix: str = "/api/demo-replay",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["demo-replay"])

    @router.get("/status", response_model=ReplayStatus)
    async def replay_status() -> dict[str, Any]:
        return service_provider().status()

    @router.get("/snapshot", response_model=ReplaySnapshot)
    async def replay_snapshot() -> dict[str, Any]:
        return service_provider().snapshot()

    @router.get("/events", include_in_schema=False)
    async def replay_events() -> StreamingResponse:
        service = service_provider()
        return StreamingResponse(
            _event_stream(service),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/control", response_model=ReplayStatus)
    async def replay_control(request: ReplayControlRequest) -> dict[str, Any]:
        service = service_provider()
        try:
            return await service.control(
                request.action,
                simulated_at=request.simulated_at,
            )
        except ReplayControlError as exc:
            status_code = 503 if service.state == "disabled" else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return router


async def _event_stream(service: ReplayService) -> AsyncIterator[str]:
    queue = service.events.open_subscription()
    try:
        snapshot = service.snapshot()
        yield _sse({"type": "replay_state", **service.status()})
        if snapshot["readings"] and snapshot["current_simulated_at"]:
            yield _sse(
                {
                    "type": "sensor_tick",
                    "run_id": service.run_id,
                    "dataset_version": snapshot["dataset_version"],
                    "simulated_at": snapshot["current_simulated_at"],
                    "window_progress": snapshot["window_progress"],
                    "total_progress": snapshot["total_progress"],
                    "readings": snapshot["readings"],
                }
            )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
            except TimeoutError:
                yield ": keepalive\n\n"
            else:
                yield _sse(event)
    finally:
        service.events.close_subscription(queue)


def _sse(event: dict[str, Any]) -> str:
    payload = orjson.dumps(event).decode("utf-8")
    return f"data: {payload}\n\n"
