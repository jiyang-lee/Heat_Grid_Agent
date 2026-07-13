from __future__ import annotations

import orjson

from heatgrid_ops.agent.errors import AgentInputContractError
from heatgrid_ops.agent.helpers import to_json
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import (
    record_decision,
    record_tool_completed,
    record_tool_started,
)
from heatgrid_ops.agent.state import AgentState
from heatgrid_ops.agent.tools import ReportToolPayloadError, make_anomaly_report_tool


async def write_anomaly_report(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    tool_name = "write_anomaly_report"
    used_tools = [*state.get("used_tools", []), tool_name]
    await record_decision(context, state, tool_name)
    await record_tool_started(context, state, tool_name)
    key = context.runtime.config.openai_api_key
    if key is None:
        message = "OPENAI_API_KEY 없음, 이상보고서 생성을 건너뜁니다."
        await record_tool_completed(context, state, tool_name, {"status": "failed"})
        await _record_report_failed(context, state, message)
        return {"used_tools": used_tools, "report_errors": [message]}

    try:
        tool_result = make_anomaly_report_tool(
            openai_api_key=key,
            openai_model=context.runtime.config.openai_model,
        ).invoke(
            {
                "payload_json": to_json(
                    {
                        "run_id": state["run_id"],
                        "card_id": state["card_id"],
                        "source_input": state["source_input"],
                        "external_context": state["external_context"],
                        "ops_output": state["ops_output"].model_dump(mode="json"),
                    }
                )
            }
        )
        artifact_payload = _tool_json_object(tool_result)
        artifact = await context.artifacts.record(
            state["run_id"],
            _required_text(artifact_payload, "kind"),
            _required_text(artifact_payload, "name"),
            _required_text(artifact_payload, "uri"),
        )
    except (OSError, RuntimeError, ValueError, ReportToolPayloadError) as exc:
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


def _tool_json_object(payload: str) -> JsonObject:
    value = orjson.loads(payload)
    if not isinstance(value, dict):
        raise AgentInputContractError(detail="tool result must be a JSON object")
    return value


def _required_text(payload: JsonObject, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise AgentInputContractError(detail=f"{field_name} must be a non-empty string")
    return value
