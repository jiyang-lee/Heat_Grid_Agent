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
    materialize_scenario_alert,
)
from alert_episode_repository import list_asset_telemetry, list_preventive_candidates, mark_alert_read
from heating_agent_routes import register_heating_agent_routes
from schemas import (
    AlertAckRequest,
    AlertAckResponse,
    AlertEnqueueResponse,
    AlertSummary,
    JsonValue,
    ScenarioAlertCreateRequest,
)
from settings import Settings


def make_alert_router(
    engine: AsyncEngine,
    settings: Settings,
    prefix: str = "",
) -> APIRouter:
    include_in_schema = prefix == "/api"
    router = APIRouter(prefix=prefix)

    @router.post(
        "/alerts/enqueue",
        response_model=AlertEnqueueResponse,
        include_in_schema=include_in_schema,
    )
    async def alerts_enqueue() -> AlertEnqueueResponse:
        result = await enqueue_priority_alerts(
            engine,
            stale_after_hours=settings.priority_stale_after_hours,
            model_version=settings.priority_model_version,
            expected_substations=settings.priority_expected_substations,
        )
        return AlertEnqueueResponse.model_validate(result)

    @router.get("/preventive-candidates", include_in_schema=include_in_schema)
    async def preventive_candidates(stream_key: str = "default") -> list[dict[str, JsonValue]]:
        return await list_preventive_candidates(engine, stream_key=stream_key)

    @router.get("/asset-telemetry", include_in_schema=include_in_schema)
    async def asset_telemetry(
        manufacturer_id: str,
        substation_id: int,
        stream_key: str = "default",
        limit: int = 72,
    ) -> dict[str, JsonValue]:
        return await list_asset_telemetry(
            engine,
            manufacturer_id=manufacturer_id,
            substation_id=substation_id,
            stream_key=stream_key,
            limit=limit,
        )

    if prefix == "/api":
        @router.post("/scenario-alerts", response_model=AlertSummary)
        async def scenario_alert_create(payload: ScenarioAlertCreateRequest) -> AlertSummary:
            row = await materialize_scenario_alert(
                engine,
                scenario_alert_id=payload.scenario_alert_id,
                substation_id=payload.substation_id,
                priority_level=payload.priority_level,
                reason=payload.reason,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="해당 기계실의 실제 priority card를 찾을 수 없습니다.")
            return AlertSummary.model_validate(row)

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
        "/alerts/{alert_id}/read",
        response_model=AlertAckResponse,
        include_in_schema=include_in_schema,
    )
    async def alert_read(alert_id: str, payload: AlertAckRequest) -> AlertAckResponse:
        await mark_alert_read(engine, alert_id=alert_id, read_by=payload.acked_by)
        row = await get_alert(engine, alert_id)
        if row is None:
            raise HTTPException(status_code=404, detail="alert_id not found")
        return AlertAckResponse.model_validate(row)

    @router.post(
        "/alerts/{alert_id}/resolve",
        response_model=AlertAckResponse,
        include_in_schema=include_in_schema,
    )
    async def alert_resolve(alert_id: str, payload: AlertAckRequest) -> AlertAckResponse:
        try:
            row = await resolve_alert(engine, alert_id=alert_id, acked_by=payload.acked_by)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        return AlertAckResponse.model_validate(row)

    if prefix == "":
        register_heating_agent_routes(router, engine)

    return router


async def alert_events(engine: AsyncEngine) -> AsyncIterator[str]:
    rows = await list_alerts(engine, status="open", priority_level=None)
    alerts_payload: list[JsonValue] = [row for row in rows]
    yield sse(
        "alerts_snapshot",
        "current open alerts loaded",
        {"alerts": alerts_payload},
    )


def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    event = {"type": kind, "message": message, "payload": payload}
    return f"data: {orjson.dumps(event).decode('utf-8')}\n\n"
