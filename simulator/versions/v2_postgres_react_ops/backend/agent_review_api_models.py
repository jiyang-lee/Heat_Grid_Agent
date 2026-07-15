from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from heatgrid_ops.agent.review_models import AgentRunReviewSnapshotV1
from heatgrid_ops.agent.v2_models import ReasonCategory


OperatorReviewStatus: TypeAlias = Literal[
    "pending",
    "approved",
    "corrected",
    "keep_human_review",
]
WorkerStatus: TypeAlias = Literal[
    "not_triggered",
    "running",
    "completed",
    "failed",
    "timeout",
    "invalid",
    "budget_exceeded",
]
ReviewSnapshotStatus: TypeAlias = Literal[
    "pending",
    "available",
    "unavailable",
    "legacy_unavailable",
]
CitationCoverage: TypeAlias = Literal[
    "complete",
    "partial",
    "missing",
    "not_applicable",
]
InputValidity: TypeAlias = Literal["valid", "invalid", "unavailable"]
ParentHandling: TypeAlias = Literal[
    "used_as_support",
    "invalid",
    "unavailable",
    "fallback_to_human",
]
EvidenceCompleteness: TypeAlias = Literal["complete", "partial", "missing"]
PolicyCandidateStatus: TypeAlias = Literal["pending", "approved", "rejected"]
PolicyCandidateAction: TypeAlias = Literal["approved", "rejected"]


class FrozenApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentRunListItem(FrozenApiModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    alert_id: str
    card_id: str
    priority: str | None = None
    operator_review_status: OperatorReviewStatus
    worker_status: WorkerStatus
    review_snapshot_status: ReviewSnapshotStatus
    created_at: datetime
    updated_at: datetime


class AgentRunListPage(FrozenApiModel):
    items: tuple[AgentRunListItem, ...]
    next_cursor: str | None = None


class AgentRunReviewSnapshotResponse(FrozenApiModel):
    run_id: str
    status: ReviewSnapshotStatus
    schema_version: Literal["agent_run_review.v1"] | None = None
    snapshot_hash: str | None = None
    snapshot: AgentRunReviewSnapshotV1 | None = None
    created_at: datetime | None = None
    unavailable_reason: str | None = None


class AgentRunEvaluationItem(FrozenApiModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    alert_id: str
    card_id: str
    operator_review_status: OperatorReviewStatus
    worker_status: WorkerStatus
    citation_coverage: CitationCoverage
    input_validity: InputValidity
    parent_handling: ParentHandling
    evidence_completeness: EvidenceCompleteness
    review_snapshot_status: ReviewSnapshotStatus
    created_at: datetime
    updated_at: datetime


class AgentRunEvaluationPage(FrozenApiModel):
    items: tuple[AgentRunEvaluationItem, ...]
    next_cursor: str | None = None


class OperatorReviewSubmitRequest(FrozenApiModel):
    expected_review_version: int
    idempotency_key: str
    decision: Literal["approve", "reject", "correct", "keep_human_review"]
    reviewer: str
    reason: str
    reason_category: ReasonCategory | None = None
    next_action: Literal[
        "none",
        "targeted_rerun",
        "manual_investigation",
        "close_without_rerun",
    ] = "none"
    disposition: Literal[
        "normal_observation",
        "inspection_recommended",
        "urgent_review",
    ]
    correction: dict[str, str] | None = None
    evidence_annotations: tuple[dict[str, str | None], ...] = ()
    operator_labels: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_reason_category(self) -> OperatorReviewSubmitRequest:
        if self.decision in {"reject", "keep_human_review"} and not self.reason_category:
            raise ValueError("reason_category is required for this decision")
        if self.next_action == "targeted_rerun" and not self.reason_category:
            raise ValueError("reason_category is required for targeted rerun")
        return self


class OperatorReviewRecordResponse(FrozenApiModel):
    review_id: str
    review_task_id: str
    run_id: str | None
    subject_type: str
    subject_key: str
    review_contract_version: int
    review_version: int
    idempotency_key: str
    request_hash: str
    decision: Literal["approve", "correct", "reject", "keep_human_review"]
    reviewer: str
    reason: str
    reason_category: str | None = None
    next_action: str = "none"
    disposition: str | None = None
    correction: dict[str, str] | None = None
    evidence_annotations: tuple[dict[str, str | None], ...] = ()
    operator_labels: tuple[str, ...] = ()
    created_at: datetime
    child_run_id: str | None = None
    routing_status: str | None = None
    target_stage: str | None = None


class OperatorReviewHistoryResponse(FrozenApiModel):
    run_id: str
    items: tuple[OperatorReviewRecordResponse, ...]


class PolicyCandidateDecisionRequest(FrozenApiModel):
    expected_version: int
    reviewer: str
    reason: str


class PolicyCandidateResponse(FrozenApiModel):
    candidate_id: str
    source_review_id: str
    status: PolicyCandidateStatus
    version: int
    scope: str
    proposal: dict[str, str | float | bool]
    supporting_evidence_ids: tuple[str, ...] = ()
    decision_history: tuple[dict[str, str | int], ...] = ()
    created_at: datetime
    updated_at: datetime


class PolicyCandidatePage(FrozenApiModel):
    items: tuple[PolicyCandidateResponse, ...]


class AgentOperationsMetricsResponse(FrozenApiModel):
    run_count: int
    pending_review_count: int
    approved_review_count: int
    corrected_review_count: int
    keep_human_review_count: int
    diagnostic_completed_count: int
    diagnostic_timeout_count: int
    diagnostic_invalid_count: int
    diagnostic_budget_exceeded_count: int
    policy_candidate_pending_count: int
    policy_candidate_approved_count: int
    policy_candidate_rejected_count: int
    approval_rate: float
    correction_rate: float
