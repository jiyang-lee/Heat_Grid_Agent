from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self, assert_never

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StringConstraints,
    model_validator,
)


ReviewerName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]


class FrozenReviewModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FrozenReviewCaptureModel(FrozenReviewModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ReviewOpsAgentOutput(FrozenReviewModel):
    summary: str
    action_plan: str
    caution: str


class ReviewFinalResultSnapshot(FrozenReviewModel):
    status: Literal["completed", "failed"]
    agent_mode: Literal["llm", "fallback"] | None = None
    ops_output: ReviewOpsAgentOutput | None = None
    error: str | None = None


class ReviewDecisionStep(FrozenReviewModel):
    sequence: int = Field(ge=1)
    decision: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)


class ReviewDiagnosticHypothesis(FrozenReviewModel):
    hypothesis_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)


class ReviewDiagnosticSnapshot(FrozenReviewModel):
    trigger: str | None = Field(default=None, max_length=120)
    status: Literal[
        "not_triggered",
        "completed",
        "failed",
        "timeout",
        "invalid",
        "budget_exceeded",
    ]
    hypotheses: tuple[ReviewDiagnosticHypothesis, ...] = Field(
        default=(), max_length=3
    )
    attempts: int = Field(default=0, ge=0, le=2)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    input_token_limit: Literal[3000] = 3000
    output_token_limit: Literal[1000] = 1000
    deadline_seconds: Literal[60] = 60
    fallback_reason: str | None = Field(default=None, max_length=1000)


class ReviewComponentResult(FrozenReviewModel):
    component: str = Field(min_length=1, max_length=200)
    agreement: bool


class ReviewModelVerificationSnapshot(FrozenReviewModel):
    status: Literal["verified", "partial", "unavailable", "error"]
    agreement: bool | None = None
    component_results: tuple[ReviewComponentResult, ...] = ()
    stored_score: float | None = None
    current_score: float | None = None
    score_delta: float | None = None
    reason: str = Field(min_length=1, max_length=1000)


class ReviewProvenanceSnapshot(FrozenReviewModel):
    source: str = Field(min_length=1, max_length=500)
    source_owner: str | None = Field(default=None, max_length=200)
    snapshot_id: str | None = Field(default=None, max_length=200)
    retrieval_id: str | None = Field(default=None, max_length=200)
    document_id: str | None = Field(default=None, max_length=200)
    chunk_id: str | None = Field(default=None, max_length=200)
    error_type: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=500)


class ReviewWeatherSnapshot(FrozenReviewModel):
    status: str = Field(min_length=1, max_length=120)
    observed_at: str | None = Field(default=None, max_length=120)
    temperature_c: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    precipitation_mm: float | None = Field(default=None, ge=0.0)
    wind_speed_mps: float | None = Field(default=None, ge=0.0)
    provenance: ReviewProvenanceSnapshot


class ReviewEvidenceSnapshot(FrozenReviewModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    document_type: Literal["internal_rag", "operator_manual_evidence"]
    source_owner: str | None = Field(default=None, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    section: str | None = Field(default=None, max_length=500)
    score: float = Field(ge=0.0)
    excerpt: str = Field(min_length=1, max_length=4000)
    provenance: ReviewProvenanceSnapshot


class ReviewSourceCardSnapshot(FrozenReviewModel):
    card_id: str = Field(min_length=1)
    substation_id: int | None = None
    manufacturer_id: str | None = None
    priority_level: str = Field(min_length=1, max_length=120)
    status: str | None = Field(default=None, max_length=120)
    review_required: bool
    reason: str = Field(min_length=1, max_length=1000)


class ReviewCaptureEvidenceSnapshot(FrozenReviewCaptureModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    document_type: Literal["internal_rag", "operator_manual_evidence"]
    source_owner: str | None = Field(default=None, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    section: str | None = Field(default=None, max_length=500)
    score: float = Field(ge=0.0)
    excerpt: str = Field(min_length=1, max_length=4000)
    provenance: ReviewProvenanceSnapshot | None = None


class ReviewCaptureSourceCardSnapshot(FrozenReviewCaptureModel):
    card_id: str = Field(min_length=1)
    substation_id: int | None = None
    manufacturer_id: str | None = None
    priority_level: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=120)
    review_required: bool
    reason: str | None = Field(default=None, max_length=1000)


class AgentRunReviewCaptureSource(FrozenReviewCaptureModel):
    schema_version: Literal["agent_run_review_capture.v1"] = (
        "agent_run_review_capture.v1"
    )
    run_id: str = Field(min_length=1)
    result: ReviewFinalResultSnapshot
    loop_count: int = Field(ge=0)
    handling_reason: str = Field(min_length=1, max_length=1000)
    diagnostic: ReviewDiagnosticSnapshot
    model_verification: ReviewModelVerificationSnapshot | None = None
    weather: ReviewWeatherSnapshot | None = None
    evidence: tuple[ReviewCaptureEvidenceSnapshot, ...] = ()
    source_card: ReviewCaptureSourceCardSnapshot


class ReviewCaptureFailure(FrozenReviewCaptureModel):
    error_type: Literal["RuntimeError", "ValidationError"]
    message: str = Field(min_length=1, max_length=1000)


class ReviewBudgetLineage(FrozenReviewModel):
    parent_token_limit: int = Field(ge=1)
    parent_tokens_used: int = Field(ge=0)
    diagnostic_token_limit: int = Field(ge=1)
    diagnostic_tokens_used: int = Field(ge=0)


class ReviewCheckpointLineage(FrozenReviewModel):
    thread_id: str = Field(min_length=1)
    namespace: str
    checkpoint_id: str | None = None
    durability: Literal["sync"] = "sync"


class AgentRunReviewSnapshotV1(FrozenReviewModel):
    schema_version: Literal["agent_run_review.v1"] = "agent_run_review.v1"
    run_id: str = Field(min_length=1)
    result: ReviewFinalResultSnapshot
    decisions: tuple[ReviewDecisionStep, ...] = ()
    loop_count: int = Field(ge=0)
    handling_reason: str = Field(min_length=1, max_length=1000)
    diagnostic: ReviewDiagnosticSnapshot
    model_verification: ReviewModelVerificationSnapshot | None = None
    weather: ReviewWeatherSnapshot | None = None
    evidence: tuple[ReviewEvidenceSnapshot, ...] = ()
    source_card: ReviewSourceCardSnapshot
    budget: ReviewBudgetLineage
    checkpoint: ReviewCheckpointLineage


class ReviewEvidenceAnnotation(FrozenReviewModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    disposition: Literal["support", "dispute", "irrelevant"]
    note: str | None = Field(default=None, max_length=1000)


class AgentRunReviewRecord(FrozenReviewModel):
    review_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    review_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve", "correct", "keep_human_review"]
    reviewer: ReviewerName
    reason: str = Field(min_length=1, max_length=2000)
    disposition: str | None = Field(default=None, max_length=500)
    correction: ReviewOpsAgentOutput | None = None
    evidence_annotations: tuple[ReviewEvidenceAnnotation, ...] = ()
    operator_labels: tuple[str, ...] = ()
    created_at: datetime


class AgentPolicyProposal(FrozenReviewModel):
    scope: Literal[
        "evidence_threshold",
        "diagnostic_trigger",
        "human_review_route",
    ]
    operation: Literal["set", "increase", "decrease"]
    target: Literal[
        "minimum_evidence_score",
        "diagnostic_priority_trigger",
        "force_human_review",
    ]
    value: StrictBool | StrictFloat | Literal["urgent", "high"]

    @model_validator(mode="after")
    def validate_allowlisted_combination(self) -> Self:
        match self.scope:
            case "evidence_threshold":
                valid = (
                    self.target == "minimum_evidence_score"
                    and self.operation in {"set", "increase", "decrease"}
                    and isinstance(self.value, float)
                    and 0.0 <= self.value <= 1.0
                )
            case "diagnostic_trigger":
                valid = (
                    self.target == "diagnostic_priority_trigger"
                    and self.operation == "set"
                    and self.value in {"urgent", "high"}
                )
            case "human_review_route":
                valid = (
                    self.target == "force_human_review"
                    and self.operation == "set"
                    and isinstance(self.value, bool)
                )
            case unreachable:
                assert_never(unreachable)
        if not valid:
            raise ValueError("unsupported policy proposal combination")
        return self


class PolicyCandidateDecision(FrozenReviewModel):
    version: int = Field(ge=1)
    decision: Literal["created", "approved", "rejected"]
    reviewer: ReviewerName
    reason: str = Field(min_length=1, max_length=2000)
    created_at: datetime


class AgentPolicyCandidate(FrozenReviewModel):
    candidate_id: str = Field(min_length=1)
    source_review_id: str = Field(min_length=1)
    status: Literal["pending", "approved", "rejected"]
    version: int = Field(ge=1)
    proposal: AgentPolicyProposal
    supporting_evidence_ids: tuple[str, ...] = ()
    decision_history: tuple[PolicyCandidateDecision, ...] = ()
    created_at: datetime
    updated_at: datetime
