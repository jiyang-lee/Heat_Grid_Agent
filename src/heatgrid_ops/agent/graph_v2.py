from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, Durability
from pydantic import TypeAdapter

from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.agent.v2_models import STAGE_ORDER, StageName, StageSnapshotEnvelope
from heatgrid_ops.agent.v2_stage_contracts import StageAdapter, StageSnapshotPort
from heatgrid_ops.agent.v2_stage_runner import StageExecutionRequest, StageRunner
from heatgrid_ops.agent.v2_policy import v2_stage_input_hash
from heatgrid_ops.agent.v2_state import AgentV2State


class V2GraphState(TypedDict, total=False):
    state: AgentV2State
    stage_hashes: dict[str, str]
    completed_stages: tuple[StageName, ...]
    start_stage: StageName


class V2GraphInput(TypedDict, total=False):
    state: AgentV2State
    stage_hashes: dict[str, str]
    completed_stages: tuple[StageName, ...]
    start_stage: StageName


@dataclass(frozen=True, slots=True)
class AgentV2GraphContext:
    snapshots: StageSnapshotPort
    adapters: Mapping[StageName, StageAdapter]
    component_versions: Mapping[str, JsonValue]
    feature_flags: Mapping[str, JsonValue]
    thresholds: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CompiledAgentV2Graph:
    compiled: CompiledStateGraph[V2GraphState, None, V2GraphInput, V2GraphState]
    max_iterations: int = 4

    @property
    def checkpointer_enabled(self) -> bool:
        return self.compiled.checkpointer is not None

    async def ainvoke(
        self,
        input: V2GraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None = None,
    ) -> V2GraphState:
        output = await self.compiled.ainvoke(input, config, durability=durability)
        return TypeAdapter(V2GraphState).validate_python(output)


def build_agent_v2_graph(
    context: AgentV2GraphContext,
    checkpointer: Checkpointer = None,
) -> CompiledAgentV2Graph:
    graph = StateGraph(V2GraphState, input_schema=V2GraphInput)
    runner = StageRunner(context.snapshots)
    for stage_name in STAGE_ORDER:
        graph.add_node(stage_name, partial(_run_stage, runner, context, stage_name))
    graph.add_conditional_edges(
        START,
        lambda state: state.get("start_stage", STAGE_ORDER[0]),
        {stage_name: stage_name for stage_name in STAGE_ORDER},
    )
    for previous, current in zip(STAGE_ORDER, STAGE_ORDER[1:]):
        graph.add_edge(previous, current)
    graph.add_edge(STAGE_ORDER[-1], END)
    return CompiledAgentV2Graph(
        compiled=graph.compile(checkpointer=checkpointer),
    )


async def _run_stage(
    runner: StageRunner,
    context: AgentV2GraphContext,
    stage_name: StageName,
    state: V2GraphState,
) -> V2GraphState:
    current = state.get("state")
    if current is None:
        raise RuntimeError("v2 graph state is missing")
    upstream_hashes = tuple(state.get("stage_hashes", {}).values())
    attempt = current.attempts.get(stage_name, 1)
    adapter = context.adapters.get(stage_name)
    if adapter is None:
        adapter = _default_adapter(stage_name)
    envelope = await runner.execute(
        StageExecutionRequest(
            run_id=current.request.run_id,
            state=current,
            stage_name=stage_name,
            attempt=attempt,
            upstream_output_hashes=upstream_hashes,
            component_versions=context.component_versions,
            feature_flags=context.feature_flags,
            thresholds=context.thresholds,
            attempt_parameters={"attempt": attempt},
        ),
        adapter,
    )
    restored = AgentV2State.model_validate(envelope.data)
    hashes = dict(state.get("stage_hashes", {}))
    hashes[stage_name] = canonical_json_hash(envelope.model_dump(mode="json"))
    completed = (*state.get("completed_stages", ()), stage_name)
    result: V2GraphState = {
        "state": restored,
        "stage_hashes": hashes,
        "completed_stages": completed,
        "start_stage": state.get("start_stage", STAGE_ORDER[0]),
    }
    return result


async def hydrate_v2_prefix(
    context: AgentV2GraphContext,
    state: AgentV2State,
) -> tuple[AgentV2State, dict[str, str], tuple[StageName, ...], StageName]:
    if state.request.target_stage is None:
        return state, {}, (), STAGE_ORDER[0]
    hashes: dict[str, str] = {}
    completed: list[StageName] = []
    current = state
    for stage_name in STAGE_ORDER:
        if stage_name == state.request.target_stage:
            break
        snapshot = await context.snapshots.get_attempt(
            state.request.run_id,
            stage_name,
            state.attempts.get(stage_name, 1),
        )
        if snapshot is None:
            break
        if snapshot.envelope.state_schema_version != state.state_schema_version:
            break
        if canonical_json_hash(snapshot.envelope.model_dump(mode="json")) != snapshot.output_hash:
            break
        expected_hash = v2_stage_input_hash(
            run_input_hash=state.request.input_hash,
            stage_name=stage_name,
            upstream_output_hashes=tuple(hashes.values()),
            component_versions=context.component_versions,
            feature_flags=context.feature_flags,
            thresholds=context.thresholds,
            attempt_parameters={"attempt": state.attempts.get(stage_name, 1)},
        )
        if snapshot.stage_input_hash != expected_hash:
            break
        if snapshot.component_versions != dict(context.component_versions):
            break
        try:
            current = AgentV2State.model_validate(snapshot.envelope.data)
        except ValueError:
            break
        hashes[stage_name] = snapshot.output_hash
        completed.append(stage_name)
    start_stage = (
        STAGE_ORDER[len(completed)]
        if len(completed) < len(STAGE_ORDER)
        else STAGE_ORDER[-1]
    )
    return current, hashes, tuple(completed), start_stage


def _default_adapter(stage_name: StageName) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        field = _stage_field(stage_name)
        value: JsonObject = {
            "execution_status": "passed",
            "quality_status": "passed",
            "score": 100.0,
        }
        current = state.model_dump(mode="json")
        if field != "routing":
            current[field] = value
        return StageSnapshotEnvelope(stage_name=stage_name, data=current)

    return execute


def _stage_field(stage_name: StageName) -> str:
    if stage_name == "ml_validation":
        return "ml"
    if stage_name == "weather_context":
        return "weather"
    if stage_name in {"rag_retrieval", "rag_interpretation"}:
        return "rag"
    if stage_name == "fault_analysis":
        return "fault"
    if stage_name == "higher_model_reassessment":
        return "escalation"
    if stage_name == "parent_disposition":
        return "routing"
    return "report"
