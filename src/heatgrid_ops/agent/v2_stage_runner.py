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
        execution_status, quality_status, score = _stage_quality(
            envelope.data,
            request.stage_name,
        )
        record = StageSnapshotWrite(
            run_id=request.run_id,
            stage_name=request.stage_name,
            attempt=request.attempt,
            stage_input_hash=stage_input,
            output_hash=canonical_json_hash(envelope.model_dump(mode="json")),
            envelope=envelope,
            execution_status=execution_status,
            quality_status=quality_status,
            score=score,
            contract_version=stage_contract_version(request.stage_name),
            component_versions=dict(request.component_versions),
            feature_flags=dict(request.feature_flags),
            thresholds=dict(request.thresholds),
            attempt_parameters=dict(request.attempt_parameters or {}),
            upstream_output_hashes=request.upstream_output_hashes,
        )
        return (await self._snapshots.record(record)).envelope


def _stage_quality(
    data: Mapping[str, JsonValue],
    stage_name: StageName,
) -> tuple[str, str | None, float | None]:
    field = {
        "ml_validation": "ml",
        "weather_context": "weather",
        "rag_retrieval": "rag",
        "rag_interpretation": "rag",
        "fault_analysis": "fault",
        "higher_model_reassessment": "escalation",
        "parent_disposition": "routing",
        "report_draft": "report",
        "report_fidelity": "report",
    }[stage_name]
    value = data.get(field)
    if not isinstance(value, dict):
        return "passed", "passed", None
    execution = value.get("execution_status", "passed")
    quality = value.get("quality_status", "passed")
    score = value.get("score")
    return (
        execution if isinstance(execution, str) else "passed",
        quality if isinstance(quality, str) else "passed",
        score if isinstance(score, float | int) else None,
    )
