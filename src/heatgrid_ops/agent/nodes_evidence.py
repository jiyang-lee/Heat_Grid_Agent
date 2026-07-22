from __future__ import annotations

from typing import Literal

from heatgrid_ops.agent.contracts import AgentLoopIterationRecord, AgentReviewRequest
from heatgrid_ops.agent.models import JsonObject, JsonValue, ModelVerificationResult
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import record_decision, risk_level
from heatgrid_ops.agent.run_models import ModelVerificationRequest
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate


async def verify_model_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    await record_decision(context, state, "verify_active_models")
    await context.audit.record_event(
        state.request.run_id,
        "model_verification_started",
        "active model verification started",
        {"attempt": 1},
    )
    result, artifact_uri = await _run_model_verification(context, state, attempt=1)
    await context.audit.record_event(
        state.request.run_id,
        "model_verification",
        "active models verified",
        result.model_dump(mode="json"),
    )
    return {
        "evidence": state.evidence.model_copy(
            update={
                "model_verification": result,
                "model_attempts": 1,
                "active_model_artifact_uri": artifact_uri,
            }
        )
    }


async def assess_collected_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    assessment_calls = list(state.evidence.assessment_calls)
    assessment = await context.runtime.assess_evidence(
        source_input=state.request.source_input,
        evidence_context=state.evidence.external_context,
        model_verification=state.evidence.model_verification,
        iteration=state.loop.iteration,
        max_iterations=state.loop.max_iterations,
        diagnostic_available=bool(
            context.runtime.diagnostic_model is not None
            and context.budget is not None
            and not state.loop.diagnostic_attempted
        ),
        force_review=state.loop.force_review,
        calls=assessment_calls,
    )
    await context.audit.record_loop_iteration(
        AgentLoopIterationRecord(
            run_id=state.request.run_id,
            iteration=state.loop.iteration,
            phase="evidence_assessment",
            decision=assessment.decision,
            confidence=assessment.confidence,
            evidence_score=assessment.evidence_score,
            missing_evidence=assessment.missing_evidence,
            model_verification=state.evidence.model_verification,
        )
    )
    decision_payload: JsonObject = {
        "iteration": state.loop.iteration,
        "decision": assessment.decision,
        "confidence": assessment.confidence,
        "evidence_score": assessment.evidence_score,
        "missing_evidence": _json_strings(assessment.missing_evidence),
        "decision_source": assessment.decision_source,
    }
    await context.audit.record_event(
        state.request.run_id,
        "loop_decision",
        f"loop decision: {assessment.decision}",
        decision_payload,
    )
    model_review_task_id = state.loop.model_review_task_id
    verification = state.evidence.model_verification
    if (
        assessment.decision == "request_human"
        and verification is not None
        and verification.agreement is False
        and model_review_task_id is None
    ):
        task = await context.reviews.create_review(
            AgentReviewRequest(
                task_type="model_disagreement",
                risk_level=risk_level(state.request.source_input),
                title="저장 예측값과 활성 모델 재검증 결과 불일치",
                run_id=state.request.run_id,
                payload={
                    "card_id": state.request.card_id,
                    "model_verification": verification.model_dump(mode="json"),
                },
            )
        )
        model_review_task_id = task.task_id
    return {
        "evidence": state.evidence.model_copy(
            update={"assessment_calls": assessment_calls}
        ),
        "loop": state.loop.model_copy(
            update={
                "assessment": assessment,
                "force_review": assessment.decision == "request_human",
                "model_review_task_id": model_review_task_id,
            }
        )
    }


def route_after_assessment(
    state: AgentState,
) -> Literal[
    "expand_internal_evidence",
    "rerun_model_verification",
    "run_diagnostic_worker",
    "generate_operational_answer",
]:
    assessment = state.loop.assessment
    if assessment is None:
        raise RuntimeError("evidence assessment is missing")
    if assessment.decision == "expand_internal":
        return "expand_internal_evidence"
    if assessment.decision == "rerun_model":
        return "rerun_model_verification"
    if assessment.decision == "diagnostic_worker":
        return "run_diagnostic_worker"
    return "generate_operational_answer"


async def expand_internal_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    iteration = state.loop.iteration + 1
    top_k = min(20, context.runtime.config.rag_top_k + iteration * 3)
    await record_decision(context, state, "expand_internal_evidence")
    external_context = await context.runtime.external_context_for(
        state.request.card_id,
        state.request.source_input,
        top_k=top_k,
    )
    await context.audit.record_event(
        state.request.run_id,
        "evidence_expanded",
        "internal evidence search expanded",
        {"iteration": iteration, "top_k": top_k},
    )
    return {
        "evidence": state.evidence.model_copy(
            update={"external_context": external_context}
        ),
        "loop": state.loop.model_copy(update={"iteration": iteration}),
    }


async def rerun_model_verification(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    attempt = state.evidence.model_attempts + 1
    iteration = state.loop.iteration + 1
    await record_decision(context, state, "rerun_model_verification")
    result, artifact_uri = await _run_model_verification(
        context,
        state,
        attempt=attempt,
    )
    await context.audit.record_event(
        state.request.run_id,
        "model_reverified",
        "active models reverified",
        {"iteration": iteration, **result.model_dump(mode="json")},
    )
    return {
        "evidence": state.evidence.model_copy(
            update={
                "model_verification": result,
                "model_attempts": attempt,
                "active_model_artifact_uri": artifact_uri,
            }
        ),
        "loop": state.loop.model_copy(update={"iteration": iteration}),
    }


async def _run_model_verification(
    context: AgentNodeContext,
    state: AgentState,
    *,
    attempt: int,
) -> tuple[ModelVerificationResult, str | None]:
    snapshot = await context.runtime.verify_models(
        ModelVerificationRequest(
            card_id=state.request.card_id,
            source_input=state.request.source_input,
            attempt=attempt,
        )
    )
    return snapshot.result, snapshot.artifact_uri


def _json_strings(values: list[str]) -> list[JsonValue]:
    return [value for value in values]
