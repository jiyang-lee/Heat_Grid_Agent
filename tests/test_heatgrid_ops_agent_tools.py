from __future__ import annotations

from pathlib import Path
import sys
from typing import Final

import orjson
import pytest

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(BACKEND_DIR))

from agent_report_writer_adapter import LocalReportWriterAdapter  # noqa: E402
from heatgrid_ops.agent.contracts import ReportWriteRequest  # noqa: E402
from heatgrid_ops.agent.models import JsonValue, OpsAgentOutput  # noqa: E402
from heatgrid_ops.agent.tools import (  # noqa: E402
    ALL_AGENT_TOOL_NAMES,
    GRAPH_CONTROLLED_TOOL_NAMES,
    LLM_SELECTABLE_TOOL_NAMES,
    make_external_context_tool,
    make_operational_tools,
    make_ops_evidence_tool,
)


def test_ops_evidence_and_external_context_tools_return_json_payloads() -> None:
    source_input = fake_source_input()
    external_context: dict[str, JsonValue] = {
        "status": "available",
        "site": {"status": "mapped", "apartment_name": "테스트 단지"},
        "weather": {"status": "available"},
        "retrieval": {"status": "available", "results": []},
    }

    evidence_tool = make_ops_evidence_tool(source_input)
    context_tool = make_external_context_tool(source_input, external_context)

    evidence = orjson.loads(evidence_tool.invoke({"card_id": "card-test"}))
    context = orjson.loads(context_tool.invoke({"card_id": "card-test"}))

    assert evidence["card_id"] == "card-test"
    assert evidence["sections"]["priority"]["priority_card"]["card_id"] == "card-test"
    assert context["site"]["apartment_name"] == "테스트 단지"


def test_tool_registry_has_no_generic_network_capability() -> None:
    tools = make_operational_tools(
        fake_source_input(),
        {
            "status": "available",
            "site": {"status": "mapped"},
            "weather": {"status": "available"},
            "retrieval": {"status": "available", "chunks": []},
        },
    )

    assert tuple(item.name for item in tools) == LLM_SELECTABLE_TOOL_NAMES
    assert len(LLM_SELECTABLE_TOOL_NAMES) == 8
    assert GRAPH_CONTROLLED_TOOL_NAMES == ("write_anomaly_report", "write_daily_report")
    assert len(ALL_AGENT_TOOL_NAMES) == 10
    assert not {"search_external_evidence", "stage_evidence_candidate"} & set(
        ALL_AGENT_TOOL_NAMES
    )

    for item in tools:
        payload = orjson.loads(item.invoke({"card_id": "card-test"}))
        assert isinstance(payload, dict)
        assert "error" not in payload


@pytest.mark.anyio
async def test_report_writer_adapter_writes_anomaly_and_daily_artifacts(
    tmp_path: Path,
) -> None:
    writer = LocalReportWriterAdapter(
        api_key=None,
        model="test-model",
        output_root=tmp_path,
        mock=True,
    )
    request = ReportWriteRequest(
        run_id="run-test",
        card_id="card-test",
        source_input=fake_source_input(),
        evidence_context={"status": "unavailable"},
        ops_output=OpsAgentOutput(
            summary="테스트 요약",
            action_plan="테스트 조치",
            caution="테스트 주의",
        ),
    )

    anomaly = await writer.write_anomaly(request)
    daily = await writer.write_daily(request)

    assert anomaly.name == "anomaly_report.json"
    assert daily.name == "daily_report.json"
    assert (
        tmp_path / "ops_agent" / "reports" / "run-test" / "anomaly_report.json"
    ).exists()
    assert (
        tmp_path / "ops_agent" / "reports" / "run-test" / "daily_report.json"
    ).exists()


def fake_source_input() -> dict[str, JsonValue]:
    priority_card: dict[str, JsonValue] = {
        "card_id": "card-test",
        "operational_label": "테스트 카드",
        "review_required": True,
        "recommended_action": "현장 점검",
        "why_reason": "테스트 근거",
    }
    priority_decision: dict[str, JsonValue] = {
        "priority_level": "high",
        "priority_score": 80.0,
        "trust_level": "medium",
        "current_best_priority_level": "high",
        "m1_specialist_priority_level": "high",
        "m1_specialist_primary_state": "warning",
        "m1_specialist_fault_group": "leakage_water_loss",
    }
    window: dict[str, JsonValue] = {
        "substation_id": 31,
        "manufacturer_id": "manufacturer 1",
        "configuration_type": "SH + DHW",
        "window_start": "2020-01-11T00:00:00+09:00",
        "window_end": "2020-01-11T06:00:00+09:00",
    }
    sections: dict[str, JsonValue] = {
        "priority": {
            "priority_card": priority_card,
            "priority_decision": priority_decision,
        },
        "window": window,
        "substation": {"substation_id": 31},
        "sensor_summaries": [],
        "model_outputs": [],
        "review_reasons": [{"reason_code": "current_only_high"}],
    }
    return {
        "card_id": "card-test",
        "sections": sections,
        "unsupported_sections": [],
        "raw_context": {
            "window": window,
            "substation": {"substation_id": 31},
            "sensor_summaries": [],
        },
        "priority_context": {
            "card": priority_card,
            "priority": priority_decision,
            "model_signals": priority_decision,
            "explanation": {
                **priority_card,
                "review_reasons": ["current_only_high"],
            },
            "model_outputs": [],
        },
    }
