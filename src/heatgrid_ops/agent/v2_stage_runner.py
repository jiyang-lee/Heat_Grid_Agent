from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonValue
from heatgrid_ops.agent.v2_models import StageName, StageSnapshotEnvelope
from heatgrid_ops.agent.v2_policy import v2_stage_input_hash
from heatgrid_ops.agent.v2_state import AgentV2State
from heatgrid_ops.agent.v2_stage_contracts import (
    StageSnapshotPort,
    StageSnapshotWrite,
    stage_contract_version,
)


@dataclass(frozen=True, slots=True)
class StageExecutionRequest:
    run_id: str
    state: AgentV2State
    stage_name: StageName
    attempt: int
    upstream_output_hashes: tuple[str, ...]
    component_versions: Mapping[str, JsonValue]
    feature_flags: Mapping[str, JsonValue]
    thresholds: Mapping[str, JsonValue]
    attempt_parameters: Mapping[str, JsonValue] | None = None


class StageReplayConflict(RuntimeError):
    pass


class StageSchemaMismatch(RuntimeError):
    pass


class StageRunner:
    def __init__(self, snapshots: StageSnapshotPort) -> None:
        self._snapshots = snapshots

    async def execute(
        self,
        request: StageExecutionRequest,
        adapter: Callable[[AgentV2State], Awaitable[StageSnapshotEnvelope]],
    ) -> StageSnapshotEnvelope:
        stage_input = v2_stage_input_hash(
            run_input_hash=request.state.request.input_hash,
            stage_name=request.stage_name,
            upstream_output_hashes=request.upstream_output_hashes,
            component_versions=request.component_versions,
            feature_flags=request.feature_flags,
            thresholds=request.thresholds,
            attempt_parameters=request.attempt_parameters,
        )
        existing = await self._snapshots.get_attempt(
            request.run_id,
            request.stage_name,
            request.attempt,
        )
        if existing is not None:
            if existing.envelope.state_schema_version != request.state.state_schema_version:
                raise StageSchemaMismatch(request.stage_name)
            if existing.stage_input_hash != stage_input:
                raise StageReplayConflict(request.stage_name)
            return existing.envelope

        envelope = await adapter(request.state)
        if envelope.stage_name != request.stage_name:
            raise ValueError("stage adapter returned the wrong stage")
        if envelope.state_schema_version != request.state.state_schema_version:
            raise StageSchemaMismatch(request.stage_name)
        record = StageSnapshotWrite(
            run_id=request.run_id,
            stage_name=request.stage_name,
            attempt=request.attempt,
            stage_input_hash=stage_input,
            output_hash=canonical_json_hash(envelope.data),
            envelope=envelope,
            execution_status="passed",
            quality_status="passed",
            score=None,
            contract_version=stage_contract_version(request.stage_name),
            component_versions=dict(request.component_versions),
        )
        return (await self._snapshots.record(record)).envelope
