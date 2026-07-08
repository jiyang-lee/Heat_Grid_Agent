from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine

from alert_repository import ack_alert, enqueue_priority_alerts, list_alerts
from heating_agent_routes import register_heating_agent_routes
from schemas import (
    AlertAckRequest,
    AlertAckResponse,
    AlertEnqueueResponse,
    AlertSummary,
)


def make_alert_router(engine: AsyncEngine) -> APIRouter:
    router = APIRouter()

    @router.post("/alerts/enqueue", response_model=AlertEnqueueResponse)
    async def alerts_enqueue() -> AlertEnqueueResponse:
        result = await enqueue_priority_alerts(engine)
        return AlertEnqueueResponse.model_validate(result)

    @router.get("/alerts", response_model=list[AlertSummary])
    async def alerts(
        status: Literal["open", "acked", "all"] = "open",
        priority_level: Literal["urgent", "high"] | None = None,
    ) -> list[AlertSummary]:
        rows = await list_alerts(engine, status=status, priority_level=priority_level)
        return [AlertSummary.model_validate(row) for row in rows]

    @router.post("/alerts/{alert_id}/ack", response_model=AlertAckResponse)
    async def alert_ack(alert_id: str, payload: AlertAckRequest) -> AlertAckResponse:
        row = await ack_alert(engine, alert_id=alert_id, acked_by=payload.acked_by)
        if row is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        return AlertAckResponse.model_validate(row)

    register_heating_agent_routes(router, engine)

    return router
