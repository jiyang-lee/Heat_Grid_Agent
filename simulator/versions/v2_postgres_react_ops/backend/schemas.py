from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


class OpsAgentOutput(BaseModel):
    summary: str
    action_plan: str
    caution: str


class TokenCall(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class CostEstimate(BaseModel):
    model: str
    input_usd_per_1m: float
    cached_input_usd_per_1m: float
    output_usd_per_1m: float
    input_cost_usd: float
    cached_input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_source: str


class TokenUsage(BaseModel):
    model_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    evidence_payload_chars: int = 0
    cost_estimate: CostEstimate | None = None
    calls: list[TokenCall] = Field(default_factory=list)


class SimulationResponse(BaseModel):
    card_id: str
    input_source: Literal["postgresql"]
    agent_mode: Literal["llm", "fallback"]
    ops_output: OpsAgentOutput
    token_usage: TokenUsage


class CardSummary(BaseModel):
    card_id: str
    manufacturer_id: str
    substation_id: str | int | None
    operational_label: str | None
    primary_state: str | None
    review_required: bool
    trust_level: str | None
    priority_level: str | None
    priority_score: float | None
    current_best_weight: float | None
    m1_specialist_weight: float | None
    current_best_priority_score: float | None
    m1_specialist_priority_score: float | None
    why_reason: str | None
    recommended_action: str | None
    stable_crossing_lead_hours: float | None
    window_start: str | None
    window_end: str | None
    window_label: str | None
    fault_event_id: str | None
