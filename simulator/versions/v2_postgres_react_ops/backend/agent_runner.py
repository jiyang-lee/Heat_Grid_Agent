from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_run_repository import fail_agent_run, reserve_agent_run
from agent_runtime_factory import create_agent_graph_context, create_agent_runtime
from heatgrid_ops.agent.contracts import AgentRunRequest, SimulateCard
from heatgrid_ops.agent.errors import AgentCoreError
from heatgrid_ops.agent.graph import execute_agent_graph
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
) -> AgentRunResponse:
    queued, created = await reserve_agent_run(
        engine,
        run_id=request.run_id,
        alert_id=request.alert_id,
        card_id=request.card_id,
    )
    if not created:
        return queued
    return await run_reserved_agent_graph(engine, request, simulate_card, runtime)


async def run_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
) -> AgentRunResponse:
    active_runtime = runtime or create_agent_runtime(Settings(), engine)
    try:
        result = await execute_agent_graph(
            create_agent_graph_context(engine, active_runtime, simulate_card),
            request,
        )
    except HTTPException as exc:
        return await fail_agent_run(engine, request.run_id, str(exc.detail))
    except AgentCoreError as exc:
        return await fail_agent_run(engine, request.run_id, str(exc))
    except Exception as exc:
        return await fail_agent_run(engine, request.run_id, str(exc))
    return AgentRunResponse.model_validate(result.model_dump(mode="json"))


def schedule_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
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
