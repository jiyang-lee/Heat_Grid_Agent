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
    state_schema_version: Literal["agent_v2_state.v1"] = STATE_SCHEMA_VERSION
    request: V2RequestState
    ml: JsonObject = Field(default_factory=dict)
    weather: JsonObject = Field(default_factory=dict)
    rag: JsonObject = Field(default_factory=dict)
    fault: JsonObject = Field(default_factory=dict)
    escalation: JsonObject = Field(default_factory=dict)
    routing: V2RoutingState = Field(default_factory=V2RoutingState)
    report: JsonObject = Field(default_factory=dict)
    attempts: dict[str, int] = Field(default_factory=dict)
    audit: tuple[str, ...] = ()
    result: JsonObject = Field(default_factory=dict)