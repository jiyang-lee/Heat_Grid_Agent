from __future__ import annotations

from typing import Protocol

import orjson
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_run_artifact_repository import insert_agent_run_artifact
from agent_run_repository import AgentRunEventRecord, record_agent_run_event
from heatgrid_ops.agent.helpers import to_json
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.state import AgentState
from heatgrid_ops.agent.tools import ReportToolPayloadError, make_anomaly_report_tool
from schemas import JsonValue


class AgentReportNodeContext(Protocol):
    engine: AsyncEngine
    runtime: AgentRuntime


async def write_anomaly_report(
    context: AgentReportNodeContext,
    state: AgentState,
) -> AgentState:
    tool_name = "write_anomaly_report"
    used_tools = [*state.get("used_tools", []), tool_name]
    await _record_decision(context, state, tool_name)
    await _record_tool_started(context, state, tool_name)
    if context.runtime.settings.openai_api_key is None:
        message = "OPENAI_API_KEY 없음, 이상보고서 생성을 건너뜁니다."
        await _record_tool_completed(context, state, tool_name, {"status": "failed"})
        await _record_report_failed(context, state, message)
        return {"used_tools": used_tools, "report_errors": [message]}

    try:
        key = context.runtime.settings.openai_api_key
        tool_result = make_anomaly_report_tool(
            openai_api_key=key.get_secret_value() if key is not None else None,
            openai_model=context.runtime.settings.openai_model,
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
        artifact = await insert_agent_run_artifact(
            context.engine,
            run_id=state["run_id"],
            kind=_required_text(artifact_payload, "kind"),
            name=_required_text(artifact_payload, "name"),
            uri=_required_text(artifact_payload, "uri"),
        )
    except (OSError, RuntimeError, ValueError, ReportToolPayloadError) as exc:
        message = str(exc)
        await _record_tool_completed(context, state, tool_name, {"status": "failed"})
        await _record_report_failed(context, state, message)
        return {"used_tools": used_tools, "report_errors": [message]}

    await _record_tool_completed(context, state, tool_name, {"status": "completed"})
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="report_written",
            message="anomaly report written",
            payload={
                "kind": artifact.kind,
                "name": artifact.name,
                "uri": artifact.uri,
            },
        ),
    )
    return {
        "used_tools": used_tools,
        "report_artifacts": [artifact.model_dump(mode="json")],
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
            event_type="llm_decision",
            message=f"LLM selected {next_step}",
            payload={"next": next_step},
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
    context: AgentReportNodeContext,
    state: AgentState,
    message: str,
) -> None:
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="report_failed",
            message="anomaly report failed",
            payload={
                "kind": "anomaly_report",
                "error": message[:500],
            },
        ),
    )


def _tool_json_object(payload: str) -> dict[str, JsonValue]:
    value = orjson.loads(payload)
    if not isinstance(value, dict):
        raise ReportToolPayloadError("tool result must be a JSON object")
    return value


def _required_text(payload: dict[str, JsonValue], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ReportToolPayloadError(f"{field_name} must be a non-empty string")
    return value
