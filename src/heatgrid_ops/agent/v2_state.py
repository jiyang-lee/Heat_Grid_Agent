from __future__ import annotations

from typing import Literal

from pydantic import Field

from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.v2_models import (
    STATE_SCHEMA_VERSION,
    ReasonCategory,
    StageName,
    V2FrozenModel,
)


class V2RequestState(V2FrozenModel):
    run_id: str
    alert_id: str
    card_id: str
    source_input: JsonObject = Field(default_factory=dict)
    input_hash: str
    target_stage: StageName | None = None
    broaden: bool = False
    revision_feedback: tuple[str, ...] = ()


class V2RoutingState(V2FrozenModel):
    force_review: bool = False
    blocking_retry_exhausted: tuple[StageName, ...] = ()
    disposition: Literal[
        "urgent_review",
        "inspection_recommended",
        "normal_observation",
    ] | None = None
    reason_category: ReasonCategory | None = None


class AgentV2State(V2FrozenModel):
    state_schema_version: Literal["agent_v2_state.v2"] = STATE_SCHEMA_VERSION
    request: V2RequestState
    ml_validation: JsonObject = Field(default_factory=dict)
    weather_context: JsonObject = Field(default_factory=dict)
    rag_retrieval: JsonObject = Field(default_factory=dict)
    rag_interpretation: JsonObject = Field(default_factory=dict)
    fault_analysis: JsonObject = Field(default_factory=dict)
    higher_model_reassessment: JsonObject = Field(default_factory=dict)
    parent_disposition: V2RoutingState = Field(default_factory=V2RoutingState)
    report_draft: JsonObject = Field(default_factory=dict)
    report_fidelity: JsonObject = Field(default_factory=dict)
    attempts: dict[str, int] = Field(default_factory=dict)
    audit: tuple[str, ...] = ()
    result: JsonObject = Field(default_factory=dict)
