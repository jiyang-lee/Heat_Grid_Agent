from __future__ import annotations

from typing import Literal, Protocol

import orjson
from fastapi import HTTPException
from openai import OpenAIError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_run_repository import (
    AgentRunEventRecord,
    complete_agent_run,
    mark_agent_run_running,
    record_agent_run_event,
)
from heatgrid_ops.agent.contracts import SimulateCard
from heatgrid_ops.agent.helpers import fallback_note
from heatgrid_ops.agent.services import AgentRuntime, MissingApiKeyError
from heatgrid_ops.agent.state import AgentState
from heatgrid_ops.agent.tools import ReportToolPayloadError
from repository import fetch_ops_input
from schemas import JsonValue, SimulationResponse
from usage import usage_with_totals


class AgentNodeContext(Protocol):
    engine: AsyncEngine
    runtime: AgentRuntime
    legacy_simulate_card: SimulateCard | None


async def mark_running(context: AgentNodeContext, state: AgentState) -> AgentState:
    await mark_agent_run_running(context.engine, state["run_id"])
    return {}


async def load_ops_input(context: AgentNodeContext, state: AgentState) -> AgentState:
    source_input = await fetch_ops_input(context.engine, state["card_id"])
    if source_input is None:
        raise HTTPException(status_code=404, detail="card_id를 찾을 수 없습니다.")
    return {"source_input": source_input}


async def get_ops_evidence(context: AgentNodeContext, state: AgentState) -> AgentState:
    await record_decision(context, state, "get_ops_evidence")
    await record_tool_started(context, state, "get_ops_evidence")
    source_input = state["source_input"]
    tools = context.runtime.tools_for(source_input, {"status": "pending"})
    evidence_payload = tools[0].invoke({"card_id": state["card_id"]})
    ops_evidence = _tool_json_object(evidence_payload)
    await record_tool_completed(
        context,
        state,
        "get_ops_evidence",
        {"payload_chars": len(evidence_payload)},
    )
    return {
        "ops_evidence": ops_evidence,
        "used_tools": [*state.get("used_tools", []), "get_ops_evidence"],
    }


async def get_external_context(context: AgentNodeContext, state: AgentState) -> AgentState:
    await record_decision(context, state, "get_external_context")
    await record_tool_started(context, state, "get_external_context")
    external_context = context.runtime.external_context_for(
        state["card_id"],
        state["source_input"],
    )
    tools = context.runtime.tools_for(state["source_input"], external_context)
    context_payload = tools[1].invoke({"card_id": state["card_id"]})
    external_context = _tool_json_object(context_payload)
    retrieval = external_context.get("retrieval")
    retrieval_status = (
        retrieval.get("status")
        if isinstance(retrieval, dict)
        else external_context.get("status")
    )
    await record_tool_completed(
        context,
        state,
        "get_external_context",
        {"status": str(retrieval_status or "unknown")},
    )
    return {
        "external_context": external_context,
        "used_tools": [*state.get("used_tools", []), "get_external_context"],
    }


async def generate_operational_answer(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    await record_decision(context, state, "final_output")
    legacy = context.legacy_simulate_card
    if legacy is not None:
        simulation = await legacy(state["card_id"])
        return {
            "ops_output": simulation.ops_output,
            "token_usage": simulation.token_usage,
            "agent_mode": simulation.agent_mode,
        }
    usage = context.runtime.token_usage_for(
        state["source_input"],
        state["external_context"],
        state["card_id"],
    )
    try:
        output = await context.runtime.generate_llm_output(
            state["source_input"],
            state["external_context"],
            state["card_id"],
            usage,
        )
    except (MissingApiKeyError, OpenAIError, ValidationError):
        return {"token_usage": usage, "agent_mode": "fallback"}
    return {"ops_output": output, "token_usage": usage, "agent_mode": "llm"}


async def generate_fallback_output(context: AgentNodeContext, state: AgentState) -> AgentState:
    usage = state.get("token_usage") or context.runtime.token_usage_for(
        state["source_input"],
        state["external_context"],
        state["card_id"],
    )
    return {
        "ops_output": fallback_note(state["source_input"], state["external_context"]),
        "token_usage": usage,
        "agent_mode": "fallback",
    }


async def validate_output(context: AgentNodeContext, state: AgentState) -> AgentState:
    output = state["ops_output"]
    used_tools = state.get("used_tools", [])
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="final_output",
            message="final output generated",
            payload={
                "card_id": state["card_id"],
                "agent_mode": state["agent_mode"],
                "used_tool_count": len(used_tools),
                "used_tools": "|".join(used_tools),
            },
        ),
    )
    return {"ops_output": output}


async def complete_run(context: AgentNodeContext, state: AgentState) -> AgentState:
    usage = usage_with_totals(state["token_usage"], context.runtime.settings)
    simulation = SimulationResponse(
        card_id=state["card_id"],
        input_source="postgresql",
        agent_mode=state["agent_mode"],
        ops_output=state["ops_output"],
        token_usage=usage,
    )
    result = await complete_agent_run(context.engine, state["run_id"], simulation)
    return {"result": result, "token_usage": usage}


def route_after_llm(state: AgentState) -> Literal["generate_fallback_output", "validate_output"]:
    if state.get("ops_output") is None:
        return "generate_fallback_output"
    return "validate_output"


async def record_decision(
    context: AgentNodeContext,
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


async def record_tool_started(
    context: AgentNodeContext,
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


async def record_tool_completed(
    context: AgentNodeContext,
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
