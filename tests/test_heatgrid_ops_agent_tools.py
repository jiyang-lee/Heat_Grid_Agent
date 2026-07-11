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

from heatgrid_ops.agent.tools import (
    ALL_AGENT_TOOL_NAMES,
    GRAPH_CONTROLLED_TOOL_NAMES,
    LLM_SELECTABLE_TOOL_NAMES,
    make_anomaly_report_tool,
    make_daily_report_tool,
    make_external_context_tool,
    make_external_search_tool,
    make_operational_tools,
    make_ops_evidence_tool,
    make_stage_evidence_candidate_tool,
)
from heatgrid_ops.agent.external_search import ExternalEvidenceSearchResult
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


def test_tool_registry_has_eight_llm_tools_and_four_graph_tools() -> None:
    source_input = fake_source_input()
    external_context: dict[str, JsonValue] = {
        "status": "available",
        "site": {"status": "mapped"},
        "weather": {"status": "available"},
        "retrieval": {"status": "available", "chunks": []},
    }
    tools = make_operational_tools(source_input, external_context)

    assert tuple(item.name for item in tools) == LLM_SELECTABLE_TOOL_NAMES
    assert len(LLM_SELECTABLE_TOOL_NAMES) == 8
    assert len(GRAPH_CONTROLLED_TOOL_NAMES) == 4
    assert len(ALL_AGENT_TOOL_NAMES) == 12
    assert set(LLM_SELECTABLE_TOOL_NAMES).isdisjoint(GRAPH_CONTROLLED_TOOL_NAMES)

    for item in tools:
        payload = orjson.loads(item.invoke({"card_id": "card-test"}))
        assert isinstance(payload, dict)
        assert "error" not in payload


@pytest.mark.anyio
async def test_graph_controlled_tools_expose_search_and_staging_boundaries() -> None:
    async def search(query: str) -> ExternalEvidenceSearchResult:
        return ExternalEvidenceSearchResult(status="no_match", query=query)

    async def stage(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return {"candidate_id": "candidate-1", "payload": payload}

    search_tool = make_external_search_tool(search)
    stage_tool = make_stage_evidence_candidate_tool(stage)
    graph_tools = (
        search_tool,
        stage_tool,
        make_anomaly_report_tool(mock=True),
        make_daily_report_tool(mock=True),
    )

    assert tuple(item.name for item in graph_tools) == GRAPH_CONTROLLED_TOOL_NAMES
    search_result = orjson.loads(await search_tool.ainvoke({"query": "heat grid"}))
    stage_result = orjson.loads(
        await stage_tool.ainvoke({"payload_json": to_json({"title": "candidate"})})
    )
    assert search_result["status"] == "no_match"
    assert stage_result["candidate_id"] == "candidate-1"


def test_write_daily_report_tool_writes_json_artifact(tmp_path: Path) -> None:
    report_tool = make_daily_report_tool(output_root=tmp_path, mock=True)
    payload = {
        "run_id": "run-daily",
        "card_id": "card-test",
        "source_input": fake_source_input(),
        "external_context": {"status": "unavailable"},
        "ops_output": {
            "summary": "summary",
            "action_plan": "action",
            "caution": "caution",
        },
    }

    result = orjson.loads(report_tool.invoke({"payload_json": to_json(payload)}))
    artifact_path = (
        tmp_path / "ops_agent" / "reports" / "run-daily" / "daily_report.json"
    )

    assert result["kind"] == "daily_report"
    assert result["name"] == "daily_report.json"
    assert artifact_path.exists()


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
