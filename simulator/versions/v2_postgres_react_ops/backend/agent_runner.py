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

    async def decide_ops_evidence(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="llm_decision",
                message="LLM selected get_ops_evidence",
                payload={"next": "get_ops_evidence"},
            ),
        )
        return {}

    async def observe_ops_evidence(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="tool_started",
                message="get_ops_evidence started",
                payload={"tool": "get_ops_evidence"},
            ),
        )
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="tool_completed",
                message="get_ops_evidence completed",
                payload={"tool": "get_ops_evidence"},
            ),
        )
        return {}

    async def decide_external_context(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="llm_decision",
                message="LLM selected get_external_context",
                payload={"next": "get_external_context"},
            ),
        )
        return {}

    async def observe_external_context(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="tool_started",
                message="get_external_context started",
                payload={"tool": "get_external_context"},
            ),
        )
        simulation = await simulate_card(state["card_id"])
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="tool_completed",
                message="get_external_context completed",
                payload={"tool": "get_external_context"},
            ),
        )
        return {"simulation": simulation}

    async def decide_final_output(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="llm_decision",
                message="LLM selected final output",
                payload={"next": "final_output"},
            ),
        )
        return {}

    async def final_output(state: AgentRunState) -> AgentRunState:
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=state["run_id"],
                event_type="final_output",
                message="final output generated",
                payload={"card_id": state["card_id"]},
            ),
        )
        return {}

    async def complete_run(state: AgentRunState) -> AgentRunState:
        result = await complete_agent_run(engine, state["run_id"], state["simulation"])
        return {"result": result}

    graph.add_node("mark_running", mark_running)
    graph.add_node("decide_ops_evidence", decide_ops_evidence)
    graph.add_node("observe_ops_evidence", observe_ops_evidence)
    graph.add_node("decide_external_context", decide_external_context)
    graph.add_node("observe_external_context", observe_external_context)
    graph.add_node("decide_final_output", decide_final_output)
    graph.add_node("final_output", final_output)
    graph.add_node("complete_run", complete_run)
    graph.add_edge(START, "mark_running")
    graph.add_edge("mark_running", "decide_ops_evidence")
    graph.add_edge("decide_ops_evidence", "observe_ops_evidence")
    graph.add_edge("observe_ops_evidence", "decide_external_context")
    graph.add_edge("decide_external_context", "observe_external_context")
    graph.add_edge("observe_external_context", "decide_final_output")
    graph.add_edge("decide_final_output", "final_output")
    graph.add_edge("final_output", "complete_run")
    graph.add_edge("complete_run", END)
    return graph.compile()
