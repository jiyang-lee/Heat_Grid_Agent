from __future__ import annotations

from heatgrid_ops.agent.contracts import AgentReviewRequest
from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.external_search import ExternalEvidenceSearchResult
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_candidates import stage_search_hits
from heatgrid_ops.agent.nodes_audit import (
    external_search_query,
    model_drift_score,
    record_decision,
    record_tool_completed,
    record_tool_started,
    tool_json_object,
)
from heatgrid_ops.agent.run_models import AutomationPolicySnapshot, ReviewTaskSnapshot
from heatgrid_ops.agent.state import AgentState
from heatgrid_ops.agent.tools import make_external_search_tool
from heatgrid_ops.approval.policy import (
    ActionExecutionContext,
    ActionExecutionDecision,
    decide_action_execution,
)


async def search_external_evidence(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentState:
    iteration = state.get("loop_iteration", 1) + 1
    query = external_search_query(state)
    await record_decision(context, state, "search_external_evidence")
    policy = await context.reviews.automation_policy()
    config = context.runtime.config
    search_calls = state.get("external_search_calls", 0)
    remaining_budget = max(
        0.0,
        config.external_search_budget_per_run_usd
        - search_calls * config.external_search_estimated_cost_usd,
    )
    allowed_domains = tuple(
        item.strip()
        for item in config.external_search_allowed_domains.split(",")
        if item.strip()
    )
    approved_task_id = state.get("approved_action_task_id")
    approved_task = (
        await context.reviews.review_task(approved_task_id)
        if approved_task_id is not None
        else None
    )
    execution = _execution_decision(
        approved_task,
        policy,
        state,
        config,
        allowed_domains,
        search_calls,
        remaining_budget,
    )
    action_decision: JsonObject = {
        "action": execution.action,
        "task_type": "external_search",
        "reason": execution.reason,
        "iteration": iteration,
        "estimated_cost_usd": config.external_search_estimated_cost_usd,
    }
    await context.audit.record_event(
        state["run_id"],
        "action_policy_decision",
        f"external search policy: {execution.action}",
        action_decision,
    )
    if execution.action != "execute":
        return await _blocked_search(
            context,
            state,
            iteration,
            query,
            allowed_domains,
            execution,
            action_decision,
            search_calls,
        )

    tool_name = "search_external_evidence"
    await record_tool_started(context, state, tool_name)
    tool_result = await make_external_search_tool(
        context.runtime.search_external_evidence
    ).ainvoke({"query": query})
    search = ExternalEvidenceSearchResult.model_validate(tool_json_object(tool_result))
    candidates, candidate_ids = await stage_search_hits(
        context,
        state,
        search,
        query,
        policy,
    )
    await record_tool_completed(
        context,
        state,
        tool_name,
        {"status": search.status, "candidate_count": len(search.hits)},
    )
    await context.audit.record_event(
        state["run_id"],
        "external_candidates_created",
        "external evidence candidates created",
        {"iteration": iteration, "status": search.status, "candidate_ids": candidate_ids},
    )
    return {
        "external_candidates": candidates,
        "external_candidate_ids": candidate_ids,
        "external_search_attempted": True,
        "external_search_calls": search_calls + 1,
        "action_decisions": [*state.get("action_decisions", []), action_decision],
        "loop_iteration": iteration,
        "used_tools": [
            *state.get("used_tools", []),
            tool_name,
            *(["stage_evidence_candidate"] if search.hits else []),
        ],
    }


def _execution_decision(
    approved_task: ReviewTaskSnapshot | None,
    policy: AutomationPolicySnapshot,
    state: AgentState,
    config: AgentRuntimeConfig,
    allowed_domains: tuple[str, ...],
    search_calls: int,
    remaining_budget: float,
) -> ActionExecutionDecision:
    if (
        approved_task is not None
        and approved_task.task_type == "external_search"
        and approved_task.status == "approved"
    ):
        return ActionExecutionDecision(
            action="execute",
            reason="human approved external search task",
            policy_eligible=True,
        )
    return decide_action_execution(
        policy,
        ActionExecutionContext(
            task_type="external_search",
            risk_level="low",
            confidence=state["evidence_assessment"].confidence,
            source_trust=1.0 if allowed_domains else 0.0,
            drift_score=model_drift_score(state),
            used_count=search_calls,
            max_count=config.external_search_max_calls_per_run,
            estimated_cost_usd=config.external_search_estimated_cost_usd,
            remaining_cost_usd=remaining_budget,
        ),
    )


async def _blocked_search(
    context: AgentNodeContext,
    state: AgentState,
    iteration: int,
    query: str,
    allowed_domains: tuple[str, ...],
    execution: ActionExecutionDecision,
    action_decision: JsonObject,
    search_calls: int,
) -> AgentState:
    if execution.action == "human_review":
        task = await context.reviews.create_review(
            AgentReviewRequest(
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
                    "estimated_cost_usd": context.runtime.config.external_search_estimated_cost_usd,
                    "policy_decision": action_decision,
                },
            )
        )
        action_decision["review_task_id"] = task.task_id
        await context.audit.record_event(
            state["run_id"],
            "action_review_requested",
            "external search requires human approval",
            {"task_type": "external_search", "review_task_id": task.task_id},
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
        "action_decisions": [*state.get("action_decisions", []), action_decision],
        "loop_iteration": iteration,
        "force_review": True,
    }
