from __future__ import annotations

import pytest

from heatgrid_ops.agent.v2_models import (
    STATE_SCHEMA_VERSION,
    STAGE_ORDER,
    StageControlEnvelope,
    StageSnapshotEnvelope,
)
from heatgrid_ops.agent.graph_v2 import AgentV2GraphContext, V2GraphInput, build_agent_v2_graph
from heatgrid_ops.agent.v2_policy import v2_stage_input_hash
from heatgrid_ops.agent.v2_stage_contracts import StageSnapshotWrite
from heatgrid_ops.agent.v2_stage_runner import (
    StageExecutionRequest,
    StageRunner,
    StageSchemaMismatch,
)
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState


class MemoryStageSnapshots:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, int], StageSnapshotWrite] = {}

    async def get_attempt(
        self,
        run_id: str,
        stage_name: object,
        attempt: int,
    ) -> StageSnapshotWrite | None:
        if not isinstance(stage_name, str):
            raise TypeError("stage name must be a string")
        return self.items.get((run_id, stage_name, attempt))

    async def record(self, request: StageSnapshotWrite) -> StageSnapshotWrite:
        key = (request.run_id, request.stage_name, request.attempt)
        self.items[key] = request
        return request


def _state() -> AgentV2State:
    return AgentV2State(
        request=V2RequestState(
            run_id="run-1",
            alert_id="alert-1",
            card_id="card-1",
            input_hash="a" * 64,
            source_input={
                "card_id": "card-1",
                "sections": {},
                "priority_context": {},
                "raw_context": {},
            },
        )
    )


def test_v2_snapshot_contains_state_schema_and_stage_name() -> None:
    envelope = StageSnapshotEnvelope(
        stage_name="rag_retrieval",
        data=_state().model_dump(mode="json"),
    )

    assert envelope.schema_version == "agent_stage_snapshot.v2"
    assert envelope.state_schema_version == STATE_SCHEMA_VERSION
    assert envelope.stage_name == "rag_retrieval"
    assert envelope.data["state_schema_version"] == STATE_SCHEMA_VERSION


def test_v2_hash_changes_when_stage_name_changes() -> None:
    common = {
        "run_input_hash": "a" * 64,
        "upstream_output_hashes": ("b" * 64,),
        "component_versions": {"rag": "rag-v1"},
        "feature_flags": {"rag_quality": True},
        "thresholds": {"retrieval": 60},
    }

    assert v2_stage_input_hash(stage_name="rag_retrieval", **common) != v2_stage_input_hash(
        stage_name="rag_interpretation", **common
    )


@pytest.mark.anyio
async def test_stage_runner_replays_committed_snapshot_without_adapter_call() -> None:
    snapshots = MemoryStageSnapshots()
    runner = StageRunner(snapshots)
    state = _state()
    request = StageExecutionRequest(
        run_id="run-1",
        state=state,
        stage_name="rag_retrieval",
        attempt=1,
        upstream_output_hashes=(),
        component_versions={"rag": "rag-v1"},
        feature_flags={"rag_quality": True},
        thresholds={"retrieval": 60},
    )
    calls = 0

    async def adapter(_: AgentV2State) -> StageSnapshotEnvelope:
        nonlocal calls
        calls += 1
        return StageSnapshotEnvelope(
            stage_name="rag_retrieval",
            data=state.model_dump(mode="json"),
        )

    await runner.execute(request, adapter)
    await runner.execute(request, adapter)

    assert calls == 1


@pytest.mark.anyio
async def test_stage_runner_rejects_state_schema_mismatch_before_reuse() -> None:
    snapshots = MemoryStageSnapshots()
    runner = StageRunner(snapshots)
    state = _state()
    request = StageExecutionRequest(
        run_id="run-1",
        state=state,
        stage_name="ml_validation",
        attempt=1,
        upstream_output_hashes=(),
        component_versions={},
        feature_flags={},
        thresholds={},
    )
    envelope = StageSnapshotEnvelope(
        stage_name="ml_validation",
        state_schema_version="agent_v2_state.v0",
        data=state.model_dump(mode="json"),
    )
    stage_input_hash = v2_stage_input_hash(
        run_input_hash=state.request.input_hash,
        stage_name="ml_validation",
        upstream_output_hashes=(),
        component_versions={},
        feature_flags={},
        thresholds={},
    )
    await snapshots.record(
        StageSnapshotWrite(
            run_id="run-1",
            stage_name="ml_validation",
            attempt=1,
            stage_input_hash=stage_input_hash,
            output_hash="output",
            envelope=envelope,
            execution_status="passed",
            quality_status="passed",
            score=100.0,
            contract_version="ml_validation.v2",
            component_versions={},
        )
    )

    async def adapter(_: AgentV2State) -> StageSnapshotEnvelope:
        return StageSnapshotEnvelope(stage_name="ml_validation", data={})

    with pytest.raises(StageSchemaMismatch):
        await runner.execute(request, adapter)


@pytest.mark.anyio
async def test_rag_evaluator_unavailable_keeps_retrieval_execution_passed() -> None:
    snapshots = MemoryStageSnapshots()
    runner = StageRunner(snapshots)
    state = _state()
    request = StageExecutionRequest(
        run_id="run-1",
        state=state,
        stage_name="rag_retrieval",
        attempt=1,
        upstream_output_hashes=(),
        component_versions={},
        feature_flags={"rag_quality": True},
        thresholds={},
    )

    async def adapter(_: AgentV2State) -> StageSnapshotEnvelope:
        value = state.model_dump(mode="json")
        value["rag"] = {
            "retrieval": {"results": [{"id": "e1"}]},
            "execution_status": "passed",
            "quality_status": "unavailable",
            "score": None,
        }
        return StageSnapshotEnvelope(
            stage_name="rag_retrieval",
            data=value,
            control=StageControlEnvelope(force_review=True),
        )

    await runner.execute(request, adapter)
    record = snapshots.items[("run-1", "rag_retrieval", 1)]
    assert record.execution_status == "passed"
    assert record.quality_status == "unavailable"
    assert record.score is None
    rag = record.envelope.data.get("rag")
    assert isinstance(rag, dict)
    assert rag.get("retrieval") == {"results": [{"id": "e1"}]}


@pytest.mark.anyio
async def test_explicit_graph_runs_all_nine_stages_and_restores_state_from_snapshot() -> None:
    snapshots = MemoryStageSnapshots()
    graph = build_agent_v2_graph(
        AgentV2GraphContext(
            snapshots=snapshots,
            adapters={},
            component_versions={"graph": "test"},
            feature_flags={"rag_quality": False},
            thresholds={"evidence": 70},
        )
    )
    state = _state()
    result = await graph.ainvoke(
        V2GraphInput(state=state, stage_hashes={}, completed_stages=()),
        {"configurable": {"thread_id": "run-1"}},
    )

    completed = result.get("completed_stages")
    hashes = result.get("stage_hashes")
    restored_state = result.get("state")
    assert completed == STAGE_ORDER
    assert hashes is not None
    assert set(hashes) == set(STAGE_ORDER)
    assert restored_state is not None
    snapshot = snapshots.items[("run-1", STAGE_ORDER[-1], 1)]
    restored = AgentV2State.model_validate(snapshot.envelope.data)
    assert restored == restored_state


@pytest.mark.anyio
async def test_explicit_graph_reuses_committed_snapshots_without_adapter_calls() -> None:
    snapshots = MemoryStageSnapshots()
    graph = build_agent_v2_graph(
        AgentV2GraphContext(
            snapshots=snapshots,
            adapters={},
            component_versions={"graph": "test"},
            feature_flags={},
            thresholds={},
        )
    )
    input_state = V2GraphInput(state=_state(), stage_hashes={}, completed_stages=())
    first = await graph.ainvoke(input_state, {"configurable": {"thread_id": "run-1"}})
    second = await graph.ainvoke(input_state, {"configurable": {"thread_id": "run-1"}})

    assert second.get("state") == first.get("state")
    assert len(snapshots.items) == len(STAGE_ORDER)
