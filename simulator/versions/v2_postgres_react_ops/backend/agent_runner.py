from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.graph import (
    AgentGraphContext,
    SimulateCard,
    execute_reserved_agent_graph,
    run_persistent_agent_graph,
)
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_rag.search import RagSearcher
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
    runtime = runtime or AgentRuntime(settings=Settings(), rag_searcher=RagSearcher())
    return await run_persistent_agent_graph(
        AgentGraphContext(
            engine=engine,
            runtime=runtime,
            legacy_simulate_card=simulate_card,
        ),
        request,
    )


async def run_reserved_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
) -> AgentRunResponse:
    runtime = runtime or AgentRuntime(settings=Settings(), rag_searcher=RagSearcher())
    return await execute_reserved_agent_graph(
        AgentGraphContext(
            engine=engine,
            runtime=runtime,
            legacy_simulate_card=simulate_card,
        ),
        request,
    )


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
