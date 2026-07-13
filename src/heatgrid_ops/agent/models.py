from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue as PydanticJsonValue


JsonValue: TypeAlias = PydanticJsonValue
JsonObject: TypeAlias = dict[str, JsonValue]


class OpsAgentOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    action_plan: str
    caution: str


class TokenCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class CostEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    model_config = ConfigDict(frozen=True)

    card_id: str
    input_source: Literal["postgresql"]
    agent_mode: Literal["llm", "fallback"]
    ops_output: OpsAgentOutput
    token_usage: TokenUsage


class ModelVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["verified", "partial", "unavailable", "error"]
    attempt: int = 1
    feature_count: int = 0
    feature_coverage: float = 0.0
    risk_score: float | None = None
    stored_risk_score: float | None = None
    risk_score_delta: float | None = None
    anomaly_score: float | None = None
    anomaly_label: bool | None = None
    leadtime_bucket: str | None = None
    stored_leadtime_bucket: str | None = None
    priority_score: float | None = None
    stored_priority_score: float | None = None
    priority_score_delta: float | None = None
    priority_level: str | None = None
    m1_specialist_priority_score: float | None = None
    component_agreement: dict[str, bool] = Field(default_factory=dict)
    agreement: bool | None = None
    active_model_version: str | None = None
    evaluation_run_id: str | None = None
    manufacturer_id: str | None = None
    substation_id: int | None = None
    reasons: list[str] = Field(default_factory=list)
