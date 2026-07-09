from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.graph import (
    AgentGraphContext,
    SimulateCard,
    run_persistent_agent_graph,
)
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_rag.search import RagSearcher
from schemas import AgentRunResponse
from settings import Settings


async def run_agent_graph(
    engine: AsyncEngine,
    request: AgentRunRequest,
    simulate_card: SimulateCard | None = None,
) -> AgentRunResponse:
    runtime = AgentRuntime(settings=Settings(), rag_searcher=RagSearcher())
    return await run_persistent_agent_graph(
        AgentGraphContext(
            engine=engine,
            runtime=runtime,
            legacy_simulate_card=simulate_card,
        ),
        request,
    )
