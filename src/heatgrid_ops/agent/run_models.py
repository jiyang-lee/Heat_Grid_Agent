from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.models import (
    JsonObject,
    ModelVerificationResult,
    OpsAgentOutput,
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
    external_candidate_ids: list[str] = Field(default_factory=list)
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


class EvidenceCandidateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    source_type: Literal["web", "manual", "internal"] = "manual"
    source_uri: str | None = None
    title: str
    content: str
    query: str | None = None
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: JsonObject = Field(default_factory=dict)
    requested_by: str = "agent"


class EvidenceCandidateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    title: str
    content: str
    source_uri: str | None = None
    status: str
    trust_score: float


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
