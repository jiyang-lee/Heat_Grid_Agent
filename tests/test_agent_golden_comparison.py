from __future__ import annotations

from pathlib import Path

import orjson

from heatgrid_ops.agent.models import OpsAgentOutput
from heatgrid_ops.agent.run_models import AgentRunResult

FIXTURES = Path(__file__).parent / "fixtures"
ALLOWED_INTENTIONAL_CHANGES = {
    "web_search_removed",
    "diagnostic_worker_added",
    "durable_resume_added",
}


def test_golden_api_and_output_contracts_match_current_models() -> None:
    golden = _load("agent_foundation_golden_0f9afa9.json")

    assert set(golden["api_required_fields"]).issubset(AgentRunResult.model_fields)
    assert set(golden["output_required_fields"]) == set(OpsAgentOutput.model_fields)


def test_golden_comparison_has_only_documented_intentional_changes() -> None:
    golden = _load("agent_foundation_golden_0f9afa9.json")
    current = _load("agent_foundation_current.json")

    assert golden["api_required_fields"] == current["api_required_fields"]
    assert golden["output_required_fields"] == current["output_required_fields"]
    assert set(golden["scenarios"]) == set(current["scenarios"])
    for name, baseline in golden["scenarios"].items():
        result = current["scenarios"][name]
        assert baseline["terminal_status"] == result["terminal_status"]
        assert baseline["artifact_kinds"] == result["artifact_kinds"]
        changes = set(result.get("intentional_changes", []))
        behavior_changed = (
            baseline["decision_order"] != result["decision_order"]
            or baseline["loop_count"] != result["loop_count"]
        )
        if behavior_changed:
            assert changes
        assert changes.issubset(ALLOWED_INTENTIONAL_CHANGES)


def _load(name: str) -> dict:
    return orjson.loads((FIXTURES / name).read_bytes())
