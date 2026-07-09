from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from alert_repository import (
    ack_alert,
    enqueue_priority_alerts,
    get_alert,
    list_alerts,
    resolve_alert,
)
from heating_agent_routes import register_heating_agent_routes
from schemas import (
    AlertAckRequest,
    AlertAckResponse,
    AlertEnqueueResponse,
    AlertSummary,
    JsonValue,
)


def make_alert_router(engine: AsyncEngine, prefix: str = "") -> APIRouter:
    include_in_schema = prefix == "/api"
    router = APIRouter(prefix=prefix)

    @router.post(
        "/alerts/enqueue",
        response_model=AlertEnqueueResponse,
        include_in_schema=include_in_schema,
    )
    async def alerts_enqueue() -> AlertEnqueueResponse:
        result = await enqueue_priority_alerts(engine)
        return AlertEnqueueResponse.model_validate(result)

    @router.get(
        "/alerts",
        response_model=list[AlertSummary],
        include_in_schema=include_in_schema,
    )
    async def alerts(
        status: Literal["open", "acked", "resolved", "all"] = "open",
        priority_level: Literal["urgent", "high"] | None = None,
    ) -> list[AlertSummary]:
        rows = await list_alerts(engine, status=status, priority_level=priority_level)
        return [AlertSummary.model_validate(row) for row in rows]

    @router.get("/alerts/events", include_in_schema=include_in_schema)
    async def alert_events_response() -> StreamingResponse:
        return StreamingResponse(alert_events(engine), media_type="text/event-stream")

    @router.get(
        "/alerts/{alert_id}",
        response_model=AlertSummary,
        include_in_schema=include_in_schema,
    )
    async def alert_detail(alert_id: str) -> AlertSummary:
        row = await get_alert(engine, alert_id)
        if row is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        return AlertSummary.model_validate(row)

    @router.post(
        "/alerts/{alert_id}/ack",
        response_model=AlertAckResponse,
        include_in_schema=include_in_schema,
    )
    async def alert_ack(alert_id: str, payload: AlertAckRequest) -> AlertAckResponse:
        row = await ack_alert(engine, alert_id=alert_id, acked_by=payload.acked_by)
        if row is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        return AlertAckResponse.model_validate(row)

    @router.post(
        "/alerts/{alert_id}/resolve",
        response_model=AlertAckResponse,
        include_in_schema=include_in_schema,
    )
    async def alert_resolve(alert_id: str, payload: AlertAckRequest) -> AlertAckResponse:
        row = await resolve_alert(engine, alert_id=alert_id, acked_by=payload.acked_by)
        if row is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        return AlertAckResponse.model_validate(row)

    if prefix == "":
        register_heating_agent_routes(router, engine)

    return router


async def alert_events(engine: AsyncEngine) -> AsyncIterator[str]:
    rows = await list_alerts(engine, status="open", priority_level=None)
    yield sse(
        "alerts_snapshot",
        "current open alerts loaded",
        {"alerts": rows},
    )


def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    event = {"type": kind, "message": message, "payload": payload}
    return f"data: {orjson.dumps(event).decode('utf-8')}\n\n"
