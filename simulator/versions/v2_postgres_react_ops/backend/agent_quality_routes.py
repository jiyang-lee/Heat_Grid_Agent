from __future__ import annotations

from datetime import datetime

import orjson
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_stage_repository import STAGE_ORDER, StageSnapshotRecord, list_stage_snapshots


class FrozenQualityModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StageProjection(FrozenQualityModel):
    stage_snapshot_id: str
    stage_name: str
    attempt: int
    execution_status: str
    quality_status: str | None
    score: float | None
    threshold: float | None
    reasons: tuple[str, ...]
    retry_exhausted: bool
    force_review: bool
    contract_version: str
    reused_from_snapshot_id: str | None
    created_at: datetime


class StageProjectionResponse(FrozenQualityModel):
    run_id: str
    graph_contract_version: str
    items: tuple[StageProjection, ...]


class ModelCallProjection(FrozenQualityModel):
    model_call_id: str
    stage_name: str
    stage_attempt: int
    execution_profile: str
    status: str
    snapshot_bundle_hash: str | None
    allowed_tools: tuple[str, ...]
    actual_tool_calls: int
    actual_model_turns: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ToolCallProjection(FrozenQualityModel):
    tool_call_id: str
    model_call_id: str
    stage_name: str
    tool_name: str
    status: str
    call_sequence: int


class CostBreakdownProjection(FrozenQualityModel):
    run_id: str
    model_call_count: int
    tool_call_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class LineageRunProjection(FrozenQualityModel):
    run_id: str
    parent_run_id: str | None
    root_run_id: str | None
    lineage_depth: int
    status: str
    target_stage: str | None


class RerunRequestProjection(FrozenQualityModel):
    rerun_request_id: str
    source_run_id: str
    child_run_id: str | None
    target_stage: str
    status: str
    created_at: datetime


class LineageProjectionResponse(FrozenQualityModel):
    root_run_id: str
    current_run_id: str
    depth: int
    ancestors: tuple[LineageRunProjection, ...]
    children: tuple[LineageRunProjection, ...]
    requests: tuple[RerunRequestProjection, ...]


def make_agent_quality_router(engine: AsyncEngine) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get(
        "/agent-runs/{run_id}/stages",
        response_model=StageProjectionResponse,
    )
    async def stages(run_id: str) -> StageProjectionResponse:
        records = await list_stage_snapshots(engine, run_id)
        if not records and not await _run_exists(engine, run_id):
            raise HTTPException(status_code=404, detail="run_id was not found")
        ordered = sorted(
            records,
            key=lambda item: (STAGE_ORDER.index(item.stage_name), item.attempt),
        )
        return StageProjectionResponse(
            run_id=run_id,
            graph_contract_version="agent_graph_v2.v3",
            items=tuple(_stage_projection(item) for item in ordered),
        )

    @router.get(
        "/agent-runs/{run_id}/rerun-lineage",
        response_model=LineageProjectionResponse,
    )
    async def rerun_lineage(run_id: str) -> LineageProjectionResponse:
        current = await _run_projection(engine, run_id)
        if current is None:
            raise HTTPException(status_code=404, detail="run_id was not found")
        ancestors = await _ancestors(engine, current)
        children = await _children(engine, run_id)
        requests = await _rerun_requests(engine, run_id)
        root_id = current.root_run_id or current.run_id
        if ancestors:
            root_id = ancestors[0].run_id
        return LineageProjectionResponse(
            root_run_id=root_id,
            current_run_id=run_id,
            depth=current.lineage_depth,
            ancestors=tuple(ancestors),
            children=tuple(children),
            requests=tuple(requests),
        )

    @router.get(
        "/agent-runs/{run_id}/model-calls",
        response_model=tuple[ModelCallProjection, ...],
    )
    async def model_calls(run_id: str) -> tuple[ModelCallProjection, ...]:
        if not await _run_exists(engine, run_id):
            raise HTTPException(status_code=404, detail="run_id was not found")
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT model_call_id, stage_name, stage_attempt, execution_profile, "
                    "status, snapshot_bundle_hash, CAST(allowed_tools AS text) AS allowed_tools, "
                    "actual_tool_calls, actual_model_turns, input_tokens, output_tokens, total_tokens "
                    "FROM agent_model_calls WHERE run_id = :run_id "
                    "ORDER BY started_at, model_call_id"
                ),
                {"run_id": run_id},
            )
        return tuple(_model_call_projection(row) for row in result.mappings().all())

    @router.get(
        "/agent-runs/{run_id}/tool-calls",
        response_model=tuple[ToolCallProjection, ...],
    )
    async def tool_calls(run_id: str) -> tuple[ToolCallProjection, ...]:
        if not await _run_exists(engine, run_id):
            raise HTTPException(status_code=404, detail="run_id was not found")
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT tool_call_id, model_call_id, stage_name, tool_name, status, call_sequence "
                    "FROM agent_tool_calls WHERE run_id = :run_id "
                    "ORDER BY started_at, tool_call_id"
                ),
                {"run_id": run_id},
            )
        return tuple(_tool_call_projection(row) for row in result.mappings().all())

    @router.get(
        "/agent-runs/{run_id}/cost-breakdown",
        response_model=CostBreakdownProjection,
    )
    async def cost_breakdown(run_id: str) -> CostBreakdownProjection:
        if not await _run_exists(engine, run_id):
            raise HTTPException(status_code=404, detail="run_id was not found")
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT count(*) AS model_call_count, "
                    "coalesce(sum(actual_tool_calls), 0) AS tool_call_count, "
                    "coalesce(sum(input_tokens), 0) AS input_tokens, "
                    "coalesce(sum(output_tokens), 0) AS output_tokens, "
                    "coalesce(sum(total_tokens), 0) AS total_tokens "
                    "FROM agent_model_calls WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        row = result.mappings().one()
        return CostBreakdownProjection(run_id=run_id, **dict(row))

    return router


def _stage_projection(record: StageSnapshotRecord) -> StageProjection:
    envelope = record.output_snapshot
    quality = envelope.get("quality") if isinstance(envelope, dict) else {}
    control = envelope.get("control") if isinstance(envelope, dict) else {}
    reasons_value = quality.get("reasons", ()) if isinstance(quality, dict) else ()
    reasons = (
        tuple(item for item in reasons_value if isinstance(item, str))
        if isinstance(reasons_value, (list, tuple))
        else ()
    )
    threshold = quality.get("threshold") if isinstance(quality, dict) else None
    return StageProjection(
        stage_snapshot_id=record.stage_snapshot_id,
        stage_name=record.stage_name,
        attempt=record.attempt,
        execution_status=record.execution_status,
        quality_status=record.quality_status,
        score=record.score,
        threshold=threshold if isinstance(threshold, (float, int)) else None,
        reasons=reasons,
        retry_exhausted=bool(quality.get("retry_exhausted", False))
        if isinstance(quality, dict)
        else False,
        force_review=bool(control.get("force_review", False))
        if isinstance(control, dict)
        else False,
        contract_version=record.contract_version,
        reused_from_snapshot_id=record.reused_from_snapshot_id,
        created_at=record.created_at,
    )


def _model_call_projection(row: RowMapping) -> ModelCallProjection:
    allowed = orjson.loads(row["allowed_tools"])
    tools = tuple(value for value in allowed if isinstance(value, str))
    return ModelCallProjection(
        model_call_id=str(row["model_call_id"]),
        stage_name=str(row["stage_name"]),
        stage_attempt=int(row["stage_attempt"]),
        execution_profile=str(row["execution_profile"]),
        status=str(row["status"]),
        snapshot_bundle_hash=None
        if row["snapshot_bundle_hash"] is None
        else str(row["snapshot_bundle_hash"]),
        allowed_tools=tools,
        actual_tool_calls=int(row["actual_tool_calls"]),
        actual_model_turns=int(row["actual_model_turns"]),
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        total_tokens=int(row["total_tokens"]),
    )


def _tool_call_projection(row: RowMapping) -> ToolCallProjection:
    return ToolCallProjection(
        tool_call_id=str(row["tool_call_id"]),
        model_call_id=str(row["model_call_id"]),
        stage_name=str(row["stage_name"]),
        tool_name=str(row["tool_name"]),
        status=str(row["status"]),
        call_sequence=int(row["call_sequence"]),
    )


async def _run_exists(engine: AsyncEngine, run_id: str) -> bool:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT 1 FROM agent_runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
    return result.scalar_one_or_none() is not None


async def _run_projection(
    engine: AsyncEngine,
    run_id: str,
) -> LineageRunProjection | None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT run_id, parent_run_id, root_run_id, lineage_depth, status, "
                "target_stage FROM agent_runs WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        row = result.mappings().one_or_none()
    return None if row is None else _lineage_row(row)


async def _ancestors(
    engine: AsyncEngine,
    current: LineageRunProjection,
) -> list[LineageRunProjection]:
    result: list[LineageRunProjection] = []
    seen = {current.run_id}
    parent_id = current.parent_run_id
    while parent_id is not None:
        if parent_id in seen or len(result) >= 2:
            raise HTTPException(status_code=409, detail="rerun lineage is invalid")
        seen.add(parent_id)
        parent = await _run_projection(engine, parent_id)
        if parent is None:
            raise HTTPException(status_code=409, detail="rerun lineage is incomplete")
        result.append(parent)
        parent_id = parent.parent_run_id
    result.reverse()
    return result


async def _children(engine: AsyncEngine, run_id: str) -> list[LineageRunProjection]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT run_id, parent_run_id, root_run_id, lineage_depth, status, "
                "target_stage FROM agent_runs WHERE parent_run_id = :run_id "
                "ORDER BY created_at, run_id"
            ),
            {"run_id": run_id},
        )
    return [_lineage_row(row) for row in result.mappings().all()]


async def _rerun_requests(
    engine: AsyncEngine,
    run_id: str,
) -> list[RerunRequestProjection]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT rerun_request_id, source_run_id, child_run_id, target_stage, "
                "status, created_at FROM agent_rerun_requests "
                "WHERE source_run_id = :run_id OR child_run_id = :run_id "
                "ORDER BY created_at, rerun_request_id"
            ),
            {"run_id": run_id},
        )
    return [
        RerunRequestProjection(
            rerun_request_id=str(row["rerun_request_id"]),
            source_run_id=str(row["source_run_id"]),
            child_run_id=None if row["child_run_id"] is None else str(row["child_run_id"]),
            target_stage=str(row["target_stage"]),
            status=str(row["status"]),
            created_at=row["created_at"],
        )
        for row in result.mappings().all()
    ]


def _lineage_row(mapping: RowMapping) -> LineageRunProjection:
    return LineageRunProjection(
        run_id=str(mapping["run_id"]),
        parent_run_id=None if mapping["parent_run_id"] is None else str(mapping["parent_run_id"]),
        root_run_id=None if mapping["root_run_id"] is None else str(mapping["root_run_id"]),
        lineage_depth=int(mapping["lineage_depth"]),
        status=str(mapping["status"]),
        target_stage=None if mapping["target_stage"] is None else str(mapping["target_stage"]),
    )
