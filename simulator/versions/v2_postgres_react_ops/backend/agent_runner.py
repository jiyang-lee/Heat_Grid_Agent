from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_run_repository import (
    AgentRunEventRecord,
    complete_agent_run,
    create_queued_agent_run,
    fail_agent_run,
    mark_agent_run_running,
    record_agent_run_event,
)
from schemas import AgentRunResponse, SimulationResponse

SimulateCard = Callable[[str], Awaitable[SimulationResponse]]


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    run_id: str
    alert_id: str
    card_id: str


class AgentRunState(TypedDict, total=False):
    run_id: str
    alert_id: str
    card_id: str
    simulation: SimulationResponse
    result: AgentRunResponse


async def run_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard,
) -> AgentRunResponse:
    await create_queued_agent_run(
        engine,
        run_id=request.run_id,
        alert_id=request.alert_id,
        card_id=request.card_id,
    )
    graph = _build_agent_graph(engine, simulate_card)
    try:
        state = await graph.ainvoke(
            {
                "run_id": request.run_id,
                "alert_id": request.alert_id,
                "card_id": request.card_id,
            }
        )
    except HTTPException as exc:
        return await fail_agent_run(engine, request.run_id, str(exc.detail))
    return state["result"]


def _build_agent_graph(engine: AsyncEngine, simulate_card: SimulateCard):
    graph = StateGraph(AgentRunState)

    async def mark_running(state: AgentRunState) -> AgentRunState:
        await mark_agent_run_running(engine, state["run_id"])
        return {}

    async def run_tool(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="tool_started",
                message="get_ops_evidence started",
                payload={"tool": "get_ops_evidence"},
            ),
        )
        simulation = await simulate_card(state["card_id"])
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="tool_completed",
                message="get_ops_evidence completed",
                payload={"tool": "get_ops_evidence"},
            ),
        )
        return {"simulation": simulation}

    async def complete_run(state: AgentRunState) -> AgentRunState:
        result = await complete_agent_run(engine, state["run_id"], state["simulation"])
        return {"result": result}

    graph.add_node("mark_running", mark_running)
    graph.add_node("run_tool", run_tool)
    graph.add_node("complete_run", complete_run)
    graph.add_edge(START, "mark_running")
    graph.add_edge("mark_running", "run_tool")
    graph.add_edge("run_tool", "complete_run")
    graph.add_edge("complete_run", END)
    return graph.compile()
