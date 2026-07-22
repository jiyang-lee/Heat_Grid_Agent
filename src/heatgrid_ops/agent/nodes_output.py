from __future__ import annotations

import logging
from typing import Literal

from heatgrid_ops.agent.assessment import validate_output as validate_ops_output
from heatgrid_ops.agent.contracts import (
    AgentLoopIterationRecord,
    AgentReviewRequest,
)
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.helpers import fallback_note
from heatgrid_ops.agent.models import (
    JsonObject,
    JsonValue,
    OpsAgentOutput,
)
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import (
    enriched_external_context,
    record_decision,
    risk_level,
)
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate


LOGGER = logging.getLogger(__name__)


async def generate_operational_answer(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    await record_decision(context, state, "generate_operational_answer")
    legacy = context.legacy_simulate_card
    if legacy is not None:
        simulation = await legacy(state.request.card_id)
        return {
            "output": state.output.model_copy(
                update={
                    "value": simulation.ops_output,
                    "token_usage": simulation.token_usage,
                    "mode": simulation.agent_mode,
                }
            )
        }
    enriched_context = enriched_external_context(state)
    usage = context.runtime.token_usage_for(
        state.request.source_input,
        enriched_context,
        state.request.card_id,
    )
    usage.calls.extend(state.evidence.diagnostic_calls)
    usage.calls.extend(state.evidence.assessment_calls)
    try:
        output = await context.runtime.generate_llm_output(
            state.request.source_input,
            enriched_context,
            state.request.card_id,
            model_verification=state.evidence.model_verification,
            evidence_assessment=state.loop.assessment,
            revision_feedback=state.loop.revision_feedback,
            usage=usage,
        )
    except AgentDependencyError as exc:
        LOGGER.warning(
            "Operational LLM fallback for card_id=%s: %s: %s",
            state.request.card_id,
            type(exc).__name__,
            exc,
        )
        return {
            "output": state.output.model_copy(
                update={"token_usage": usage, "mode": "fallback"}
            )
        }
    return {
        "output": state.output.model_copy(
            update={"value": output, "token_usage": usage, "mode": "llm"}
        )
    }


async def generate_fallback_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    enriched_context = enriched_external_context(state)
    usage = state.output.token_usage or context.runtime.token_usage_for(
        state.request.source_input,
        enriched_context,
        state.request.card_id,
    )
    if state.output.token_usage is None:
        usage.calls.extend(state.evidence.diagnostic_calls)
        usage.calls.extend(state.evidence.assessment_calls)
    return {
        "output": state.output.model_copy(
            update={
                "value": fallback_note(state.request.source_input, enriched_context),
                "token_usage": usage,
                "mode": "fallback",
            }
        )
    }


async def validate_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    output = _required_output(state)
    mode = _required_mode(state)
    validation = validate_ops_output(output, agent_mode=mode)
    output_payload: JsonObject = {
        "card_id": state.request.card_id,
        "agent_mode": mode,
        "used_tool_count": len(state.audit.used_tools),
        "used_tools": _json_strings(state.audit.used_tools),
        "validation": validation.model_dump(mode="json"),
    }
    await context.audit.record_event(
        state.request.run_id,
        "final_output",
        "final output generated",
        output_payload,
    )
    return {
        "output": state.output.model_copy(
            update={"value": output, "validation": validation}
        )
    }


def route_after_output_validation(
    state: AgentState,
) -> Literal["prepare_output_retry", "create_final_review"]:
    validation = state.output.validation
    if validation is None:
        raise RuntimeError("output validation is missing")
    if (
        not validation.valid
        and state.output.mode == "llm"
        and state.loop.revision_count < 1
        and state.loop.iteration < state.loop.max_iterations
    ):
        return "prepare_output_retry"
    return "create_final_review"


async def prepare_output_retry(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    validation = state.output.validation
    assessment = state.loop.assessment
    if validation is None or assessment is None:
        raise RuntimeError("loop output state is incomplete")
    iteration = state.loop.iteration + 1
    await context.audit.record_loop_iteration(
        AgentLoopIterationRecord(
            run_id=state.request.run_id,
            iteration=iteration,
            phase="output_revision",
            decision="revise_output",
            confidence=validation.score,
            evidence_score=assessment.evidence_score,
            missing_evidence=validation.issues,
            model_verification=state.evidence.model_verification,
        )
    )
    await context.audit.record_event(
        state.request.run_id,
        "output_retry",
        "output validation requested one revision",
        {
            "iteration": iteration,
            "issues": _json_strings(validation.issues),
        },
    )
    return {
        "loop": state.loop.model_copy(
            update={
                "iteration": iteration,
                "revision_count": state.loop.revision_count + 1,
                "revision_feedback": validation.issues,
            }
        )
    }


async def create_final_review(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    assessment = state.loop.assessment
    validation = state.output.validation
    verification = state.evidence.model_verification
    if assessment is None or validation is None or verification is None:
        raise RuntimeError("final review state is incomplete")
    review_payload: JsonObject = {
        "card_id": state.request.card_id,
        "ops_output": _required_output(state).model_dump(mode="json"),
        "evidence_assessment": assessment.model_dump(mode="json"),
        "model_verification": verification.model_dump(mode="json"),
        "used_tools": _json_strings(state.audit.used_tools),
        "action_decisions": _json_objects(state.audit.action_decisions),
        "output_validation": validation.model_dump(mode="json"),
    }
    if state.evidence.diagnostic_summary is not None:
        review_payload["diagnostic_summary"] = (
            state.evidence.diagnostic_summary.model_dump(mode="json")
        )
    task = await context.reviews.create_review(
        AgentReviewRequest(
            task_type="final_output",
            risk_level=risk_level(state.request.source_input),
            title=f"에이전트 최종 운영 결과 검수: {state.request.card_id}",
            run_id=state.request.run_id,
            payload=review_payload,
        )
    )
    await context.audit.record_event(
        state.request.run_id,
        "review_requested",
        "final human review requested",
        {"task_id": task.task_id, "task_type": task.task_type},
    )
    return {"loop": state.loop.model_copy(update={"review_task_id": task.task_id})}


def route_after_llm(
    state: AgentState,
) -> Literal["generate_fallback_output", "validate_output"]:
    if state.output.value is None:
        return "generate_fallback_output"
    return "validate_output"


def _required_output(state: AgentState) -> OpsAgentOutput:
    if state.output.value is None:
        raise RuntimeError("agent output is missing")
    return state.output.value


def _required_mode(state: AgentState) -> Literal["llm", "fallback"]:
    if state.output.mode is None:
        raise RuntimeError("agent mode is missing")
    return state.output.mode


def _json_strings(values: list[str]) -> list[JsonValue]:
    return [value for value in values]


def _json_objects(values: list[JsonObject]) -> list[JsonValue]:
    return [value for value in values]
