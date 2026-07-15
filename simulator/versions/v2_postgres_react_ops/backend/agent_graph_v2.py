from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from langgraph.types import Checkpointer, Durability
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_stage_adapter import PostgresStageSnapshotAdapter
from agent_v2_adapters import make_v2_adapters
from heatgrid_ops.agent.graph import AgentGraphInvoker
from heatgrid_ops.agent.graph_v2 import (
    AgentV2GraphContext,
    CompiledAgentV2Graph,
    V2GraphInput,
    build_agent_v2_graph,
)
from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import OpsAgentOutput, TokenUsage
from heatgrid_ops.agent.run_models import AgentLoopSummary, AgentRunResult
from heatgrid_ops.agent.state import (
    AgentGraphInput,
    AgentGraphOutput,
    ResultState,
)
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState
from heatgrid_ops.agent.services import AgentRuntime


@dataclass(frozen=True, slots=True)
class ExplicitV2AgentGraph:
    graph: CompiledAgentV2Graph
    max_iterations: int = 4

    @property
    def checkpointer_enabled(self) -> bool:
        return bool(getattr(self.graph, "checkpointer_enabled", False))

    async def ainvoke(
        self,
        input: AgentGraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None,
    ) -> AgentGraphOutput:
        if input is None:
            result = await self.graph.ainvoke(None, config, durability=durability)
        else:
            request = input["request"]
            source_input = request.source_input
            state = AgentV2State(
                request=V2RequestState(
                    run_id=request.run_id,
                    alert_id=request.alert_id,
                    card_id=request.card_id,
                    source_input=source_input,
                    input_hash=canonical_json_hash(source_input),
                )
            )
            result = await self.graph.ainvoke(
                V2GraphInput(
                    state=state,
                    stage_hashes={},
                    completed_stages=(),
                ),
                config,
                durability=durability,
            )
        return _to_legacy_output(result)


def build_agent_graph_v2(
    base: AgentGraphInvoker,
    engine: AsyncEngine,
    *,
    openai_model: str,
    rag_quality_enabled: bool,
    evidence_threshold: float,
    model_score_tolerance: float,
    checkpointer: Checkpointer = None,
    runtime: AgentRuntime | None = None,
) -> AgentGraphInvoker:
    del base, openai_model, model_score_tolerance
    context = AgentV2GraphContext(
        snapshots=PostgresStageSnapshotAdapter(engine),
        adapters={}
        if runtime is None
        else make_v2_adapters(runtime, rag_quality_enabled=rag_quality_enabled),
        component_versions={
            "graph": "agent_graph:v2",
            "adapter": "postgres.v008",
        },
        feature_flags={"rag_quality": rag_quality_enabled},
        thresholds={"evidence": evidence_threshold},
    )
    graph = build_agent_v2_graph(context, checkpointer=checkpointer)
    return ExplicitV2AgentGraph(graph=graph, max_iterations=graph.max_iterations)


def _to_legacy_output(result: object) -> AgentGraphOutput:
    state = TypeAdapter(dict[str, object]).validate_python(result)
    raw_state = state.get("state")
    if not isinstance(raw_state, AgentV2State):
        raw_state = AgentV2State.model_validate(raw_state)
    output = OpsAgentOutput(
        summary="Graph v2 stage execution completed.",
        action_plan="Review the persisted stage evidence and disposition.",
        caution="Stage quality and external evaluator availability are recorded in snapshots.",
    )
    completed_stages = state.get("completed_stages")
    iteration_count = (
        len(completed_stages)
        if isinstance(completed_stages, (tuple, list))
        else 0
    )
    loop_summary = AgentLoopSummary(
        iterations=iteration_count,
        max_iterations=4,
        decision="finalize",
        confidence=1.0,
        evidence_score=100.0,
        review_required=raw_state.routing.force_review,
        disposition=raw_state.routing.disposition,
        blocking_retry_exhausted=list(raw_state.routing.blocking_retry_exhausted),
        graph_contract_version="agent_graph_v2.v2",
    )
    result_model = AgentRunResult(
        run_id=raw_state.request.run_id,
        status="completed",
        input_source="alert",
        alert_id=raw_state.request.alert_id,
        card_id=raw_state.request.card_id,
        agent_mode="fallback",
        ops_output=output,
        token_usage=TokenUsage(),
        loop_summary=loop_summary,
        review_status="pending" if not raw_state.routing.force_review else "pending",
    )
    return {"result": ResultState(value=result_model)}
