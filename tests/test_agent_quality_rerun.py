from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from heatgrid_ops.agent.lineage import source_output_hash, stage_input_hash
from heatgrid_ops.agent.models import OpsAgentOutput
from heatgrid_ops.agent.quality import ml_quality_result, rag_quality_result


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "008_agent_quality_rerun.sql"
BACKEND_DIR = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"


def test_v008_schema_contract_and_artifact_preflight_order() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    duplicate_check = sql.index("having count(*) > 1")
    old_index_drop = sql.index("drop index if exists public.agent_run_artifact_run_name_idx")
    lineage_columns = sql.index("add column if not exists source_output_hash")
    new_index = sql.index("nulls not distinct")

    assert duplicate_check < old_index_drop < lineage_columns < new_index
    assert "execution_status" in sql
    assert "quality_status" in sql
    assert "reused_from_snapshot_id" in sql
    assert "reused_from_snapshot_id <> stage_snapshot_id" in sql
    assert "check (lineage_depth between 0 and 2)" in sql
    assert "blocked_legacy_input_unavailable" in sql
    assert "agent_run_tasks_one_graph_per_run_uidx" in sql
    assert "where task_key in ('agent_graph:v1', 'agent_graph:v2')" in sql
    assert sql.count("owner to current_user") == 2


def test_source_output_hash_uses_only_effective_output_fields() -> None:
    output = OpsAgentOutput(
        summary="summary",
        action_plan="inspect",
        caution="verify",
    )

    assert source_output_hash(output) == source_output_hash(
        OpsAgentOutput(summary="summary", action_plan="inspect", caution="verify")
    )
    assert source_output_hash(output) != source_output_hash(
        OpsAgentOutput(summary="changed", action_plan="inspect", caution="verify")
    )


def test_stage_input_hash_includes_upstream_and_component_versions() -> None:
    baseline = stage_input_hash(
        run_input_hash="a" * 64,
        upstream_output_hashes=("b" * 64,),
        contract_version="ml_validation.v1",
        policy_version="agent_graph_v2.v1",
        component_versions={"model": "model-v1", "prompt": "prompt-v1"},
        feature_flags={"rag_quality": False},
        thresholds={"agreement": 0.75},
    )

    assert baseline != stage_input_hash(
        run_input_hash="a" * 64,
        upstream_output_hashes=("c" * 64,),
        contract_version="ml_validation.v1",
        policy_version="agent_graph_v2.v1",
        component_versions={"model": "model-v1", "prompt": "prompt-v1"},
        feature_flags={"rag_quality": False},
        thresholds={"agreement": 0.75},
    )
    assert baseline != stage_input_hash(
        run_input_hash="a" * 64,
        upstream_output_hashes=("b" * 64,),
        contract_version="ml_validation.v1",
        policy_version="agent_graph_v2.v1",
        component_versions={"model": "model-v2", "prompt": "prompt-v1"},
        feature_flags={"rag_quality": False},
        thresholds={"agreement": 0.75},
    )


def test_stage_input_hash_includes_stage_name_and_state_schema_version() -> None:
    retrieval = stage_input_hash(
        run_input_hash="a" * 64,
        upstream_output_hashes=("b" * 64,),
        contract_version="rag_retrieval.v2",
        policy_version="agent_graph_v2.v2",
        component_versions={"rag": "rag-v1"},
        feature_flags={"rag_quality": True},
        thresholds={"retrieval": 60},
        stage_name="rag_retrieval",
        state_schema_version="agent_v2_state.v1",
    )
    interpretation = stage_input_hash(
        run_input_hash="a" * 64,
        upstream_output_hashes=("b" * 64,),
        contract_version="rag_interpretation.v2",
        policy_version="agent_graph_v2.v2",
        component_versions={"rag": "rag-v1"},
        feature_flags={"rag_quality": True},
        thresholds={"retrieval": 60},
        stage_name="rag_interpretation",
        state_schema_version="agent_v2_state.v1",
    )

    assert retrieval != interpretation


@pytest.mark.parametrize(
    ("status", "agreement", "execution_status", "quality_status", "score"),
    [
        ("verified", True, "passed", "passed", 100.0),
        ("verified", None, "passed", "partial", 50.0),
        ("verified", False, "passed", "insufficient", 25.0),
        ("partial", True, "passed", "partial", 60.0),
        ("partial", None, "passed", "partial", 40.0),
        ("partial", False, "passed", "insufficient", 25.0),
        ("unavailable", None, "unavailable", "unavailable", None),
        ("error", None, "failed", "insufficient", 0.0),
    ],
)
def test_ml_quality_decision_table_is_complete(
    status: str,
    agreement: bool | None,
    execution_status: str,
    quality_status: str,
    score: float | None,
) -> None:
    result = ml_quality_result(status=status, agreement=agreement)

    assert result.execution_status == execution_status
    assert result.quality_status == quality_status
    assert result.score == score


def test_rag_quality_off_records_execution_without_quality_score() -> None:
    result = rag_quality_result(result_count=3, quality_enabled=False)

    assert result.execution_status == "passed"
    assert result.quality_status == "skipped"
    assert result.score is None


def test_targeted_rerun_policy_blocks_unsafe_child_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    policy = importlib.import_module("agent_rerun_policy")

    assert (
        policy.rerun_block_status(
            target_stage="fault_analysis",
            lineage_depth=2,
            input_status="available",
            rag_quality_enabled=True,
        )
        == "rerun_limit_reached"
    )
    assert (
        policy.rerun_block_status(
            target_stage="fault_analysis",
            lineage_depth=0,
            input_status="unavailable",
            rag_quality_enabled=True,
        )
        == "blocked_legacy_input_unavailable"
    )
    assert (
        policy.rerun_block_status(
            target_stage="rag_retrieval",
            lineage_depth=0,
            input_status="available",
            rag_quality_enabled=False,
        )
        == "blocked_integration_disabled"
    )
