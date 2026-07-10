from __future__ import annotations

from pathlib import Path
import sys
from typing import Final

import orjson

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(BACKEND_DIR))

from heatgrid_ops.agent.tools import (
    make_anomaly_report_tool,
    make_external_context_tool,
    make_ops_evidence_tool,
)
from schemas import JsonValue


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


def test_write_anomaly_report_tool_writes_json_artifact(tmp_path: Path) -> None:
    report_tool = make_anomaly_report_tool(output_root=tmp_path, mock=True)
    payload = {
        "run_id": "run-test",
        "card_id": "card-test",
        "source_input": fake_source_input(),
        "external_context": {"status": "unavailable"},
        "ops_output": {
            "summary": "테스트 요약",
            "action_plan": "테스트 조치",
            "caution": "테스트 주의",
        },
    }

    result = orjson.loads(report_tool.invoke({"payload_json": to_json(payload)}))
    artifact_path = tmp_path / "ops_agent" / "reports" / "run-test" / "anomaly_report.json"

    assert result["kind"] == "anomaly_report"
    assert result["name"] == "anomaly_report.json"
    assert result["uri"] == "output/ops_agent/reports/run-test/anomaly_report.json"
    assert artifact_path.exists()
    assert orjson.loads(artifact_path.read_bytes())["report_metadata"]["report_type"] == "anomaly_report"


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


def to_json(payload: dict[str, JsonValue]) -> str:
    return orjson.dumps(payload).decode("utf-8")
