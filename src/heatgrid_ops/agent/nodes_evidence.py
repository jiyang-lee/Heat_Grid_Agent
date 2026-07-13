from __future__ import annotations

from typing import Literal

from heatgrid_ops.agent.contracts import AgentLoopIterationRecord, AgentReviewRequest
from heatgrid_ops.agent.model_verification import verify_models
from heatgrid_ops.agent.models import ModelVerificationResult
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import record_decision
from heatgrid_ops.agent.state import AgentState


async def verify_model_output(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
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
    response: AgentState = {"model_verification": result, "model_attempts": 1}
    if artifact_uri:
        response["active_model_artifact_uri"] = artifact_uri
    return response


async def assess_collected_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    iteration = state.get("loop_iteration", 1)
    assessment = await context.runtime.assess_evidence(
        source_input=state["source_input"],
        external_context=state["external_context"],
        model_verification=state.get("model_verification"),
        iteration=iteration,
        max_iterations=state.get("max_iterations", context.runtime.config.agent_max_iterations),
        external_candidate_count=len(state.get("external_candidate_ids", [])),
        external_search_attempted=state.get("external_search_attempted", False),
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
    await context.audit.record_event(
        state["run_id"],
        "loop_decision",
        f"loop decision: {assessment.decision}",
        {
            "iteration": iteration,
            "decision": assessment.decision,
            "confidence": assessment.confidence,
            "evidence_score": assessment.evidence_score,
            "missing_evidence": assessment.missing_evidence,
            "decision_source": assessment.decision_source,
        },
    )
    response: AgentState = {
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
    "search_external_evidence",
    "rerun_model_verification",
    "generate_operational_answer",
]:
    if state.get("approved_action_task_id") and not state.get(
        "external_search_attempted",
        False,
    ):
        return "search_external_evidence"
    return {
        "expand_internal": "expand_internal_evidence",
        "search_external": "search_external_evidence",
        "rerun_model": "rerun_model_verification",
        "request_human": "generate_operational_answer",
        "finalize": "generate_operational_answer",
    }[state["evidence_assessment"].decision]


async def expand_internal_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    iteration = state.get("loop_iteration", 1) + 1
    top_k = min(20, context.runtime.config.rag_top_k + iteration * 3)
    await record_decision(context, state, "expand_internal_evidence")
    external_context = context.runtime.external_context_for(
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
) -> AgentState:
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
    response: AgentState = {
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
    features = await context.model_data.feature_values(state["card_id"])
    if not features:
        features = _feature_values_from_source(state)
    artifact_uri = await context.model_data.active_artifact_uri()
    snapshot = await context.model_data.infer(
        features,
        state["source_input"],
        artifact_uri,
    )
    result = verify_models(
        snapshot,
        features,
        state["source_input"],
        tolerance=context.runtime.config.model_score_tolerance,
        attempt=attempt,
    )
    evaluation_context = state["source_input"].get("evaluation_context")
    if not isinstance(evaluation_context, dict):
        return result, artifact_uri
    evaluation = evaluation_context.get("evaluation")
    snapshot_result = evaluation_context.get("result")
    return (
        result.model_copy(
            update={
                "evaluation_run_id": evaluation.get("evaluation_run_id")
                if isinstance(evaluation, dict)
                else None,
                "manufacturer_id": snapshot_result.get("manufacturer_id")
                if isinstance(snapshot_result, dict)
                else None,
                "substation_id": snapshot_result.get("substation_id")
                if isinstance(snapshot_result, dict)
                else None,
            }
        ),
        artifact_uri,
    )


def _feature_values_from_source(state: AgentState) -> dict[str, float]:
    raw_context = state["source_input"].get("raw_context")
    summaries = raw_context.get("sensor_summaries") if isinstance(raw_context, dict) else None
    if not isinstance(summaries, list):
        return {}
    values: dict[str, float] = {}
    for item in summaries:
        if not isinstance(item, dict):
            continue
        name = item.get("feature_name")
        value = item.get("feature_value")
        if not isinstance(name, str):
            continue
        try:
            values[name] = float(value)
        except (TypeError, ValueError):
            continue
    return values


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
