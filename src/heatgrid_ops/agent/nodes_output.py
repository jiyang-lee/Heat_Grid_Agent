from __future__ import annotations

import logging
from typing import Literal

from heatgrid_ops.agent.assessment import validate_output as validate_ops_output
from heatgrid_ops.agent.contracts import (
    AgentLoopIterationRecord,
    AgentReviewRequest,
    AgentRunCompletion,
)
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.helpers import fallback_note
from heatgrid_ops.agent.models import JsonObject, JsonValue, SimulationResponse
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import enriched_external_context, record_decision
from heatgrid_ops.agent.run_models import AgentLoopSummary
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate
from heatgrid_ops.agent.usage import usage_with_totals


LOGGER = logging.getLogger(__name__)


async def generate_operational_answer(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    await record_decision(context, state, "generate_operational_answer")
    legacy = context.legacy_simulate_card
    if legacy is not None:
        simulation = await legacy(state["card_id"])
        return {
            "ops_output": simulation.ops_output,
            "token_usage": simulation.token_usage,
            "agent_mode": simulation.agent_mode,
        }
    enriched_context = enriched_external_context(state)
    usage = context.runtime.token_usage_for(
        state["source_input"],
        enriched_context,
        state["card_id"],
    )
    try:
        output = await context.runtime.generate_llm_output(
            state["source_input"],
            enriched_context,
            state["card_id"],
            model_verification=state.get("model_verification"),
            evidence_assessment=state.get("evidence_assessment"),
            revision_feedback=state.get("revision_feedback"),
            usage=usage,
        )
    except AgentDependencyError as exc:
        LOGGER.warning(
            "Operational LLM fallback for card_id=%s: %s: %s",
            state["card_id"],
            type(exc).__name__,
            exc,
        )
        return {"token_usage": usage, "agent_mode": "fallback"}
    return {"ops_output": output, "token_usage": usage, "agent_mode": "llm"}


async def generate_fallback_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    enriched_context = enriched_external_context(state)
    usage = state.get("token_usage") or context.runtime.token_usage_for(
        state["source_input"],
        enriched_context,
        state["card_id"],
    )
    return {
        "ops_output": fallback_note(state["source_input"], enriched_context),
        "token_usage": usage,
        "agent_mode": "fallback",
    }


async def validate_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    output = state["ops_output"]
    validation = validate_ops_output(output, agent_mode=state["agent_mode"])
    used_tools = state.get("used_tools", [])
    output_payload: JsonObject = {
        "card_id": state["card_id"],
        "agent_mode": state["agent_mode"],
        "used_tool_count": len(used_tools),
        "used_tools": _json_strings(used_tools),
        "validation": validation.model_dump(mode="json"),
    }
    await context.audit.record_event(
        state["run_id"],
        "final_output",
        "final output generated",
        output_payload,
    )
    return {"ops_output": output, "output_validation": validation}


def route_after_output_validation(
    state: AgentState,
) -> Literal["prepare_output_retry", "create_final_review"]:
    validation = state["output_validation"]
    if (
        not validation.valid
        and state.get("agent_mode") == "llm"
        and state.get("revision_count", 0) < 1
        and state.get("loop_iteration", 1) < state.get("max_iterations", 4)
    ):
        return "prepare_output_retry"
    return "create_final_review"


async def prepare_output_retry(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    iteration = state.get("loop_iteration", 1) + 1
    issues = state["output_validation"].issues
    await context.audit.record_loop_iteration(
        AgentLoopIterationRecord(
            run_id=state["run_id"],
            iteration=iteration,
            phase="output_revision",
            decision="revise_output",
            confidence=state["output_validation"].score,
            evidence_score=state["evidence_assessment"].evidence_score,
            missing_evidence=issues,
            model_verification=state.get("model_verification"),
        )
    )
    retry_payload: JsonObject = {
        "iteration": iteration,
        "issues": _json_strings(issues),
    }
    await context.audit.record_event(
        state["run_id"],
        "output_retry",
        "output validation requested one revision",
        retry_payload,
    )
    return {
        "loop_iteration": iteration,
        "revision_count": state.get("revision_count", 0) + 1,
        "revision_feedback": issues,
    }


async def create_final_review(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    assessment = state["evidence_assessment"]
    review_payload: JsonObject = {
        "card_id": state["card_id"],
        "ops_output": state["ops_output"].model_dump(mode="json"),
        "evidence_assessment": assessment.model_dump(mode="json"),
        "model_verification": state["model_verification"].model_dump(mode="json"),
        "external_candidate_ids": _json_strings(
            state.get("external_candidate_ids", [])
        ),
        "used_tools": _json_strings(state.get("used_tools", [])),
        "action_decisions": _json_objects(state.get("action_decisions", [])),
        "output_validation": state["output_validation"].model_dump(mode="json"),
    }
    task = await context.reviews.create_review(
        AgentReviewRequest(
            task_type="final_output",
            risk_level=_risk_level(state),
            title=f"에이전트 최종 운영 결과 검수: {state['card_id']}",
            run_id=state["run_id"],
            payload=review_payload,
        )
    )
    await context.audit.record_event(
        state["run_id"],
        "review_requested",
        "final human review requested",
        {"task_id": task.task_id, "task_type": task.task_type},
    )
    return {"review_task_id": task.task_id}


async def complete_run(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    usage = usage_with_totals(state["token_usage"], context.runtime.config)
    assessment = state["evidence_assessment"]
    loop_summary = AgentLoopSummary(
        iterations=state.get("loop_iteration", 1),
        max_iterations=state.get("max_iterations", context.runtime.config.agent_max_iterations),
        decision=assessment.decision,
        confidence=assessment.confidence,
        evidence_score=assessment.evidence_score,
        missing_evidence=assessment.missing_evidence,
        external_candidate_ids=state.get("external_candidate_ids", []),
        used_tools=state.get("used_tools", []),
        action_decisions=state.get("action_decisions", []),
        model_verification=state.get("model_verification"),
        review_required=True,
        review_task_id=state.get("review_task_id"),
    )
    result = await context.lifecycle.complete(
        state["run_id"],
        AgentRunCompletion(
            simulation=SimulationResponse(
                card_id=state["card_id"],
                input_source="postgresql",
                agent_mode=state["agent_mode"],
                ops_output=state["ops_output"],
                token_usage=usage,
            ),
            loop_summary=loop_summary,
            review_task_id=state.get("review_task_id"),
        ),
    )
    return {"result": result, "token_usage": usage}


def route_after_llm(state: AgentState) -> Literal["generate_fallback_output", "validate_output"]:
    if state.get("ops_output") is None:
        return "generate_fallback_output"
    return "validate_output"


def _risk_level(state: AgentState) -> Literal["low", "medium", "high", "critical"]:
    priority_context = state["source_input"].get("priority_context")
    priority = priority_context.get("priority") if isinstance(priority_context, dict) else None
    level = str(priority.get("priority_level") or "medium").lower() if isinstance(priority, dict) else "medium"
    if level == "urgent":
        return "critical"
    if level == "high":
        return "high"
    if level == "low":
        return "low"
    return "medium"


def _json_strings(values: list[str]) -> list[JsonValue]:
    return [value for value in values]


def _json_objects(values: list[dict[str, JsonValue]]) -> list[JsonValue]:
    return [value for value in values]
