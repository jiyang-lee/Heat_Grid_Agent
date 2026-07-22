from __future__ import annotations

import sys
from pathlib import Path

from heatgrid_ops.agent.models import TokenCall, TokenUsage
from heatgrid_ops.agent.v2_models import STAGE_ORDER
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState


ROOT = Path(__file__).resolve().parents[1]


def test_v2_result_exposes_report_draft_usage_and_execution_duration() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_result import build_v2_graph_output

    state = AgentV2State(
        request=V2RequestState(
            run_id="child-run",
            alert_id="alert-1",
            card_id="card-1",
            input_hash="a" * 64,
        ),
        report_draft={
            "summary": "RAG 재검색 후 작성한 두 번째 초안",
            "action_plan": "현장 점검을 진행합니다.",
            "caution": "사람 검토가 필요합니다.",
            "token_usage": TokenUsage(
                model_calls=1,
                input_tokens=120,
                output_tokens=30,
                total_tokens=150,
                calls=[TokenCall(input_tokens=120, output_tokens=30, total_tokens=150)]
            ).model_dump(mode="json"),
        },
    )

    output = build_v2_graph_output(
        {"state": state, "completed_stages": STAGE_ORDER},
        execution_duration_ms=37,
    )

    result = output["result"].value
    assert result is not None
    assert result.ops_output is not None
    assert result.ops_output.model_dump(mode="json") == {
        "summary": "RAG 재검색 후 작성한 두 번째 초안",
        "action_plan": "현장 점검을 진행합니다.",
        "caution": "사람 검토가 필요합니다.",
    }
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 150
    assert result.loop_summary is not None
    assert result.loop_summary.execution_duration_ms == 37
