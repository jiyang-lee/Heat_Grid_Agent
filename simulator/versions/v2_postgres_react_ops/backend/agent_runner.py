from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_execution_repository import (
    claim_agent_graph_task,
    complete_agent_graph_task,
    list_reclaimable_agent_runs,
    release_agent_graph_task,
)
from agent_run_repository import fail_agent_run, get_agent_run, reserve_agent_run
from agent_runtime_factory import create_agent_graph_context, create_agent_runtime
from heatgrid_ops.agent.contracts import AgentRunRequest, SimulateCard
from heatgrid_ops.agent.errors import AgentCoreError
from heatgrid_ops.agent.graph import AgentGraphInvoker, execute_agent_graph
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.services import AgentRuntime
from schemas import AgentRunResponse
from settings import Settings


logger = logging.getLogger(__name__)

_BACKGROUND_AGENT_TASKS: dict[str, asyncio.Task[AgentRunResponse]] = {}


async def run_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
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
    )


async def run_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
) -> AgentRunResponse:
    active_runtime = runtime or create_agent_runtime(Settings(), engine)
    context = create_agent_graph_context(engine, active_runtime, simulate_card)
    while True:
        claim = await claim_agent_graph_task(
            engine,
            run_id=request.run_id,
            input_snapshot=_request_snapshot(request),
        )
        if not claim.claimed or claim.lease_owner is None:
            existing = await get_agent_run(engine, request.run_id)
            if existing is None:
                raise RuntimeError("reserved agent run no longer exists")
            return existing
        try:
            result = await execute_agent_graph(
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
            usage = result.token_usage
            await complete_agent_graph_task(
                engine,
                run_id=request.run_id,
                lease_owner=claim.lease_owner,
                output_snapshot=_result_snapshot(result.status),
                tokens_used=0 if usage is None else usage.total_tokens,
            )
            return AgentRunResponse.model_validate(result.model_dump(mode="json"))
        retryable = await release_agent_graph_task(
            engine,
            run_id=request.run_id,
            lease_owner=claim.lease_owner,
            error=error,
        )
        if not retryable:
            return await fail_agent_run(engine, request.run_id, error)


def schedule_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph: AgentGraphInvoker | None = None,
) -> asyncio.Task[AgentRunResponse]:
    existing = _BACKGROUND_AGENT_TASKS.get(request.run_id)
    if existing is not None and not existing.done():
        return existing
    task = asyncio.create_task(
        run_reserved_agent_graph(
            engine,
            request,
            simulate_card,
            runtime,
            graph,
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


async def resume_reclaimable_agent_runs(
    engine: AsyncEngine,
    *,
    runtime: AgentRuntime,
    graph: AgentGraphInvoker,
) -> int:
    runs = await list_reclaimable_agent_runs(engine)
    for run in runs:
        schedule_reserved_agent_graph(
            engine,
            AgentRunRequest(
                run_id=run.run_id,
                alert_id=run.alert_id,
                card_id=run.card_id,
            ),
            runtime=runtime,
            graph=graph,
        )
    return len(runs)


def is_agent_run_scheduled(run_id: str) -> bool:
    task = _BACKGROUND_AGENT_TASKS.get(run_id)
    return task is not None and not task.done()


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


def _result_snapshot(status: str) -> JsonObject:
    return {"status": status}
