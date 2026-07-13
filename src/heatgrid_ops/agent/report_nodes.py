from __future__ import annotations

from heatgrid_ops.agent.contracts import ReportWriteRequest
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import (
    record_decision,
    record_tool_completed,
    record_tool_started,
)
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate


async def write_anomaly_report(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    tool_name = "write_anomaly_report"
    used_tools = [*state.get("used_tools", []), tool_name]
    await record_decision(context, state, tool_name)
    await record_tool_started(context, state, tool_name)
    try:
        draft = await context.runtime.write_anomaly(
            ReportWriteRequest(
                run_id=state["run_id"],
                card_id=state["card_id"],
                source_input=state["source_input"],
                evidence_context=state["external_context"],
                ops_output=state["ops_output"],
            )
        )
        artifact = await context.artifacts.record(
            state["run_id"],
            draft.kind,
            draft.name,
            draft.uri,
        )
    except (AgentDependencyError, OSError, RuntimeError, ValueError) as exc:
        message = str(exc)
        await record_tool_completed(context, state, tool_name, {"status": "failed"})
        await _record_report_failed(context, state, message)
        return {"used_tools": used_tools, "report_errors": [message]}

    await record_tool_completed(context, state, tool_name, {"status": "completed"})
    await context.audit.record_event(
        state["run_id"],
        "report_written",
        "anomaly report written",
        {"kind": artifact.kind, "name": artifact.name, "uri": artifact.uri},
    )
    return {
        "used_tools": used_tools,
        "report_artifacts": [artifact.model_dump(mode="json")],
    }


async def _record_report_failed(
    context: AgentNodeContext,
    state: AgentState,
    message: str,
) -> None:
    await context.audit.record_event(
        state["run_id"],
        "report_failed",
        "anomaly report failed",
        {"kind": "anomaly_report", "error": message[:500]},
    )
