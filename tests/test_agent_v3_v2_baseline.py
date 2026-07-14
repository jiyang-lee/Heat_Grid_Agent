from __future__ import annotations

from pathlib import Path
from runpy import run_path
import subprocess
from typing import Final, get_args

import orjson
import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.types import Durability

from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.diagnostics import (
    DIAGNOSTIC_DEADLINE_SECONDS,
    DIAGNOSTIC_FIRST_ATTEMPT_SECONDS,
    DIAGNOSTIC_INPUT_TOKEN_LIMIT,
    DIAGNOSTIC_OUTPUT_TOKEN_LIMIT,
    DIAGNOSTIC_RETRY_SECONDS,
    DIAGNOSTIC_TOTAL_TOKEN_LIMIT,
    DiagnosticSummary,
    DiagnosticWorkerInput,
    DiagnosticWorkerOutput,
)
from heatgrid_ops.agent.graph import execute_agent_graph
from heatgrid_ops.agent.models import OpsAgentOutput
from heatgrid_ops.agent.run_models import AgentRunResult
from heatgrid_ops.agent.state import AgentGraphInput, AgentGraphOutput, ResultState
from v3_baseline_graph_harness import GraphReplay, GraphScenario, replay_graph


ROOT: Final = Path(__file__).resolve().parents[1]
FIXTURE: Final = ROOT / "tests" / "fixtures" / "agent_v3_v2_behavior_baseline.json"
BUDGET_REPOSITORY: Final = (
    ROOT
    / "simulator"
    / "versions"
    / "v2_postgres_react_ops"
    / "backend"
    / "agent_budget_repository.py"
)
EXECUTION_MIGRATION: Final = (
    ROOT / "docker" / "postgres" / "init" / "004_agent_execution.sql"
)
BASELINE = orjson.loads(FIXTURE.read_bytes())
BEHAVIOR_SHA: Final = "8ddc0b485dbe4a7ee9601066354280cc997101d6"
BRANCH_START_SHA: Final = "bb3fb32f6429f0ca84e162a88fa59109effc712b"


class RecordingGraph:
    def __init__(self) -> None:
        self.checkpointer_enabled = True
        self.max_iterations = 4
        self.inputs: list[AgentGraphInput | None] = []
        self.configs: list[RunnableConfig] = []
        self.durabilities: list[Durability | None] = []

    async def ainvoke(
        self,
        input: AgentGraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None,
    ) -> AgentGraphOutput:
        self.inputs.append(input)
        self.configs.append(config)
        self.durabilities.append(durability)
        return {
            "result": ResultState(
                value=AgentRunResult(
                    run_id="run-baseline",
                    status="completed",
                    input_source="alert",
                    alert_id="alert-baseline",
                    card_id="card-baseline",
                )
            )
        }


def test_v2_baseline_pins_behavior_and_branch_start_commits() -> None:
    assert BASELINE["provenance"] == {
        "behavior_sha": BEHAVIOR_SHA,
        "branch_start_sha": BRANCH_START_SHA,
    }
    behavior = _git("rev-parse", f"{BEHAVIOR_SHA}^{{commit}}")
    branch_start = _git("rev-parse", f"{BRANCH_START_SHA}^{{commit}}")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BEHAVIOR_SHA, BRANCH_START_SHA],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert behavior == BEHAVIOR_SHA
    assert branch_start == BRANCH_START_SHA
    assert ancestry.returncode == 0


@pytest.mark.anyio
async def test_normal_high_replays_full_graph_to_human_review() -> None:
    replay = await replay_graph(
        GraphScenario(
            priority_level="high",
            review_required=False,
            rag_chunk_count=2,
            agreement=True,
        )
    )

    _assert_replay("normal_high", replay)


@pytest.mark.anyio
async def test_urgent_model_mismatch_replays_full_graph_to_review() -> None:
    replay = await replay_graph(
        GraphScenario(
            priority_level="urgent",
            review_required=False,
            rag_chunk_count=2,
            agreement=False,
        )
    )

    _assert_replay("model_mismatch_urgent", replay)


@pytest.mark.anyio
async def test_review_required_insufficient_evidence_replays_full_graph() -> None:
    replay = await replay_graph(
        GraphScenario(
            priority_level="medium",
            review_required=True,
            rag_chunk_count=0,
            agreement=True,
        )
    )

    _assert_replay("review_required_insufficient_evidence", replay)


def test_current_run_response_matches_v2_baseline() -> None:
    contract = BASELINE["run_response_contract"]

    assert list(AgentRunResult.model_fields) == contract["fields"]
    assert list(OpsAgentOutput.model_fields) == contract["ops_output_fields"]
    assert list(get_args(AgentRunResult.model_fields["status"].annotation)) == contract[
        "statuses"
    ]
    assert list(
        get_args(AgentRunResult.model_fields["review_status"].annotation)
    ) == contract["review_statuses"]
    assert get_args(AgentRunResult.model_fields["input_source"].annotation) == (
        contract["input_source"],
    )
    assert AgentRunResult(
        run_id="run-1",
        status="queued",
        input_source="alert",
        alert_id="alert-1",
        card_id="card-1",
    ).model_dump()["review_status"] == "pending"


def test_diagnostic_limits_match_pr04_pr05_baseline() -> None:
    contract = BASELINE["diagnostic_contract"]

    assert DIAGNOSTIC_INPUT_TOKEN_LIMIT == contract["input_token_limit"]
    assert DIAGNOSTIC_OUTPUT_TOKEN_LIMIT == contract["output_token_limit"]
    assert DIAGNOSTIC_TOTAL_TOKEN_LIMIT == contract["total_token_limit"]
    assert DIAGNOSTIC_DEADLINE_SECONDS == contract["deadline_seconds"]
    assert DIAGNOSTIC_FIRST_ATTEMPT_SECONDS == contract["first_attempt_seconds"]
    assert DIAGNOSTIC_RETRY_SECONDS == contract["retry_seconds"]
    assert DiagnosticWorkerInput.model_fields["task_key"].default == contract["task_key"]
    assert DiagnosticWorkerOutput.model_json_schema()["properties"]["hypotheses"][
        "maxItems"
    ] == contract["max_hypotheses"]
    assert DiagnosticSummary.model_json_schema()["properties"]["attempts"][
        "maximum"
    ] == contract["max_attempts"]


def test_budget_contract_matches_pr03_pr05_baseline() -> None:
    budget = BASELINE["budget_contract"]
    repository = run_path(str(BUDGET_REPOSITORY))
    migration = EXECUTION_MIGRATION.read_text(encoding="utf-8").lower()

    assert repository["PARENT_TOKEN_LIMIT"] == budget["parent_token_limit"]
    assert repository["PARENT_RETRY_LIMIT"] == budget["parent_retry_limit"]
    assert repository["EXTERNAL_SEARCH_LIMIT"] == budget["external_search_limit"]
    assert "max_attempts integer not null default 3" in migration
    assert "unique (run_id, task_key)" in migration
    assert "operation_key text not null unique" in migration


@pytest.mark.anyio
async def test_checkpoint_contract_drives_initial_and_resume_invocations() -> None:
    graph = RecordingGraph()
    request = AgentRunRequest(
        run_id="run-baseline",
        alert_id="alert-baseline",
        card_id="card-baseline",
    )
    await execute_agent_graph(None, request, graph=graph)
    await execute_agent_graph(None, request, graph=graph, resume=True)

    assert graph.inputs[0] is not None
    assert graph.inputs[1] is None
    assert [config.get("configurable") for config in graph.configs] == [
        {"thread_id": "run-baseline"},
        {"thread_id": "run-baseline"},
    ]
    assert graph.durabilities == ["sync", "sync"]
    assert BASELINE["checkpoint_contract"] == {
        "thread_id": "run_id",
        "durability": "sync",
        "resume_input": None,
    }


def _assert_replay(name: str, replay: GraphReplay) -> None:
    expected = BASELINE["scenarios"][name]
    assert list(replay.decisions) == expected["decision_order"]
    assert replay.loop_count == expected["loop_count"]
    assert replay.terminal_status == expected["terminal_status"]


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
