from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

from langchain_core.runnables import RunnableConfig
from langgraph.types import Checkpointer, Durability
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_stage_adapter import PostgresStageSnapshotAdapter
from agent_stage_repository import (
    StageSnapshotDraft,
    insert_stage_snapshot,
    list_stage_snapshots,
    resolve_original_stage_snapshot,
)
from agent_v2_result import (
    build_v2_graph_output,
    persist_completed_v2_run,
    v2_state_from_graph_result,
)
from agent_v2_adapters import make_v2_adapters
from heatgrid_ops.agent.graph import AgentGraphInvoker
from heatgrid_ops.agent.graph_v2 import (
    AgentV2GraphContext,
    CompiledAgentV2Graph,
    V2GraphInput,
    build_agent_v2_graph,
    hydrate_v2_prefix,
)
from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.state import AgentGraphInput, AgentGraphOutput
from heatgrid_ops.agent.v2_models import STAGE_ORDER, StageName
from heatgrid_ops.agent.v2_policy import v2_stage_input_hash
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState
from heatgrid_ops.agent.v2_stage_contracts import stage_contract_version
from heatgrid_ops.agent.services import AgentRuntime


@dataclass(frozen=True, slots=True)
class ExplicitV2AgentGraph:
    graph: CompiledAgentV2Graph
    context: AgentV2GraphContext
    engine: AsyncEngine
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
        started_at_ns = perf_counter_ns()
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
                    target_stage=_target_stage(config),
                )
            )
            await _hydrate_parent_prefix(self.engine, self.context, state)
            hydrated, hashes, completed, start_stage = await hydrate_v2_prefix(
                self.context,
                state,
            )
            result = await self.graph.ainvoke(
                V2GraphInput(
                    state=hydrated,
                    stage_hashes=hashes,
                    completed_stages=completed,
                    start_stage=start_stage,
                ),
                config,
                durability=durability,
            )
        execution_duration_ms = (perf_counter_ns() - started_at_ns) // 1_000_000
        output = build_v2_graph_output(result, execution_duration_ms=execution_duration_ms)
        await persist_completed_v2_run(
            self.engine,
            output,
            state=v2_state_from_graph_result(result),
        )
        return output


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
    return ExplicitV2AgentGraph(
        graph=graph,
        context=context,
        engine=engine,
        max_iterations=graph.max_iterations,
    )


def _target_stage(config: RunnableConfig) -> StageName | None:
    configurable = config.get("configurable") or {}
    value = configurable.get("target_stage")
    if not isinstance(value, str) or value not in STAGE_ORDER:
        return None
    return value


async def _hydrate_parent_prefix(
    engine: AsyncEngine,
    context: AgentV2GraphContext,
    state: AgentV2State,
) -> None:
    if state.request.target_stage is None:
        return
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT parent_run_id, input_hash FROM agent_runs "
                "WHERE run_id = :run_id"
            ),
            {"run_id": state.request.run_id},
        )
        row = result.mappings().one_or_none()
    if row is None or row["parent_run_id"] is None:
        return
    if row["input_hash"] is not None and str(row["input_hash"]) != state.request.input_hash:
        return
    parent_run_id = str(row["parent_run_id"])
    parent = {item.stage_name: item for item in await list_stage_snapshots(engine, parent_run_id)}
    existing = {item.stage_name for item in await list_stage_snapshots(engine, state.request.run_id)}
    upstream: list[str] = []
    target_index = STAGE_ORDER.index(state.request.target_stage)
    async with engine.begin() as connection:
        for stage_name in STAGE_ORDER[:target_index]:
            if stage_name in existing:
                source = parent.get(stage_name)
                if source is not None:
                    upstream.append(source.output_hash)
                continue
            source = parent.get(stage_name)
            if source is None or source.execution_status != "passed":
                return
            if source.state_schema_version != state.state_schema_version:
                return
            if source.contract_version != stage_contract_version(stage_name):
                return
            if source.component_versions != dict(context.component_versions):
                return
            if canonical_json_hash(source.output_snapshot) != source.output_hash:
                return
            output_data = source.output_snapshot.get("data")
            if not isinstance(output_data, dict):
                return
            expected = v2_stage_input_hash(
                run_input_hash=state.request.input_hash,
                stage_name=stage_name,
                upstream_output_hashes=tuple(upstream),
                component_versions=context.component_versions,
                feature_flags=context.feature_flags,
                thresholds=context.thresholds,
                attempt_parameters={"attempt": source.attempt},
            )
            if source.stage_input_hash != expected:
                return
            original = await resolve_original_stage_snapshot(
                connection,
                source.stage_snapshot_id,
            )
            if original.execution_status != "passed":
                return
            reused = await insert_stage_snapshot(
                connection,
                StageSnapshotDraft(
                    run_id=state.request.run_id,
                    stage_name=stage_name,
                    stage_kind=source.stage_kind,
                    execution_status="reused",
                    quality_status=source.quality_status,
                    score=source.score,
                    run_input_hash=state.request.input_hash,
                    upstream_output_hashes=tuple(upstream),
                    output_snapshot=output_data,
                    contract_version=stage_contract_version(stage_name),
                    component_versions=dict(context.component_versions),
                    feature_flags=dict(context.feature_flags),
                    thresholds=dict(context.thresholds),
                    attempt=source.attempt,
                    reused_from_snapshot_id=original.stage_snapshot_id,
                    state_schema_version=state.state_schema_version,
                    envelope=source.output_snapshot,
                    policy_version="agent_graph_v2.v3",
                    attempt_parameters={"attempt": source.attempt},
                ),
            )
            upstream.append(reused.output_hash)
