from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_run_repository import (
    create_queued_agent_run,
    fail_agent_run,
)
from heatgrid_ops.agent.contracts import AgentRunRequest, SimulateCard
from heatgrid_ops.agent.nodes import (
    complete_run,
    generate_fallback_output,
    generate_operational_answer,
    get_external_context,
    get_ops_evidence,
    load_ops_input,
    mark_running,
    route_after_llm,
    validate_output,
)
from heatgrid_ops.agent.report_nodes import write_anomaly_report
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.state import AgentState
from schemas import AgentRunResponse


@dataclass(frozen=True, slots=True)
class AgentGraphContext:
    engine: AsyncEngine
    runtime: AgentRuntime
    legacy_simulate_card: SimulateCard | None = None


async def run_persistent_agent_graph(
    context: AgentGraphContext,
    request: AgentRunRequest,
) -> AgentRunResponse:
    await create_queued_agent_run(
        context.engine,
        run_id=request.run_id,
        alert_id=request.alert_id,
        card_id=request.card_id,
    )
    graph = build_agent_graph(context)
    try:
        state = await graph.ainvoke(
            {
                "run_id": request.run_id,
                "alert_id": request.alert_id,
                "card_id": request.card_id,
                "used_tools": [],
            }
        )
    except HTTPException as exc:
        return await fail_agent_run(context.engine, request.run_id, str(exc.detail))
    return state["result"]


def build_agent_graph(context: AgentGraphContext):
    graph = StateGraph(AgentState)
    graph.add_node("mark_running", partial(mark_running, context))
    graph.add_node("load_ops_input", partial(load_ops_input, context))
    graph.add_node("get_ops_evidence", partial(get_ops_evidence, context))
    graph.add_node("get_external_context", partial(get_external_context, context))
    graph.add_node("generate_operational_answer", partial(generate_operational_answer, context))
    graph.add_node("generate_fallback_output", partial(generate_fallback_output, context))
    graph.add_node("validate_output", partial(validate_output, context))
    graph.add_node("complete_run", partial(complete_run, context))
    graph.add_node("write_anomaly_report", partial(write_anomaly_report, context))
    graph.add_edge(START, "mark_running")
    graph.add_edge("mark_running", "load_ops_input")
    graph.add_edge("load_ops_input", "get_ops_evidence")
    graph.add_edge("get_ops_evidence", "get_external_context")
    graph.add_edge("get_external_context", "generate_operational_answer")
    graph.add_conditional_edges(
        "generate_operational_answer",
        route_after_llm,
        {
            "generate_fallback_output": "generate_fallback_output",
            "validate_output": "validate_output",
        },
    )
    graph.add_edge("generate_fallback_output", "validate_output")
    graph.add_edge("validate_output", "complete_run")
    graph.add_edge("complete_run", "write_anomaly_report")
    graph.add_edge("write_anomaly_report", END)
    return graph.compile()
