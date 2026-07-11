from __future__ import annotations

import asyncio
import logging

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
    SimulateCard,
    execute_reserved_agent_graph,
    run_persistent_agent_graph,
)
from heatgrid_ops.agent.review_models import AgentRunReviewCaptureSource
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.v2_models import STAGE_ORDER, StageName
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
