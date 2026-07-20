from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_execution_repository import (
    AGENT_GRAPH_TASK_KEY_V1,
    AGENT_GRAPH_TASK_KEY_V2,
    claim_agent_graph_task,
    complete_agent_graph_task,
    list_reclaimable_agent_runs,
    release_agent_graph_task,
)
from agent_rerun_repository import mark_child_rescheduled
from agent_rerun_policy import broaden_for_reason
from agent_input_snapshot_repository import (
    AgentInputLineage,
    get_agent_input_lineage,
    persist_native_agent_input,
)
from agent_review_snapshot_adapter import PostgresReviewSnapshotAdapter
from agent_review_snapshot_lineage import (
    assemble_review_snapshot,
    load_review_snapshot_lineage,
)
from agent_run_repository import fail_agent_run, get_agent_run, reserve_agent_run
from agent_runtime_factory import create_agent_graph_context, create_agent_runtime
from heatgrid_ops.agent.contracts import (
    AgentInputSnapshot,
    AgentRunRequest,
    SimulateCard,
    validate_agent_input,
)
from heatgrid_ops.agent.errors import AgentCoreError
from heatgrid_ops.agent.graph import (
    AgentGraphContext,
    AgentGraphInvoker,
    execute_agent_graph_with_capture,
    execute_agent_graph_v2_with_capture,
)
from heatgrid_ops.agent.review_models import AgentRunReviewCaptureSource
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.v2_models import STAGE_ORDER, StageName
from heatgrid_ops.agent.services import AgentRuntime
from schemas import AgentRunResponse
from settings import Settings


logger = logging.getLogger(__name__)

_BACKGROUND_AGENT_TASKS: dict[str, asyncio.Task[AgentRunResponse]] = {}
# 분석 요청은 모두 DB에 queued 상태로 먼저 저장된다. 한 프로세스가 동시에 실행하는
# 그래프 수만 제한해, 초과 요청은 상태를 유지한 채 FIFO 대기열에서 기다리게 한다.
MAX_CONCURRENT_AGENT_RUNS = 2
_AGENT_RUN_SLOTS = asyncio.Semaphore(MAX_CONCURRENT_AGENT_RUNS)


@dataclass(frozen=True, slots=True)
class PreparedTaskInput:
    snapshot: JsonObject
    schema_version: str | None
    input_hash: str | None
    origin: str
    status: str


@dataclass(frozen=True, slots=True)
class V2RunOptions:
    target_stage: StageName | None
    broaden: bool
    revision_feedback: tuple[str, ...]


async def run_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
    *,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
) -> AgentRunResponse:
    queued, created = await reserve_agent_run(
        engine,
        run_id=request.run_id,
        alert_id=request.alert_id,
        card_id=request.card_id,
    )
    if not created:
        return queued
    return await run_reserved_agent_graph(
        engine,
        request,
        simulate_card,
        runtime,
        graph,
        task_key=task_key,
    )


async def run_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
    *,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
) -> AgentRunResponse:
    active_runtime = runtime or create_agent_runtime(Settings(), engine)
    context = create_agent_graph_context(engine, active_runtime, simulate_card)
    prepared_input = await _prepare_task_input(context, engine, request, task_key)
    while True:
        claim = await claim_agent_graph_task(
            engine,
            run_id=request.run_id,
            input_snapshot=prepared_input.snapshot,
            task_key=task_key,
            input_schema_version=prepared_input.schema_version,
            input_hash=prepared_input.input_hash,
            input_snapshot_origin=prepared_input.origin,
            input_snapshot_status=prepared_input.status,
        )
        if not claim.claimed or claim.lease_owner is None:
            existing = await get_agent_run(engine, request.run_id)
            if existing is None:
                raise RuntimeError("reserved agent run no longer exists")
            return existing
        try:
            if task_key == AGENT_GRAPH_TASK_KEY_V2:
                options = await _v2_run_options(engine, request.run_id)
                execution = await execute_agent_graph_v2_with_capture(
                    context,
                    request,
                    AgentInputSnapshot(source_input=prepared_input.snapshot),
                    graph=graph,
                    resume=claim.resume_from_checkpoint,
                    target_stage=options.target_stage,
                    broaden=options.broaden,
                    revision_feedback=options.revision_feedback,
                )
            else:
                execution = await execute_agent_graph_with_capture(
                    context,
                    request,
                    graph=graph,
                    resume=claim.resume_from_checkpoint,
                )
        except HTTPException as exc:
            error = str(exc.detail)
        except AgentCoreError as exc:
            error = str(exc)
        except Exception as exc:
            error = str(exc)
        else:
            result = execution.result
            usage = result.token_usage
            marker_recorded = True
            if execution.review_capture_source is not None:
                marker_recorded = await _record_review_snapshot_pending(
                    engine,
                    execution.review_capture_source.run_id
                )
            elif execution.review_capture_failure is not None:
                marker_recorded = await _record_review_capture_build_failure(
                    engine,
                    request.run_id,
                    execution.review_capture_failure.error_type,
                )
            await complete_agent_graph_task(
                engine,
                run_id=request.run_id,
                lease_owner=claim.lease_owner,
                output_snapshot=_result_snapshot(result.status),
                tokens_used=0 if usage is None else usage.total_tokens,
                task_key=task_key,
            )
            if execution.review_capture_source is not None:
                if not marker_recorded:
                    await _record_review_snapshot_pending(
                        engine,
                        execution.review_capture_source.run_id,
                    )
                await _capture_completed_review_snapshot(
                    engine,
                    execution.review_capture_source,
                )
            elif (
                execution.review_capture_failure is not None
                and not marker_recorded
            ):
                await _record_review_capture_build_failure(
                    engine,
                    request.run_id,
                    execution.review_capture_failure.error_type,
                )
            return AgentRunResponse.model_validate(result.model_dump(mode="json"))
        retryable = await release_agent_graph_task(
            engine,
            run_id=request.run_id,
            lease_owner=claim.lease_owner,
            error=error,
            task_key=task_key,
        )
        if not retryable:
            return await fail_agent_run(engine, request.run_id, error)


def schedule_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
    *,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
) -> asyncio.Task[AgentRunResponse]:
    existing = _BACKGROUND_AGENT_TASKS.get(request.run_id)
    if existing is not None and not existing.done():
        return existing
    task = asyncio.create_task(
        _run_queued_agent_graph(
            engine,
            request,
            simulate_card,
            runtime,
            graph,
            task_key=task_key,
        )
    )
    _BACKGROUND_AGENT_TASKS[request.run_id] = task
    task.add_done_callback(
        lambda completed, run_id=request.run_id: _finish_background_agent_task(
            run_id,
            completed,
        )
    )
    return task


async def _run_queued_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
    *,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
) -> AgentRunResponse:
    async with _AGENT_RUN_SLOTS:
        return await run_reserved_agent_graph(
            engine,
            request,
            simulate_card,
            runtime,
            graph,
            task_key=task_key,
        )


async def resume_reclaimable_agent_runs(
    engine: AsyncEngine,
    *,
    runtime: AgentRuntime,
    graph: AgentGraphInvoker,
    v2_graph: AgentGraphInvoker | None = None,
) -> int:
    runs = await list_reclaimable_agent_runs(engine)
    for run in runs:
        active_graph = v2_graph if run.task_key == AGENT_GRAPH_TASK_KEY_V2 else graph
        schedule_reserved_agent_graph(
            engine,
            AgentRunRequest(
                run_id=run.run_id,
                alert_id=run.alert_id,
                card_id=run.card_id,
            ),
            runtime=runtime,
            graph=active_graph or graph,
            task_key=run.task_key,
        )
        if run.task_key == AGENT_GRAPH_TASK_KEY_V2:
            await mark_child_rescheduled(engine, run.run_id)
    return len(runs)


def is_agent_run_scheduled(run_id: str) -> bool:
    task = _BACKGROUND_AGENT_TASKS.get(run_id)
    return task is not None and not task.done()


def cancel_scheduled_agent_graph(run_id: str) -> bool:
    task = _BACKGROUND_AGENT_TASKS.get(run_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def _finish_background_agent_task(
    run_id: str,
    task: asyncio.Task[AgentRunResponse],
) -> None:
    if _BACKGROUND_AGENT_TASKS.get(run_id) is task:
        _BACKGROUND_AGENT_TASKS.pop(run_id, None)
    if task.cancelled():
        logger.warning("background agent run cancelled: %s", run_id)
        return
    error = task.exception()
    if error is not None:
        logger.exception(
            "background agent run crashed: %s",
            run_id,
            exc_info=error,
        )


def _request_snapshot(request: AgentRunRequest) -> JsonObject:
    return {
        "run_id": request.run_id,
        "alert_id": request.alert_id,
        "card_id": request.card_id,
    }


async def _v2_run_options(engine: AsyncEngine, run_id: str) -> V2RunOptions:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT runs.target_stage, reviews.reason_category, CAST(reviews.correction AS text) AS correction "
                "FROM agent_runs runs "
                "LEFT JOIN agent_run_reviews reviews "
                "ON reviews.review_id = runs.source_review_id "
                "WHERE runs.run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    row = result.mappings().one_or_none()
    if row is None:
        return V2RunOptions(target_stage=None, broaden=False, revision_feedback=())
    value = row["target_stage"]
    target_stage = value if isinstance(value, str) and value in STAGE_ORDER else None
    import orjson
    correction = orjson.loads(row["correction"]) if isinstance(row["correction"], str) else {}
    feedback = tuple(value for key, value in correction.items() if key in {"instruction", "current_body", "target_area"} and isinstance(value, str)) if isinstance(correction, dict) else ()
    return V2RunOptions(
        target_stage=target_stage,
        broaden=broaden_for_reason(row["reason_category"]),
        revision_feedback=feedback,
    )


async def _prepare_task_input(
    context: AgentGraphContext,
    engine: AsyncEngine,
    request: AgentRunRequest,
    task_key: str,
) -> PreparedTaskInput:
    lineage = await get_agent_input_lineage(engine, request.run_id)
    if lineage is None:
        raise RuntimeError("reserved agent run no longer exists")
    if task_key == AGENT_GRAPH_TASK_KEY_V1:
        if lineage.status == "available":
            return _prepared_lineage(lineage)
        return PreparedTaskInput(
            snapshot=_request_snapshot(request),
            schema_version=None,
            input_hash=None,
            origin=lineage.origin,
            status="unavailable",
        )
    if lineage.status == "available":
        return _prepared_lineage(lineage)
    if lineage.origin == "legacy_v1":
        raise RuntimeError("blocked_legacy_input_unavailable")
    snapshot = await context.inputs.load(request)
    if snapshot is None:
        raise RuntimeError("agent input is unavailable")
    source_input = validate_agent_input(snapshot, request)
    return _prepared_lineage(
        await persist_native_agent_input(
            engine,
            run_id=request.run_id,
            source_input=source_input,
        )
    )


def _prepared_lineage(lineage: AgentInputLineage) -> PreparedTaskInput:
    if lineage.source_input is None:
        raise RuntimeError("available agent input snapshot is missing")
    return PreparedTaskInput(
        snapshot=lineage.source_input,
        schema_version=lineage.input_schema_version,
        input_hash=lineage.input_hash,
        origin=lineage.origin,
        status=lineage.status,
    )


def _result_snapshot(status: str) -> JsonObject:
    return {"status": status}


async def _capture_completed_review_snapshot(
    engine: AsyncEngine,
    source: AgentRunReviewCaptureSource,
) -> None:
    adapter = PostgresReviewSnapshotAdapter(engine)
    try:
        lineage = await load_review_snapshot_lineage(engine, source.run_id)
        await adapter.capture(assemble_review_snapshot(source, lineage))
    except Exception as exc:  # noqa: BLE001 - completion boundary isolates review capture
        reason = f"{type(exc).__name__}: review snapshot capture failed"[:1000]
        logger.warning("review snapshot unavailable for run %s", source.run_id)
        try:
            await adapter.mark_unavailable(source.run_id, reason)
        except Exception:  # noqa: BLE001 - run completion must remain durable
            logger.exception(
                "review snapshot unavailable event failed for run %s",
                source.run_id,
            )


async def _record_review_capture_build_failure(
    engine: AsyncEngine,
    run_id: str,
    error_type: str,
) -> bool:
    try:
        await PostgresReviewSnapshotAdapter(engine).mark_unavailable(
            run_id,
            f"{error_type}: review snapshot source unavailable",
        )
    except Exception:  # noqa: BLE001 - run completion must remain durable
        logger.warning(
            "review snapshot build failure event failed for run %s",
            run_id,
        )
        return False
    return True


async def _record_review_snapshot_pending(
    engine: AsyncEngine,
    run_id: str,
) -> bool:
    try:
        await PostgresReviewSnapshotAdapter(engine).mark_pending(run_id)
    except Exception:  # noqa: BLE001 - run completion must remain durable
        logger.warning(
            "review snapshot pending event failed for run %s",
            run_id,
        )
        return False
    return True
