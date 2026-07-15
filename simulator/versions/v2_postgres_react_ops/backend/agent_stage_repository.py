from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from heatgrid_ops.agent.lineage import canonical_json_hash, stage_input_hash
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.quality import ExecutionStatus, QualityStatus


StageName = Literal[
    "ml_validation",
    "weather_context",
    "rag_retrieval",
    "rag_interpretation",
    "fault_analysis",
    "higher_model_reassessment",
    "parent_disposition",
    "report_draft",
    "report_fidelity",
]
StageKind = Literal["quality", "orchestration"]
STAGE_ORDER: tuple[StageName, ...] = (
    "ml_validation",
    "weather_context",
    "rag_retrieval",
    "rag_interpretation",
    "fault_analysis",
    "higher_model_reassessment",
    "parent_disposition",
    "report_draft",
    "report_fidelity",
)


@dataclass(frozen=True, slots=True)
class StageSnapshotDraft:
    run_id: str
    stage_name: StageName
    stage_kind: StageKind
    execution_status: ExecutionStatus
    quality_status: QualityStatus | None
    score: float | None
    run_input_hash: str
    upstream_output_hashes: tuple[str, ...]
    output_snapshot: JsonObject
    contract_version: str
    component_versions: JsonObject
    feature_flags: JsonObject
    thresholds: JsonObject
    attempt: int = 1
    reused_from_snapshot_id: str | None = None
    state_schema_version: str = "agent_v2_state.v1"
    envelope: JsonObject | None = None
    policy_version: str = "agent_graph_v2.v1"
    attempt_parameters: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class StageSnapshotRecord:
    stage_snapshot_id: str
    run_id: str
    stage_name: StageName
    stage_kind: StageKind
    attempt: int
    execution_status: ExecutionStatus
    quality_status: QualityStatus | None
    score: float | None
    stage_input_hash: str
    output_snapshot: JsonObject
    output_hash: str
    contract_version: str
    component_versions: JsonObject
    reused_from_snapshot_id: str | None
    state_schema_version: str | None


async def record_stage_snapshot(
    engine: AsyncEngine,
    draft: StageSnapshotDraft,
) -> StageSnapshotRecord:
    async with engine.begin() as connection:
        return await insert_stage_snapshot(connection, draft)


async def insert_stage_snapshot(
    connection: AsyncConnection,
    draft: StageSnapshotDraft,
) -> StageSnapshotRecord:
    envelope = draft.envelope or {
        "schema_version": "agent_stage_snapshot.v2",
        "state_schema_version": draft.state_schema_version,
        "stage_name": draft.stage_name,
        "data": draft.output_snapshot,
        "quality": {
            "threshold": draft.thresholds.get("threshold"),
            "reasons": [],
            "retry_exhausted": False,
        },
        "control": {
            "force_review": draft.quality_status == "unavailable",
            "suggested_query": None,
            "broaden": False,
        },
    }
    output_hash = canonical_json_hash(envelope)
    if draft.reused_from_snapshot_id is not None:
        source = await resolve_original_stage_snapshot(
            connection,
            draft.reused_from_snapshot_id,
        )
        if source.output_hash != output_hash:
            raise ValueError("reused stage output hash mismatch")
    component_versions = dict(draft.component_versions)
    if draft.attempt_parameters:
        component_versions["attempt_parameters"] = dict(draft.attempt_parameters)
    input_hash = stage_input_hash(
        run_input_hash=draft.run_input_hash,
        upstream_output_hashes=draft.upstream_output_hashes,
        contract_version=draft.contract_version,
        policy_version=draft.policy_version,
        component_versions=component_versions,
        feature_flags=draft.feature_flags,
        thresholds=draft.thresholds,
        stage_name=draft.stage_name,
        state_schema_version=draft.state_schema_version,
    )
    result = await connection.execute(
        text(
            "INSERT INTO agent_stage_snapshots ("
            "stage_snapshot_id, run_id, stage_name, stage_kind, attempt, execution_status, "
            "quality_status, score, stage_input_hash, output_snapshot, output_hash, "
            "contract_version, component_versions, reused_from_snapshot_id"
            ") VALUES ("
            ":stage_snapshot_id, :run_id, :stage_name, :stage_kind, :attempt, "
            ":execution_status, :quality_status, :score, :stage_input_hash, "
            "CAST(:output_snapshot AS jsonb), :output_hash, :contract_version, "
            "CAST(:component_versions AS jsonb), :reused_from_snapshot_id"
            ") ON CONFLICT (run_id, stage_name, attempt) DO NOTHING RETURNING "
            + _columns()
        ),
        {
            "stage_snapshot_id": str(uuid4()),
            "run_id": draft.run_id,
            "stage_name": draft.stage_name,
            "stage_kind": draft.stage_kind,
            "attempt": draft.attempt,
            "execution_status": draft.execution_status,
            "quality_status": draft.quality_status,
            "score": draft.score,
            "stage_input_hash": input_hash,
            "output_snapshot": _json(envelope),
            "output_hash": output_hash,
            "contract_version": draft.contract_version,
            "component_versions": _json(draft.component_versions),
            "reused_from_snapshot_id": draft.reused_from_snapshot_id,
        },
    )
    row = result.mappings().one_or_none()
    if row is None:
        existing = await connection.execute(
            text(
                "SELECT " + _columns() + " FROM agent_stage_snapshots "
                "WHERE run_id = :run_id AND stage_name = :stage_name AND attempt = :attempt"
            ),
            {
                "run_id": draft.run_id,
                "stage_name": draft.stage_name,
                "attempt": draft.attempt,
            },
        )
        row = existing.mappings().one()
        if row["stage_input_hash"] != input_hash or row["output_hash"] != output_hash:
            raise ValueError("stage snapshot is immutable")
    return _record(row)


async def list_stage_snapshots(
    engine: AsyncEngine,
    run_id: str,
) -> tuple[StageSnapshotRecord, ...]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT " + _columns() + " FROM agent_stage_snapshots "
                "WHERE run_id = :run_id ORDER BY created_at, stage_name"
            ),
            {"run_id": run_id},
        )
    return tuple(_record(row) for row in result.mappings().all())


async def resolve_original_stage_snapshot(
    connection: AsyncConnection,
    snapshot_id: str,
) -> StageSnapshotRecord:
    visited: set[str] = set()
    current_id = snapshot_id
    while True:
        if current_id in visited:
            raise ValueError("stage snapshot reuse cycle detected")
        visited.add(current_id)
        result = await connection.execute(
            text(
                "SELECT " + _columns() + " FROM agent_stage_snapshots "
                "WHERE stage_snapshot_id = :stage_snapshot_id"
            ),
            {"stage_snapshot_id": current_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ValueError("reused stage snapshot was not found")
        record = _record(row)
        if record.reused_from_snapshot_id is None:
            return record
        current_id = record.reused_from_snapshot_id


def _columns() -> str:
    return (
        "stage_snapshot_id, run_id, stage_name, stage_kind, attempt, execution_status, "
        "quality_status, score, stage_input_hash, CAST(output_snapshot AS text) "
        "AS output_snapshot, output_hash, contract_version, "
        "CAST(component_versions AS text) AS component_versions, reused_from_snapshot_id"
    )


def _record(row: RowMapping) -> StageSnapshotRecord:
    return StageSnapshotRecord(
        stage_snapshot_id=str(row["stage_snapshot_id"]),
        run_id=str(row["run_id"]),
        stage_name=row["stage_name"],
        stage_kind=row["stage_kind"],
        attempt=int(row["attempt"]),
        execution_status=row["execution_status"],
        quality_status=row["quality_status"],
        score=row["score"],
        stage_input_hash=str(row["stage_input_hash"]),
        output_snapshot=orjson.loads(row["output_snapshot"]),
        output_hash=str(row["output_hash"]),
        contract_version=str(row["contract_version"]),
        component_versions=orjson.loads(row["component_versions"]),
        reused_from_snapshot_id=None
        if row["reused_from_snapshot_id"] is None
        else str(row["reused_from_snapshot_id"]),
        state_schema_version=orjson.loads(row["output_snapshot"]).get(
            "state_schema_version"
        ),
    )


def _json(value: JsonObject) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
