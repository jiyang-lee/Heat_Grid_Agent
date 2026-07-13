from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.models import (
    JsonObject,
    JsonValue,
    ModelVerificationResult,
    OpsAgentOutput,
    TokenCall,
    TokenUsage,
)


class AgentLoopSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    iterations: int = 0
    max_iterations: int = 0
    decision: str = "finalize"
    confidence: float = 0.0
    evidence_score: float = 0.0
    missing_evidence: list[str] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    action_decisions: list[JsonObject] = Field(default_factory=list)
    model_verification: ModelVerificationResult | None = None
    review_required: bool = True
    review_task_id: str | None = None


class AgentRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    input_source: Literal["alert"]
    alert_id: str
    card_id: str
    evaluation_run_id: str | None = None
    manufacturer_id: str | None = None
    substation_id: int | None = None
    parent_run_id: str | None = None
    trigger_type: str = "alert"
    requested_by: str | None = None
    trigger_reason: str | None = None
    approved_action_task_id: str | None = None
    agent_mode: Literal["llm", "fallback"] | None = None
    ops_output: OpsAgentOutput | None = None
    token_usage: TokenUsage | None = None
    loop_summary: AgentLoopSummary | None = None
    review_status: Literal["pending", "approved", "rejected", "corrected"] = "pending"
    review_task_id: str | None = None
    error: str | None = None


class ReviewTaskSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    task_type: str
    status: str


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    run_id: str
    kind: str
    name: str
    uri: str


class AutomationPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["human_only", "assisted", "guarded_auto"] = "human_only"
    auto_transition_enabled: bool = False
    minimum_review_count: int = 100
    minimum_approval_rate: float = 0.95
    minimum_confidence: float = 0.9
    minimum_source_trust: float = 0.85
    maximum_drift_score: float = 0.1
    reviewed_count: int = 0
    approval_rate: float = 0.0
    eligible_for_guarded_auto: bool = False


class EvidenceContextSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    rag_evidence: JsonObject
    external_data: JsonObject


class ModelInferenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    usable: bool = False
    payload: JsonObject = Field(default_factory=dict)
    error: str | None = None


class ExternalDataRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    substation_id: int
    window_start: str
    window_end: str


class ExternalDataSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    site: JsonObject = Field(default_factory=dict)
    weather: JsonObject = Field(default_factory=dict)


class RagEvidenceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    card_id: str
    source_input: JsonObject
    top_k: int = Field(ge=1, le=20)


class RagEvidenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    retrieval: JsonObject = Field(default_factory=dict)
    references: JsonObject = Field(default_factory=dict)


class ChatModelResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    output: OpsAgentOutput
    calls: list[TokenCall] = Field(default_factory=list)


class AgentStreamEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["llm", "tool_start", "tool_end", "token", "final"]
    message: str
    payload: JsonValue | None = None
    token_call: TokenCall | None = None
    output: OpsAgentOutput | None = None


class ModelVerificationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    card_id: str
    source_input: JsonObject
    attempt: int = Field(ge=1)


class ModelVerificationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    result: ModelVerificationResult
    artifact_uri: str | None = None


class ReportArtifactDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    name: str
    uri: str
