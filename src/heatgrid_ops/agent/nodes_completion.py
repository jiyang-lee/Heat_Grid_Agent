from __future__ import annotations

from typing import Literal

from heatgrid_ops.agent.contracts import AgentRunCompletion
from heatgrid_ops.agent.models import OpsAgentOutput, SimulationResponse, TokenUsage
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.run_models import AgentLoopSummary
from heatgrid_ops.agent.review_capture import try_build_review_capture_source
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate
from heatgrid_ops.agent.usage import usage_with_totals


async def complete_run(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    usage = usage_with_totals(_required_usage(state), context.runtime.config)
    assessment = state.loop.assessment
    if assessment is None:
        raise RuntimeError("evidence assessment is missing")
    loop_summary = AgentLoopSummary(
        iterations=state.loop.iteration,
        max_iterations=state.loop.max_iterations,
        decision=assessment.decision,
        confidence=assessment.confidence,
        evidence_score=assessment.evidence_score,
        missing_evidence=assessment.missing_evidence,
        used_tools=state.audit.used_tools,
        action_decisions=state.audit.action_decisions,
        model_verification=state.evidence.model_verification,
        review_required=True,
        review_task_id=state.loop.review_task_id,
    )
    result = await context.lifecycle.complete(
        state.request.run_id,
        AgentRunCompletion(
            simulation=SimulationResponse(
                card_id=state.request.card_id,
                input_source="postgresql",
                agent_mode=_required_mode(state),
                ops_output=_required_output(state),
                token_usage=usage,
            ),
            loop_summary=loop_summary,
            review_task_id=state.loop.review_task_id,
        ),
    )
    capture_source = try_build_review_capture_source(state, result)
    return {
        "result": state.result.model_copy(
            update={"value": result, "review_capture_source": capture_source}
        ),
        "output": state.output.model_copy(update={"token_usage": usage}),
    }


def _required_output(state: AgentState) -> OpsAgentOutput:
    if state.output.value is None:
        raise RuntimeError("agent output is missing")
    return state.output.value


def _required_usage(state: AgentState) -> TokenUsage:
    if state.output.token_usage is None:
        raise RuntimeError("token usage is missing")
    return state.output.token_usage


def _required_mode(state: AgentState) -> Literal["llm", "fallback"]:
    if state.output.mode is None:
        raise RuntimeError("agent mode is missing")
    return state.output.mode
