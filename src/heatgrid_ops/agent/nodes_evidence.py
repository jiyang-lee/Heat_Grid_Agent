from __future__ import annotations

from typing import Literal

from heatgrid_ops.agent.contracts import AgentLoopIterationRecord, AgentReviewRequest
from heatgrid_ops.agent.models import JsonObject, JsonValue, ModelVerificationResult
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import record_decision
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate
from heatgrid_ops.agent.run_models import ModelVerificationRequest


async def verify_model_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    await record_decision(context, state, "verify_active_models")
    await context.audit.record_event(
        state["run_id"],
        "model_verification_started",
        "active model verification started",
        {"attempt": 1},
    )
    result, artifact_uri = await _run_model_verification(context, state, attempt=1)
    await context.audit.record_event(
        state["run_id"],
        "model_verification",
        "active models verified",
        result.model_dump(mode="json"),
    )
    response: AgentStateUpdate = {"model_verification": result, "model_attempts": 1}
    if artifact_uri:
        response["active_model_artifact_uri"] = artifact_uri
    return response


async def assess_collected_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    iteration = state.get("loop_iteration", 1)
    assessment = await context.runtime.assess_evidence(
        source_input=state["source_input"],
        evidence_context=state["external_context"],
        model_verification=state.get("model_verification"),
        iteration=iteration,
        max_iterations=state.get("max_iterations", context.runtime.config.agent_max_iterations),
    )
    await context.audit.record_loop_iteration(
        AgentLoopIterationRecord(
            run_id=state["run_id"],
            iteration=iteration,
            phase="evidence_assessment",
            decision=assessment.decision,
            confidence=assessment.confidence,
            evidence_score=assessment.evidence_score,
            missing_evidence=assessment.missing_evidence,
            model_verification=state.get("model_verification"),
        )
    )
    decision_payload: JsonObject = {
        "iteration": iteration,
        "decision": assessment.decision,
        "confidence": assessment.confidence,
        "evidence_score": assessment.evidence_score,
        "missing_evidence": _json_strings(assessment.missing_evidence),
        "decision_source": assessment.decision_source,
    }
    await context.audit.record_event(
        state["run_id"],
        "loop_decision",
        f"loop decision: {assessment.decision}",
        decision_payload,
    )
    response: AgentStateUpdate = {
        "evidence_assessment": assessment,
        "force_review": assessment.decision == "request_human",
    }
    verification = state.get("model_verification")
    if (
        assessment.decision == "request_human"
        and verification is not None
        and verification.agreement is False
        and not state.get("model_review_task_id")
    ):
        task = await context.reviews.create_review(
            AgentReviewRequest(
                task_type="model_disagreement",
                risk_level=_risk_level(state),
                title="저장 예측값과 활성 모델 재검증 결과 불일치",
                run_id=state["run_id"],
                payload={
                    "card_id": state["card_id"],
                    "model_verification": verification.model_dump(mode="json"),
                },
            )
        )
        response["model_review_task_id"] = task.task_id
    return response


def route_after_assessment(
    state: AgentState,
) -> Literal[
    "expand_internal_evidence",
    "rerun_model_verification",
    "generate_operational_answer",
]:
    decision = state["evidence_assessment"].decision
    if decision == "expand_internal":
        return "expand_internal_evidence"
    if decision == "rerun_model":
        return "rerun_model_verification"
    return "generate_operational_answer"


async def expand_internal_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    iteration = state.get("loop_iteration", 1) + 1
    top_k = min(20, context.runtime.config.rag_top_k + iteration * 3)
    await record_decision(context, state, "expand_internal_evidence")
    external_context = await context.runtime.external_context_for(
        state["card_id"],
        state["source_input"],
        top_k=top_k,
    )
    await context.audit.record_event(
        state["run_id"],
        "evidence_expanded",
        "internal evidence search expanded",
        {"iteration": iteration, "top_k": top_k},
    )
    return {"external_context": external_context, "loop_iteration": iteration}


async def rerun_model_verification(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    attempt = state.get("model_attempts", 1) + 1
    iteration = state.get("loop_iteration", 1) + 1
    await record_decision(context, state, "rerun_model_verification")
    result, artifact_uri = await _run_model_verification(context, state, attempt=attempt)
    await context.audit.record_event(
        state["run_id"],
        "model_reverified",
        "active models reverified",
        {"iteration": iteration, **result.model_dump(mode="json")},
    )
    response: AgentStateUpdate = {
        "model_verification": result,
        "model_attempts": attempt,
        "loop_iteration": iteration,
    }
    if artifact_uri:
        response["active_model_artifact_uri"] = artifact_uri
    return response


async def _run_model_verification(
    context: AgentNodeContext,
    state: AgentState,
    *,
    attempt: int,
) -> tuple[ModelVerificationResult, str | None]:
    snapshot = await context.runtime.verify_models(
        ModelVerificationRequest(
            card_id=state["card_id"],
            source_input=state["source_input"],
            attempt=attempt,
        )
    )
    return snapshot.result, snapshot.artifact_uri


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
