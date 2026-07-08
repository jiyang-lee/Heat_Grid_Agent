from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_run_repository import (
    get_agent_run,
    list_agent_run_artifacts,
    save_completed_agent_run,
)
from alert_repository import get_alert
from schemas import (
    AgentRunArtifact,
    AgentRunCreateRequest,
    AgentRunResponse,
    JsonValue,
    SimulationResponse,
)

SimulateCard = Callable[[str], Awaitable[SimulationResponse]]


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
        simulation = await simulate_card(str(alert["card_id"]))
        return await save_completed_agent_run(
            engine,
            run_id=str(uuid4()),
            alert_id=payload.alert_id,
            simulation=simulation,
        )

    @router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
    async def agent_run(run_id: str) -> AgentRunResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return run

    @router.get("/agent-runs/{run_id}/artifacts", response_model=list[AgentRunArtifact])
    async def agent_run_artifacts(run_id: str) -> list[AgentRunArtifact]:
        artifacts = await list_agent_run_artifacts(engine, run_id)
        if artifacts is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return artifacts

    @router.get("/agent-runs/{run_id}/events")
    async def agent_run_events_response(run_id: str) -> StreamingResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return StreamingResponse(agent_run_events(run), media_type="text/event-stream")

    return router


async def agent_run_events(run: AgentRunResponse) -> AsyncIterator[str]:
    yield sse(
        "run_started",
        "agent run loaded",
        {"run_id": run.run_id, "alert_id": run.alert_id},
    )
    yield sse(
        "run_completed",
        "agent run completed",
        {
            "run_id": run.run_id,
            "status": run.status,
            "card_id": run.card_id,
            "agent_mode": run.agent_mode,
            "ops_output": None
            if run.ops_output is None
            else run.ops_output.model_dump(mode="json"),
            "token_usage": None
            if run.token_usage is None
            else run.token_usage.model_dump(mode="json"),
        },
    )


def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    event = {"type": kind, "message": message, "payload": payload}
    return f"data: {orjson.dumps(event).decode('utf-8')}\n\n"
