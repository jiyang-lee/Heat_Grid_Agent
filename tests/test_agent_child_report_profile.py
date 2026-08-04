from __future__ import annotations

import sys
from pathlib import Path

import pytest

from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.models import OpsAgentOutput, TokenUsage
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState


ROOT = Path(__file__).resolve().parents[1]


class ReportRuntime:
    def __init__(self) -> None:
        self.config = AgentRuntimeConfig(
            openai_model="test-model",
            rag_top_k=5,
            agent_max_iterations=4,
            agent_evidence_threshold=0.75,
            model_score_tolerance=0.12,
            input_usd_per_1m=1.0,
            cached_input_usd_per_1m=0.1,
            output_usd_per_1m=1.0,
            pricing_source="test",
        )
        self.arguments: dict[str, object] = {}

    def token_usage_for(self, _source, _evidence, _card_id) -> TokenUsage:
        return TokenUsage()

    async def generate_llm_output(self, *_args, **kwargs) -> OpsAgentOutput:
        self.arguments = kwargs
        return OpsAgentOutput(
            summary="snapshot report",
            action_plan="review the evidence",
            caution="human review remains available",
        )


@pytest.mark.anyio
async def test_child_report_draft_uses_a_tool_free_snapshot_profile() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report

    runtime = ReportRuntime()
    state = AgentV2State(
        request=V2RequestState(
            run_id="child-run",
            alert_id="alert-1",
            card_id="card-1",
            input_hash="a" * 64,
            target_stage="report_draft",
        )
    )

    envelope = await _report(runtime)(state)

    assert runtime.arguments["execution_profile"] == "report_snapshot_only"
    assert runtime.arguments["snapshot_bundle"] is not None
    report = envelope.data["report_draft"]
    assert isinstance(report, dict)
    assert report["tool_call_count"] == 0
    assert report["model_call_count"] <= 1
