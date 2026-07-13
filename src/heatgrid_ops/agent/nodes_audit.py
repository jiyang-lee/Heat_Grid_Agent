from __future__ import annotations

from typing import Literal

from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.state import AgentState


async def record_decision(
    context: AgentNodeContext,
    state: AgentState,
    next_step: str,
) -> None:
    await context.audit.record_event(
        state.request.run_id,
        "graph_transition",
        f"graph entered {next_step}",
        {"next": next_step, "decision_source": "graph"},
    )


async def record_tool_started(
    context: AgentNodeContext,
    state: AgentState,
    tool_name: str,
) -> None:
    await context.audit.record_event(
        state.request.run_id,
        "tool_started",
        f"{tool_name} started",
        {"tool": tool_name},
    )


async def record_tool_completed(
    context: AgentNodeContext,
    state: AgentState,
    tool_name: str,
    payload: JsonObject,
) -> None:
    await context.audit.record_event(
        state.request.run_id,
        "tool_completed",
        f"{tool_name} completed",
        {"tool": tool_name, **payload},
    )


def enriched_external_context(state: AgentState) -> JsonObject:
    context = dict(state.evidence.external_context)
    verification = state.evidence.model_verification
    assessment = state.loop.assessment
    if verification is not None:
        context["model_verification"] = verification.model_dump(mode="json")
    if assessment is not None:
        context["evidence_assessment"] = assessment.model_dump(mode="json")
    return context


def risk_level(
    source_input: JsonObject,
) -> Literal["low", "medium", "high", "critical"]:
    priority_context = source_input.get("priority_context")
    priority = (
        priority_context.get("priority")
        if isinstance(priority_context, dict)
        else None
    )
    level = (
        str(priority.get("priority_level") or "medium").lower()
        if isinstance(priority, dict)
        else "medium"
    )
    if level == "urgent":
        return "critical"
    if level == "high":
        return "high"
    if level == "low":
        return "low"
    return "medium"


def model_drift_score(state: AgentState) -> float:
    verification = state.evidence.model_verification
    if verification is None or verification.risk_score_delta is None:
        return 0.0
    return min(1.0, abs(float(verification.risk_score_delta)))
