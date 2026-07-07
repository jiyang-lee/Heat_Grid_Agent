import json

from httpx import ASGITransport, AsyncClient
import pytest

from heat_grid_ops.app import app
from heat_grid_ops.llm_input import build_ops_agent_llm_input, get_priority_rule
from heat_grid_ops.repository import load_example_input
from heat_grid_ops.schemas import OpsAgentOutput


@pytest.mark.anyio
async def test_simulation_returns_minimal_output_when_database_is_unavailable() -> None:
    card_id = "10000000-0000-0000-0000-000000000001"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(f"/api/simulate/{card_id}")

    assert response.status_code == 200
    payload = response.json()
    ops_input = payload["ops_input"]
    assert ops_input["input_version"] == "ops-agent-input-v0.2"
    assert set(ops_input) == {
        "input_version",
        "event_context",
        "control_context",
        "handoff_context",
    }
    event_context = ops_input["event_context"]
    control_context = ops_input["control_context"]
    handoff_context = ops_input["handoff_context"]
    raw_context = event_context["raw_context"]
    priority_context = event_context["priority_context"]
    assert priority_context["card"]["card_id"] == card_id
    assert raw_context["current_best_sensor_values"]["top_n"] == 10
    assert len(raw_context["current_best_sensor_values"]["values"]) == 10
    assert raw_context["m1_specialist_features"]["feature_count"] == 13
    assert len(raw_context["m1_specialist_features"]["features"]) == 13
    assert "formula" not in priority_context
    assert "review_reasons" not in priority_context
    assert "review_required" not in priority_context["card"]
    calculation = priority_context["priority"]["calculation"]
    explanation = priority_context["explanation"]
    assert calculation["current_best_weight"] == 0.65
    assert calculation["m1_specialist_weight"] == 0.35
    assert "current_best_priority_score" not in calculation
    assert "m1_specialist_priority_score" not in calculation
    assert explanation["review_required"] is True
    assert explanation["review_reasons"] == [
        "current_only_high",
        "lead_time_1_3d",
        "fault_group_leakage_water_loss",
    ]
    assert control_context["output_contract"]["required"] == [
        "summary",
        "action_plan",
        "caution",
    ]
    assert control_context["output_contract"]["additionalProperties"] is False
    assert handoff_context["escalation_context"]["review_required"] is True
    assert payload["ops_output"]["summary"]
    assert payload["ops_output"]["action_plan"]
    assert payload["ops_output"]["caution"]


def test_llm_input_builder_returns_v1_context_shape() -> None:
    source_input = load_example_input()

    llm_input = build_ops_agent_llm_input(source_input)

    assert llm_input.input_version == "ops-agent-input-v0.2"
    assert llm_input.event_context.raw_context == source_input.raw_context
    assert llm_input.event_context.priority_context == source_input.priority_context
    assert llm_input.control_context.output_contract.required == [
        "summary",
        "action_plan",
        "caution",
    ]
    assert llm_input.handoff_context.audit_context.card_id == (
        source_input.priority_context.card.card_id
    )


def test_priority_rule_returns_output_contract() -> None:
    rule = get_priority_rule()

    assert rule.output_contract.required == ["summary", "action_plan", "caution"]
    assert rule.output_contract.additionalProperties is False
    assert set(rule.output_contract.properties.model_dump()) == {
        "summary",
        "action_plan",
        "caution",
    }


def test_llm_input_excludes_local_document_references() -> None:
    llm_input = build_ops_agent_llm_input(load_example_input())

    serialized = json.dumps(llm_input.model_dump(mode="json"), ensure_ascii=False)

    for forbidden in [
        "C:/",
        "C:\\",
        "Obsidian",
        "Documents",
        "Heat_Grid_Agent_simulation",
        "05_시뮬레이션",
    ]:
        assert forbidden not in serialized


def test_ops_output_normalizes_list_action_plan() -> None:
    output = OpsAgentOutput.model_validate(
        {
            "summary": "요약",
            "action_plan": ["밸브 상태 확인", "primary return 온도 확인"],
            "caution": "검증 필요",
        }
    )

    assert output.action_plan == "밸브 상태 확인\nprimary return 온도 확인"
