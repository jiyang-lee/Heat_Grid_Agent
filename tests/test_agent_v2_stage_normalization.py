from __future__ import annotations

from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState


def test_v2_state_keeps_each_stage_result_in_a_distinct_field() -> None:
    state = AgentV2State(
        request=V2RequestState(
            run_id="run-1",
            alert_id="alert-1",
            card_id="card-1",
            input_hash="a" * 64,
        )
    )

    assert state.state_schema_version == "agent_v2_state.v2"
    assert {
        "ml_validation",
        "weather_context",
        "rag_retrieval",
        "rag_interpretation",
        "fault_analysis",
        "higher_model_reassessment",
        "parent_disposition",
        "report_draft",
        "report_fidelity",
    } <= set(AgentV2State.model_fields)
    assert {"ml", "weather", "rag", "fault", "escalation", "report"}.isdisjoint(
        AgentV2State.model_fields
    )
