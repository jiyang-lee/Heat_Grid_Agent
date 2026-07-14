from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from langgraph.types import Durability
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_stage_repository import (
    STAGE_ORDER,
    StageName,
    StageSnapshotDraft,
    insert_stage_snapshot,
    list_stage_snapshots,
    resolve_original_stage_snapshot,
)
from agent_stage_projection import project_stage_result
from heatgrid_ops.agent.graph import AgentGraphInvoker
from heatgrid_ops.agent.lineage import canonical_json_hash, stage_input_hash
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.state import AgentGraphInput, AgentGraphOutput, ResultState


@dataclass(frozen=True, slots=True)
class StagedAgentGraph:
    base: AgentGraphInvoker
    engine: AsyncEngine
    component_versions: JsonObject
    feature_flags: JsonObject
    thresholds: JsonObject

    @property
    def checkpointer_enabled(self) -> bool:
        return self.base.checkpointer_enabled

    @property
    def max_iterations(self) -> int:
        return self.base.max_iterations

    async def ainvoke(
        self,
        input: AgentGraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None,
    ) -> AgentGraphOutput:
        run_id = _run_id(input, config)
        await _reuse_parent_stages(
            self.engine,
            run_id=run_id,
            component_versions=self.component_versions,
            feature_flags=self.feature_flags,
            thresholds=self.thresholds,
        )
        output = await self.base.ainvoke(input, config, durability=durability)
        await _record_completed_stages(
            self.engine,
            run_id=run_id,
            result=ResultState.model_validate(output["result"]),
            component_versions=self.component_versions,
            feature_flags=self.feature_flags,
            thresholds=self.thresholds,
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
) -> AgentGraphInvoker:
    return StagedAgentGraph(
        base=base,
        engine=engine,
        component_versions={
            "graph": "agent_graph:v2",
            "policy": "agent_graph_v2.v1",
            "openai_model": openai_model,
            "prompt": "heatgrid_ops.v1",
            "adapter": "postgres.v008",
        },
        feature_flags={"rag_quality": rag_quality_enabled},
        thresholds={
            "evidence": evidence_threshold,
            "model_score_tolerance": model_score_tolerance,
        },
    )


async def _record_completed_stages(
    engine: AsyncEngine,
    *,
    run_id: str,
    result: ResultState,
    component_versions: JsonObject,
    feature_flags: JsonObject,
    thresholds: JsonObject,
) -> None:
    run_input_hash = await _run_input_hash(engine, run_id)
    existing = {item.stage_name: item for item in await list_stage_snapshots(engine, run_id)}
    upstream_hashes: list[str] = []
    async with engine.begin() as connection:
        for stage_name in STAGE_ORDER:
            prior = existing.get(stage_name)
            if prior is not None:
                upstream_hashes.append(prior.output_hash)
                continue
            draft = _stage_draft(
                run_id=run_id,
                stage_name=stage_name,
                result=result,
                run_input_hash=run_input_hash,
                upstream_output_hashes=tuple(upstream_hashes),
                component_versions=component_versions,
                feature_flags=feature_flags,
                thresholds=thresholds,
            )
            record = await insert_stage_snapshot(connection, draft)
            upstream_hashes.append(record.output_hash)


async def _reuse_parent_stages(
    engine: AsyncEngine,
    *,
    run_id: str,
    component_versions: JsonObject,
    feature_flags: JsonObject,
    thresholds: JsonObject,
) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT parent_run_id, target_stage, input_hash FROM agent_runs "
                "WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        row = result.mappings().one_or_none()
        if row is None or row["parent_run_id"] is None or row["target_stage"] is None:
            return
        parent_result = await connection.execute(
            text("SELECT input_hash FROM agent_runs WHERE run_id = :run_id"),
            {"run_id": row["parent_run_id"]},
        )
        parent_input_hash = parent_result.scalar_one_or_none()
    run_input_hash = row["input_hash"]
    if run_input_hash is None or parent_input_hash != run_input_hash:
        return
    target_stage = str(row["target_stage"])
    target_index = STAGE_ORDER.index(target_stage)
    parent = {
        item.stage_name: item
        for item in await list_stage_snapshots(engine, str(row["parent_run_id"]))
    }
    upstream_hashes: list[str] = []
    async with engine.begin() as connection:
        for stage_name in STAGE_ORDER[:target_index]:
            source = parent.get(stage_name)
            if source is None or source.execution_status not in {"passed", "reused"}:
                return
            contract_version = _contract_version(stage_name)
            expected_input_hash = stage_input_hash(
                run_input_hash=str(run_input_hash),
                upstream_output_hashes=upstream_hashes,
                contract_version=contract_version,
                policy_version="agent_graph_v2.v1",
                component_versions=component_versions,
                feature_flags=feature_flags,
                thresholds=thresholds,
            )
            if source.contract_version != contract_version:
                return
            if source.stage_input_hash != expected_input_hash:
                return
            if canonical_json_hash(source.output_snapshot) != source.output_hash:
                return
            if source.component_versions != component_versions:
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
                    run_id=run_id,
                    stage_name=stage_name,
                    stage_kind=source.stage_kind,
                    execution_status="reused",
                    quality_status=source.quality_status,
                    score=source.score,
                    run_input_hash=str(run_input_hash),
                    upstream_output_hashes=tuple(upstream_hashes),
                    output_snapshot=source.output_snapshot,
                    contract_version=contract_version,
                    component_versions=component_versions,
                    feature_flags=feature_flags,
                    thresholds=thresholds,
                    reused_from_snapshot_id=original.stage_snapshot_id,
                ),
            )
            upstream_hashes.append(reused.output_hash)


def _stage_draft(
    *,
    run_id: str,
    stage_name: StageName,
    result: ResultState,
    run_input_hash: str,
    upstream_output_hashes: tuple[str, ...],
    component_versions: JsonObject,
    feature_flags: JsonObject,
    thresholds: JsonObject,
) -> StageSnapshotDraft:
    stage_kind, quality, output = project_stage_result(stage_name, result, feature_flags)
    return StageSnapshotDraft(
        run_id=run_id,
        stage_name=stage_name,
        stage_kind=stage_kind,
        execution_status=quality.execution_status,
        quality_status=quality.quality_status,
        score=quality.score,
        run_input_hash=run_input_hash,
        upstream_output_hashes=upstream_output_hashes,
        output_snapshot=output,
        contract_version=_contract_version(stage_name),
        component_versions=component_versions,
        feature_flags=feature_flags,
        thresholds=thresholds,
    )


async def _run_input_hash(engine: AsyncEngine, run_id: str) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT input_hash FROM agent_runs WHERE run_id = :run_id "
                "AND input_snapshot_status = 'available'"
            ),
            {"run_id": run_id},
        )
    input_hash = result.scalar_one_or_none()
    if input_hash is None:
        raise RuntimeError("agent input hash is unavailable")
    return str(input_hash)


def _contract_version(stage_name: StageName) -> str:
    return f"{stage_name}.v1"


def _run_id(input: AgentGraphInput | None, config: RunnableConfig) -> str:
    if input is not None:
        return input["request"].run_id
    configurable = config.get("configurable") or {}
    run_id = configurable.get("thread_id")
    if not isinstance(run_id, str) or not run_id:
        raise RuntimeError("agent graph thread_id is unavailable")
    return run_id
