from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_stage_repository import (
    StageSnapshotDraft,
    StageSnapshotRecord,
    list_stage_snapshots,
    record_stage_snapshot,
)
from heatgrid_ops.agent.quality import ExecutionStatus, QualityStatus
from heatgrid_ops.agent.v2_models import StageName, StageSnapshotEnvelope
from heatgrid_ops.agent.v2_stage_contracts import StageSnapshotPort, StageSnapshotWrite


class PostgresStageSnapshotAdapter(StageSnapshotPort):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_attempt(
        self,
        run_id: str,
        stage_name: StageName,
        attempt: int,
    ) -> StageSnapshotWrite | None:
        records = await list_stage_snapshots(self._engine, run_id)
        for record in records:
            if record.stage_name == stage_name and _attempt(record) == attempt:
                return _to_write(record)
        return None

    async def record(self, request: StageSnapshotWrite) -> StageSnapshotWrite:
        record = await record_stage_snapshot(
            self._engine,
            StageSnapshotDraft(
                run_id=request.run_id,
                stage_name=request.stage_name,
                stage_kind="quality",
                execution_status=cast(ExecutionStatus, request.execution_status),
                quality_status=cast(QualityStatus | None, request.quality_status),
                score=request.score,
                run_input_hash=_run_input_hash(request),
                upstream_output_hashes=request.upstream_output_hashes,
                output_snapshot=request.envelope.data,
                contract_version=request.contract_version,
                component_versions=request.component_versions,
                feature_flags=request.feature_flags,
                thresholds=request.thresholds,
                attempt=request.attempt,
                state_schema_version=request.envelope.state_schema_version,
                envelope=request.envelope.model_dump(mode="json"),
                policy_version=request.policy_version,
                attempt_parameters=request.attempt_parameters,
            ),
        )
        return _to_write(record)


def _to_write(record: StageSnapshotRecord) -> StageSnapshotWrite:
    envelope = StageSnapshotEnvelope.model_validate(record.output_snapshot)
    return StageSnapshotWrite(
        run_id=record.run_id,
        stage_name=record.stage_name,
        attempt=_attempt(record),
        stage_input_hash=record.stage_input_hash,
        output_hash=record.output_hash,
        envelope=envelope,
        execution_status=record.execution_status,
        quality_status=record.quality_status,
        score=record.score,
        contract_version=record.contract_version,
        component_versions=record.component_versions,
        reused_from_snapshot_id=record.reused_from_snapshot_id,
    )


def _attempt(record: StageSnapshotRecord) -> int:
    return record.attempt


def _run_input_hash(request: StageSnapshotWrite) -> str:
    value = request.envelope.data.get("request")
    if not isinstance(value, dict):
        raise ValueError("stage snapshot request state is missing")
    input_hash = value.get("input_hash")
    if not isinstance(input_hash, str):
        raise ValueError("stage snapshot input hash is missing")
    return input_hash
