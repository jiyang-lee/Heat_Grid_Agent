from __future__ import annotations

from heatgrid_ops.agent.contracts import AgentRunRequest, validate_agent_input
from heatgrid_ops.agent.errors import AgentInputNotFoundError
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import (
    record_decision,
    record_tool_completed,
    record_tool_started,
    tool_json_object,
)
from heatgrid_ops.agent.state import AgentState


async def mark_running(context: AgentNodeContext, state: AgentState) -> AgentState:
    await context.lifecycle.mark_running(state["run_id"])
    return {}


async def load_ops_input(context: AgentNodeContext, state: AgentState) -> AgentState:
    request = AgentRunRequest(
        run_id=state["run_id"],
        alert_id=state["alert_id"],
        card_id=state["card_id"],
        approved_action_task_id=state.get("approved_action_task_id"),
    )
    snapshot = await context.inputs.load(request)
    if snapshot is None:
        raise AgentInputNotFoundError(
            entity="card_id",
            identifier=state["card_id"],
        )
    return {"source_input": validate_agent_input(snapshot, request)}


async def get_ops_evidence(context: AgentNodeContext, state: AgentState) -> AgentState:
    tool_name = "get_ops_evidence"
    await record_decision(context, state, tool_name)
    await record_tool_started(context, state, tool_name)
    tools = {
        item.name: item
        for item in context.runtime.tools_for(state["source_input"], {"status": "pending"})
    }
    evidence_payload = tools[tool_name].invoke({"card_id": state["card_id"]})
    ops_evidence = tool_json_object(evidence_payload)
    await record_tool_completed(
        context,
        state,
        tool_name,
        {"payload_chars": len(evidence_payload)},
    )
    return {
        "ops_evidence": ops_evidence,
        "used_tools": [*state.get("used_tools", []), tool_name],
    }


async def get_external_context(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    tool_name = "get_external_context"
    await record_decision(context, state, tool_name)
    collected_context = context.runtime.external_context_for(
        state["card_id"],
        state["source_input"],
    )
    tools = {
        item.name: item
        for item in context.runtime.tools_for(state["source_input"], collected_context)
    }
    await record_tool_started(context, state, tool_name)
    context_payload = tools[tool_name].invoke({"card_id": state["card_id"]})
    external_context = tool_json_object(context_payload)
    await record_tool_completed(
        context,
        state,
        tool_name,
        {"status": str(external_context.get("status") or "unknown")},
    )

    reference_tool = "get_internal_references"
    await record_tool_started(context, state, reference_tool)
    references_payload = tools[reference_tool].invoke({"card_id": state["card_id"]})
    internal_references = tool_json_object(references_payload)
    external_context.update(internal_references)
    retrieval = external_context.get("retrieval")
    retrieval_status = (
        retrieval.get("status")
        if isinstance(retrieval, dict)
        else external_context.get("status")
    )
    await record_tool_completed(
        context,
        state,
        reference_tool,
        {"status": str(retrieval_status or "unknown")},
    )
    return {
        "external_context": external_context,
        "used_tools": [*state.get("used_tools", []), tool_name, reference_tool],
    }
