from __future__ import annotations

from typing import Literal, Protocol

import orjson
from fastapi import HTTPException
from openai import OpenAIError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_loop_repository import insert_agent_loop_iteration
from alert_repository import get_alert
from agent_run_event_repository import AgentRunEventRecord
from agent_run_repository import (
    complete_agent_run,
    mark_agent_run_running,
    record_agent_run_event,
)
from heatgrid_ops.agent.assessment import validate_output as validate_ops_output
from heatgrid_ops.agent.contracts import SimulateCard
from heatgrid_ops.agent.external_search import ExternalEvidenceSearchResult
from heatgrid_ops.agent.helpers import fallback_note
from heatgrid_ops.agent.model_verification import verify_models
from heatgrid_ops.agent.services import AgentRuntime, MissingApiKeyError
from heatgrid_ops.agent.state import AgentState
from heatgrid_ops.agent.tools import (
    ReportToolPayloadError,
    make_external_search_tool,
    make_stage_evidence_candidate_tool,
)
from heatgrid_ops.approval.policy import (
    ActionExecutionDecision,
    ActionExecutionContext,
    ApprovalPolicyContext,
    decide_action_execution,
    decide_approval,
)
from heatgrid_ops.priority.evaluation import get_priority_evaluation_result
from model_feature_repository import fetch_model_feature_snapshot
from repository import fetch_ops_input
from retrain_repository import get_active_model_deployment
from review_repository import (
    create_evidence_candidate,
    create_review_task,
    get_automation_policy,
    get_review_task,
)
from schemas import (
    AgentLoopSummary,
    EvidenceCandidateCreateRequest,
    JsonValue,
    ModelVerificationResult,
    SimulationResponse,
)
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
    alert = await get_alert(context.engine, state["alert_id"])
    if (
        alert is not None
        and alert.get("evaluation_run_id") is not None
        and alert.get("substation_id") is not None
    ):
        evaluation_context = await get_priority_evaluation_result(
            context.engine,
            str(alert["evaluation_run_id"]),
            int(alert["substation_id"]),
            manufacturer_id=str(alert["manufacturer_id"])
            if alert.get("manufacturer_id") is not None
            else None,
        )
        if evaluation_context is not None:
            source_input["evaluation_context"] = evaluation_context
            sections = source_input.get("sections")
            if isinstance(sections, dict):
                sections["evaluation"] = evaluation_context
    return {"source_input": source_input}


async def get_ops_evidence(context: AgentNodeContext, state: AgentState) -> AgentState:
    await record_decision(context, state, "get_ops_evidence")
    await record_tool_started(context, state, "get_ops_evidence")
    source_input = state["source_input"]
    tools = {
        item.name: item
        for item in context.runtime.tools_for(source_input, {"status": "pending"})
    }
    evidence_payload = tools["get_ops_evidence"].invoke(
        {"card_id": state["card_id"]}
    )
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
    collected_context = context.runtime.external_context_for(
        state["card_id"],
        state["source_input"],
    )
    tools = {
        item.name: item
        for item in context.runtime.tools_for(state["source_input"], collected_context)
    }

    await record_tool_started(context, state, "get_external_context")
    context_payload = tools["get_external_context"].invoke(
        {"card_id": state["card_id"]}
    )
    external_context = _tool_json_object(context_payload)
    await record_tool_completed(
        context,
        state,
        "get_external_context",
        {"status": str(external_context.get("status") or "unknown")},
    )

    await record_tool_started(context, state, "get_internal_references")
    references_payload = tools["get_internal_references"].invoke(
        {"card_id": state["card_id"]}
    )
    internal_references = _tool_json_object(references_payload)
    external_context.update(internal_references)
    retrieval = external_context.get("retrieval")
    retrieval_status = (
        retrieval.get("status")
        if isinstance(retrieval, dict)
        else external_context.get("status")
    )
    await record_tool_completed(
        context,
        state,
        "get_internal_references",
        {"status": str(retrieval_status or "unknown")},
    )
    return {
        "external_context": external_context,
        "used_tools": [
            *state.get("used_tools", []),
            "get_external_context",
            "get_internal_references",
        ],
    }


async def verify_model_output(context: AgentNodeContext, state: AgentState) -> AgentState:
    await record_decision(context, state, "verify_active_models")
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="model_verification_started",
            message="active model verification started",
            payload={"attempt": 1},
        ),
    )
    result, artifact_uri = await _run_model_verification(context, state, attempt=1)
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="model_verification",
            message="active models verified",
            payload=result.model_dump(mode="json"),
        ),
    )
    response: AgentState = {
        "model_verification": result,
        "model_attempts": 1,
    }
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
        max_iterations=state.get(
            "max_iterations", context.runtime.settings.agent_max_iterations
        ),
        external_candidate_count=len(state.get("external_candidate_ids", [])),
        external_search_attempted=state.get("external_search_attempted", False),
    )
    await insert_agent_loop_iteration(
        context.engine,
        run_id=state["run_id"],
        iteration=iteration,
        phase="evidence_assessment",
        decision=assessment.decision,
        confidence=assessment.confidence,
        evidence_score=assessment.evidence_score,
        missing_evidence=assessment.missing_evidence,
        model_verification=state.get("model_verification"),
    )
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="loop_decision",
            message=f"loop decision: {assessment.decision}",
            payload={
                "iteration": iteration,
                "decision": assessment.decision,
                "confidence": assessment.confidence,
                "evidence_score": assessment.evidence_score,
                "missing_evidence": assessment.missing_evidence,
                "decision_source": assessment.decision_source,
            },
        ),
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
        task = await create_review_task(
            context.engine,
            task_type="model_disagreement",
            risk_level=_risk_level(state["source_input"]),
            title="저장 예측값과 활성 모델 재검증 결과 불일치",
            run_id=state["run_id"],
            payload={
                "card_id": state["card_id"],
                "model_verification": verification.model_dump(mode="json"),
            },
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
    decision = state["evidence_assessment"].decision
    return {
        "expand_internal": "expand_internal_evidence",
        "search_external": "search_external_evidence",
        "rerun_model": "rerun_model_verification",
        "request_human": "generate_operational_answer",
        "finalize": "generate_operational_answer",
    }[decision]


async def expand_internal_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    iteration = state.get("loop_iteration", 1) + 1
    top_k = min(20, context.runtime.settings.rag_top_k + iteration * 3)
    await record_decision(context, state, "expand_internal_evidence")
    external_context = context.runtime.external_context_for(
        state["card_id"],
        state["source_input"],
        top_k=top_k,
    )
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="evidence_expanded",
            message="internal evidence search expanded",
            payload={"iteration": iteration, "top_k": top_k},
        ),
    )
    return {
        "external_context": external_context,
        "loop_iteration": iteration,
    }


async def search_external_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    iteration = state.get("loop_iteration", 1) + 1
    query = _external_search_query(state)
    await record_decision(context, state, "search_external_evidence")
    policy = await get_automation_policy(context.engine)
    settings = context.runtime.settings
    search_calls = state.get("external_search_calls", 0)
    remaining_budget = max(
        0.0,
        settings.external_search_budget_per_run_usd
        - search_calls * settings.external_search_estimated_cost_usd,
    )
    allowed_domains = tuple(
        item.strip()
        for item in settings.external_search_allowed_domains.split(",")
        if item.strip()
    )
    approved_task_id = state.get("approved_action_task_id")
    approved_task = (
        await get_review_task(context.engine, approved_task_id)
        if approved_task_id
        else None
    )
    if (
        approved_task is not None
        and approved_task.task_type == "external_search"
        and approved_task.status == "approved"
    ):
        execution = ActionExecutionDecision(
            action="execute",
            reason=f"human approved external search task {approved_task.task_id}",
            policy_eligible=True,
        )
    else:
        execution = decide_action_execution(
            policy,
            ActionExecutionContext(
                task_type="external_search",
                risk_level="low",
                confidence=state["evidence_assessment"].confidence,
                source_trust=1.0 if allowed_domains else 0.0,
                drift_score=_model_drift_score(state),
                used_count=search_calls,
                max_count=settings.external_search_max_calls_per_run,
                estimated_cost_usd=settings.external_search_estimated_cost_usd,
                remaining_cost_usd=remaining_budget,
            ),
        )
    action_decision = {
        "action": execution.action,
        "task_type": "external_search",
        "reason": execution.reason,
        "iteration": iteration,
        "estimated_cost_usd": settings.external_search_estimated_cost_usd,
    }
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="action_policy_decision",
            message=f"external search policy: {execution.action}",
            payload=action_decision,
        ),
    )
    if execution.action != "execute":
        if execution.action == "human_review":
            task = await create_review_task(
                context.engine,
                task_type="external_search",
                risk_level="low",
                title="External evidence search approval",
                run_id=state["run_id"],
                payload={
                    "run_id": state["run_id"],
                    "alert_id": state["alert_id"],
                    "card_id": state["card_id"],
                    "query": query,
                    "allowed_domains": list(allowed_domains),
                    "estimated_cost_usd": settings.external_search_estimated_cost_usd,
                    "policy_decision": action_decision,
                },
            )
            action_decision["review_task_id"] = task.task_id
            await record_agent_run_event(
                context.engine,
                AgentRunEventRecord(
                    run_id=state["run_id"],
                    event_type="action_review_requested",
                    message="external search requires human approval",
                    payload={
                        "task_type": "external_search",
                        "review_task_id": task.task_id,
                    },
                ),
            )
        external_context = dict(state["external_context"])
        external_context["external_search"] = {
            "status": "blocked",
            "decision": execution.action,
            "reason": execution.reason,
        }
        return {
            "external_context": external_context,
            "external_search_attempted": True,
            "external_search_calls": search_calls,
            "action_decisions": [
                *state.get("action_decisions", []),
                action_decision,
            ],
            "loop_iteration": iteration,
            "force_review": True,
        }

    await record_tool_started(context, state, "search_external_evidence")
    tool_result = await make_external_search_tool(
        context.runtime.search_external_evidence
    ).ainvoke({"query": query})
    search = ExternalEvidenceSearchResult.model_validate(
        _tool_json_object(tool_result)
    )
    candidates = list(state.get("external_candidates", []))
    candidate_ids = list(state.get("external_candidate_ids", []))
    risk_level = _risk_level(state["source_input"])
    for hit in search.hits:
        approval = decide_approval(
            policy,
            ApprovalPolicyContext(
                task_type="evidence_candidate",
                risk_level=risk_level,
                confidence=hit.trust_score,
                source_trust=hit.trust_score,
            ),
        )
        auto = approval.action == "auto_approve"
        candidate_payload = EvidenceCandidateCreateRequest(
            run_id=state["run_id"],
            source_type="web",
            source_uri=hit.url,
            title=hit.title,
            content=hit.content,
            query=query,
            risk_level=risk_level,
            trust_score=hit.trust_score,
            metadata=hit.metadata,
            requested_by="agent-loop",
        )
        stage_result = await make_stage_evidence_candidate_tool(
            lambda payload: _stage_evidence_candidate(context, payload)
        ).ainvoke(
            {
                "payload_json": orjson.dumps(
                    {
                        "candidate": candidate_payload.model_dump(mode="json"),
                        "status": "auto_approved" if auto else "pending",
                        "reviewed_by": "automation-policy" if auto else None,
                        "review_reason": approval.reason if auto else None,
                    }
                ).decode("utf-8")
            }
        )
        candidate = _tool_json_object(stage_result)
        candidate_ids.append(str(candidate["candidate_id"]))
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "title": candidate["title"],
                "content": candidate["content"],
                "source_uri": candidate.get("source_uri"),
                "status": candidate["status"],
                "trust_score": candidate["trust_score"],
            }
        )
    await record_tool_completed(
        context,
        state,
        "search_external_evidence",
        {"status": search.status, "candidate_count": len(search.hits)},
    )
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="external_candidates_created",
            message="external evidence candidates created",
            payload={
                "iteration": iteration,
                "status": search.status,
                "candidate_ids": candidate_ids,
            },
        ),
    )
    return {
        "external_candidates": candidates,
        "external_candidate_ids": candidate_ids,
        "external_search_attempted": True,
        "external_search_calls": search_calls + 1,
        "action_decisions": [
            *state.get("action_decisions", []),
            action_decision,
        ],
        "loop_iteration": iteration,
        "used_tools": [
            *state.get("used_tools", []),
            "search_external_evidence",
            *(["stage_evidence_candidate"] if search.hits else []),
        ],
    }


async def rerun_model_verification(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    attempt = state.get("model_attempts", 1) + 1
    iteration = state.get("loop_iteration", 1) + 1
    await record_decision(context, state, "rerun_model_verification")
    result, artifact_uri = await _run_model_verification(context, state, attempt=attempt)
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="model_reverified",
            message="active models reverified",
            payload={
                "iteration": iteration,
                **result.model_dump(mode="json"),
            },
        ),
    )
    response: AgentState = {
        "model_verification": result,
        "model_attempts": attempt,
        "loop_iteration": iteration,
    }
    if artifact_uri:
        response["active_model_artifact_uri"] = artifact_uri
    return response


async def generate_operational_answer(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    await record_decision(context, state, "generate_operational_answer")
    legacy = context.legacy_simulate_card
    if legacy is not None:
        simulation = await legacy(state["card_id"])
        return {
            "ops_output": simulation.ops_output,
            "token_usage": simulation.token_usage,
            "agent_mode": simulation.agent_mode,
        }
    enriched_context = _enriched_external_context(state)
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
            external_candidates=state.get("external_candidates"),
            revision_feedback=state.get("revision_feedback"),
            usage=usage,
        )
    except (MissingApiKeyError, OpenAIError, ValidationError):
        return {"token_usage": usage, "agent_mode": "fallback"}
    return {"ops_output": output, "token_usage": usage, "agent_mode": "llm"}


async def generate_fallback_output(context: AgentNodeContext, state: AgentState) -> AgentState:
    enriched_context = _enriched_external_context(state)
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


async def validate_output(context: AgentNodeContext, state: AgentState) -> AgentState:
    output = state["ops_output"]
    validation = validate_ops_output(output, agent_mode=state["agent_mode"])
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
                "used_tools": used_tools,
                "validation": validation.model_dump(mode="json"),
            },
        ),
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


async def prepare_output_retry(context: AgentNodeContext, state: AgentState) -> AgentState:
    iteration = state.get("loop_iteration", 1) + 1
    issues = state["output_validation"].issues
    await insert_agent_loop_iteration(
        context.engine,
        run_id=state["run_id"],
        iteration=iteration,
        phase="output_revision",
        decision="revise_output",
        confidence=state["output_validation"].score,
        evidence_score=state["evidence_assessment"].evidence_score,
        missing_evidence=issues,
        model_verification=state.get("model_verification"),
    )
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="output_retry",
            message="output validation requested one revision",
            payload={"iteration": iteration, "issues": issues},
        ),
    )
    return {
        "loop_iteration": iteration,
        "revision_count": state.get("revision_count", 0) + 1,
        "revision_feedback": issues,
    }


async def create_final_review(context: AgentNodeContext, state: AgentState) -> AgentState:
    assessment = state["evidence_assessment"]
    task = await create_review_task(
        context.engine,
        task_type="final_output",
        risk_level=_risk_level(state["source_input"]),
        title=f"에이전트 최종 운영 결과 검수: {state['card_id']}",
        run_id=state["run_id"],
        payload={
            "card_id": state["card_id"],
            "ops_output": state["ops_output"].model_dump(mode="json"),
            "evidence_assessment": assessment.model_dump(mode="json"),
            "model_verification": state["model_verification"].model_dump(mode="json"),
            "external_candidate_ids": state.get("external_candidate_ids", []),
            "used_tools": state.get("used_tools", []),
            "action_decisions": state.get("action_decisions", []),
            "output_validation": state["output_validation"].model_dump(mode="json"),
        },
    )
    await record_agent_run_event(
        context.engine,
        AgentRunEventRecord(
            run_id=state["run_id"],
            event_type="review_requested",
            message="final human review requested",
            payload={"task_id": task.task_id, "task_type": task.task_type},
        ),
    )
    return {"review_task_id": task.task_id}


async def complete_run(context: AgentNodeContext, state: AgentState) -> AgentState:
    usage = usage_with_totals(state["token_usage"], context.runtime.settings)
    assessment = state["evidence_assessment"]
    loop_summary = AgentLoopSummary(
        iterations=state.get("loop_iteration", 1),
        max_iterations=state.get(
            "max_iterations", context.runtime.settings.agent_max_iterations
        ),
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
    simulation = SimulationResponse(
        card_id=state["card_id"],
        input_source="postgresql",
        agent_mode=state["agent_mode"],
        ops_output=state["ops_output"],
        token_usage=usage,
    )
    result = await complete_agent_run(
        context.engine,
        state["run_id"],
        simulation,
        loop_summary=loop_summary,
        review_task_id=state.get("review_task_id"),
    )
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
            event_type="graph_transition",
            message=f"graph entered {next_step}",
            payload={"next": next_step, "decision_source": "graph"},
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
    payload: dict[str, JsonValue],
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


async def _run_model_verification(
    context: AgentNodeContext,
    state: AgentState,
    *,
    attempt: int,
) -> tuple[ModelVerificationResult, str | None]:
    features = await fetch_model_feature_snapshot(context.engine, state["card_id"])
    if not features:
        features = _feature_values_from_source(state["source_input"])
    deployment = await get_active_model_deployment(context.engine)
    artifact_uri = None if deployment is None else deployment.artifact_uri
    result = verify_models(
        features,
        state["source_input"],
        tolerance=context.runtime.settings.model_score_tolerance,
        attempt=attempt,
        active_artifact_uri=artifact_uri,
    )
    evaluation_context = state["source_input"].get("evaluation_context")
    if isinstance(evaluation_context, dict):
        evaluation = evaluation_context.get("evaluation")
        snapshot_result = evaluation_context.get("result")
        result = result.model_copy(
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
        )
    return result, artifact_uri


def _feature_values_from_source(source_input: dict[str, JsonValue]) -> dict[str, float]:
    raw_context = source_input.get("raw_context")
    summaries = raw_context.get("sensor_summaries") if isinstance(raw_context, dict) else None
    values: dict[str, float] = {}
    if not isinstance(summaries, list):
        return values
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


def _enriched_external_context(state: AgentState) -> dict[str, JsonValue]:
    context = dict(state["external_context"])
    context["model_verification"] = state["model_verification"].model_dump(mode="json")
    context["evidence_assessment"] = state["evidence_assessment"].model_dump(mode="json")
    if state.get("external_candidates"):
        context["pending_external_evidence"] = state["external_candidates"]
    return context


def _external_search_query(state: AgentState) -> str:
    assessment = state["evidence_assessment"]
    priority_context = state["source_input"].get("priority_context")
    explanation = (
        priority_context.get("explanation") if isinstance(priority_context, dict) else None
    )
    recommended = explanation.get("recommended_action") if isinstance(explanation, dict) else ""
    terms = [*assessment.missing_evidence, str(recommended or ""), "지역난방 운영 점검"]
    return " ".join(item for item in terms if item).strip()


def _risk_level(source_input: dict[str, JsonValue]) -> Literal["low", "medium", "high", "critical"]:
    priority_context = source_input.get("priority_context")
    priority = priority_context.get("priority") if isinstance(priority_context, dict) else None
    level = str(priority.get("priority_level") or "medium").lower() if isinstance(priority, dict) else "medium"
    if level == "urgent":
        return "critical"
    if level == "high":
        return "high"
    if level == "low":
        return "low"
    return "medium"


def _model_drift_score(state: AgentState) -> float:
    verification = state.get("model_verification")
    if verification is None or verification.risk_score_delta is None:
        return 0.0
    return min(1.0, abs(float(verification.risk_score_delta)))


async def _stage_evidence_candidate(
    context: AgentNodeContext,
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    candidate_payload = payload.get("candidate")
    if not isinstance(candidate_payload, dict):
        raise ReportToolPayloadError("candidate must be a JSON object")
    status = str(payload.get("status") or "pending")
    if status not in {"pending", "auto_approved"}:
        raise ReportToolPayloadError("unsupported evidence candidate status")
    reviewed_by_value = payload.get("reviewed_by")
    review_reason_value = payload.get("review_reason")
    reviewed_by = reviewed_by_value if isinstance(reviewed_by_value, str) else None
    review_reason = (
        review_reason_value if isinstance(review_reason_value, str) else None
    )
    request = EvidenceCandidateCreateRequest.model_validate(candidate_payload)
    candidate = await create_evidence_candidate(
        context.engine,
        request,
        status=status,
        reviewed_by=reviewed_by,
        review_reason=review_reason,
    )
    await create_review_task(
        context.engine,
        task_type="evidence_candidate",
        risk_level=request.risk_level,
        title=f"외부 근거 후보 검수: {candidate.title}",
        run_id=request.run_id,
        candidate_id=candidate.candidate_id,
        payload=candidate.model_dump(mode="json"),
        status=status,
        reviewed_by=reviewed_by,
    )
    return candidate.model_dump(mode="json")


def _tool_json_object(payload: str) -> dict[str, JsonValue]:
    value = orjson.loads(payload)
    if not isinstance(value, dict):
        raise ReportToolPayloadError("tool result must be a JSON object")
    return value
