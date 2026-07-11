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
    used_tools = [*state.audit.used_tools, tool_name]
    await record_decision(context, state, tool_name)
    await record_tool_started(context, state, tool_name)
    output = state.output.value
    if output is None:
        raise RuntimeError("agent output is missing")
    try:
        draft = await context.runtime.write_anomaly(
            ReportWriteRequest(
                run_id=state.request.run_id,
                card_id=state.request.card_id,
                source_input=state.request.source_input,
                evidence_context=state.evidence.external_context,
                ops_output=output,
            )
        )
        artifact = await context.artifacts.record(
            state.request.run_id,
            draft.kind,
            draft.name,
            draft.uri,
        )
    except (AgentDependencyError, OSError, RuntimeError, ValueError) as exc:
        message = str(exc)
        await record_tool_completed(context, state, tool_name, {"status": "failed"})
        await _record_report_failed(context, state, message)
        return {
            "audit": state.audit.model_copy(update={"used_tools": used_tools}),
            "output": state.output.model_copy(update={"report_errors": [message]}),
        }

    await record_tool_completed(context, state, tool_name, {"status": "completed"})
    await context.audit.record_event(
        state.request.run_id,
        "report_written",
        "anomaly report written",
        {"kind": artifact.kind, "name": artifact.name, "uri": artifact.uri},
    )
    return {
        "audit": state.audit.model_copy(update={"used_tools": used_tools}),
        "output": state.output.model_copy(
            update={"report_artifacts": [artifact.model_dump(mode="json")]}
        ),
    }


async def _record_decision(
    context: AgentReportNodeContext,
    state: AgentState,
    next_step: str,
) -> None:
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="graph_transition",
            message=f"graph entered {next_step}",
            payload={"next": next_step, "decision_source": "graph"},
        ),
    )


async def _record_tool_started(
    context: AgentReportNodeContext,
    state: AgentState,
    tool_name: str,
) -> None:
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="tool_started",
            message=f"{tool_name} started",
            payload={"tool": tool_name},
        ),
    )


async def _record_tool_completed(
    context: AgentReportNodeContext,
    state: AgentState,
    tool_name: str,
    payload: dict[str, str | int],
) -> None:
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="tool_completed",
            message=f"{tool_name} completed",
            payload={"tool": tool_name, **payload},
        ),
    )


async def _record_report_failed(
    context: AgentNodeContext,
    state: AgentState,
    message: str,
) -> None:
    await context.audit.record_event(
        state.request.run_id,
        "report_failed",
        "anomaly report failed",
        {"kind": "anomaly_report", "error": message[:500]},
    )
