from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.types import Durability

from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.graph import execute_agent_graph
from heatgrid_ops.agent.run_models import AgentRunResult
from heatgrid_ops.agent.state import AgentGraphInput, AgentGraphOutput, ResultState


ROOT: Final = Path(__file__).resolve().parents[1]
MIGRATION: Final = ROOT / "migrations" / "004_agent_execution.sql"
BASE_AGENT_SCHEMA: Final = (
    ROOT / "migrations" / "002_agent_automation.sql"
)


class RecordingGraph:
    def __init__(self) -> None:
        self.checkpointer_enabled = True
        self.max_iterations = 4
        self.input: AgentGraphInput | None = None
        self.config: RunnableConfig = {}
        self.durability: Durability | None = None

    async def ainvoke(
        self,
        input: AgentGraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None,
    ) -> AgentGraphOutput:
        self.input = input
        self.config = config
        self.durability = durability
        return {
            "result": ResultState(
                value=AgentRunResult(
                    run_id="run-1",
                    status="completed",
                    input_source="alert",
                    alert_id="alert-1",
                    card_id="card-1",
                )
            )
        }


@pytest.mark.anyio
async def test_durable_graph_uses_run_id_and_sync_checkpointing() -> None:
    graph = RecordingGraph()
    result = await execute_agent_graph(
        None,
        AgentRunRequest(run_id="run-1", alert_id="alert-1", card_id="card-1"),
        graph=graph,
    )

    assert result.status == "completed"
    assert graph.config.get("configurable") == {"thread_id": "run-1"}
    assert graph.durability == "sync"
    assert graph.input is not None


@pytest.mark.anyio
async def test_durable_resume_invokes_graph_with_none() -> None:
    graph = RecordingGraph()
    await execute_agent_graph(
        None,
        AgentRunRequest(run_id="run-1", alert_id="alert-1", card_id="card-1"),
        graph=graph,
        resume=True,
    )

    assert graph.input is None


def test_agent_execution_migration_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists agent_run_tasks" in sql
    assert "unique (run_id, task_key)" in sql
    assert "unique (operation_key)" in sql
    assert "create table if not exists agent_budget_ledger" in sql
    assert "token_limit" in sql
    assert "tokens_used <= token_limit" in sql
    assert "external_search_limit" in sql
    assert "check (external_search_limit = 0)" in sql
    assert "on conflict (run_id, task_key) do nothing" in sql
    assert "agent_run_tasks_run_id_fkey" in sql
    assert "agent_budget_ledger_run_id_fkey" in sql


def test_clean_init_creates_agent_base_after_canonical_dependencies() -> None:
    sql = BASE_AGENT_SCHEMA.read_text(encoding="utf-8").lower()

    assert "create table if not exists public.ops_alert_queue" in sql
    assert "create table if not exists public.agent_runs" in sql
    assert sql.index("create table if not exists public.ops_alert_queue") < sql.index(
        "create table if not exists public.agent_runs"
    )
