from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_runner import AgentRunRequest, SimulateCard, run_agent_graph
from agent_run_artifact_repository import list_agent_run_artifacts
from agent_run_event_repository import list_agent_run_events
from agent_run_repository import (
    get_agent_run,
)
from alert_repository import get_alert
from schemas import (
    AgentRunArtifact,
    AgentRunCreateRequest,
    AgentRunEvent,
    AgentRunResponse,
    JsonValue,
)


def make_agent_run_router(
    engine: AsyncEngine,
    simulate_card: SimulateCard,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/agent-runs", response_model=AgentRunResponse)
    async def create_agent_run(payload: AgentRunCreateRequest) -> AgentRunResponse:
        alert = await get_alert(engine, payload.alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        return await run_agent_graph(
            engine,
            AgentRunRequest(
                run_id=str(uuid4()),
                alert_id=payload.alert_id,
                card_id=str(alert["card_id"]),
            ),
            simulate_card,
        )

    @router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
    async def agent_run(run_id: str) -> AgentRunResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return run

    @router.get("/agent-runs/{run_id}/artifacts", response_model=list[AgentRunArtifact])
    async def agent_run_artifacts(run_id: str) -> list[AgentRunArtifact]:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return await list_agent_run_artifacts(engine, run_id)

    @router.get("/agent-runs/{run_id}/events")
    async def agent_run_events_response(run_id: str) -> StreamingResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        events = await list_agent_run_events(engine, run_id)
        return StreamingResponse(agent_run_events(events), media_type="text/event-stream")

    return router


async def agent_run_events(events: list[AgentRunEvent]) -> AsyncIterator[str]:
    for event in events:
        yield sse(event.event_type, event.message, event.payload)


def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    event = {"type": kind, "message": message, "payload": payload}
    return f"data: {orjson.dumps(event).decode('utf-8')}\n\n"
