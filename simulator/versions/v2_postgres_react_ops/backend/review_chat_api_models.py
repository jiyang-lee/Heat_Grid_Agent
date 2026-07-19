from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenReviewChatModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


ChatRole = Literal["system_event", "operator", "assistant"]
ChatMessageKind = Literal[
    "question",
    "explanation",
    "action_request",
    "action_proposal",
    "confirmation",
    "execution_result",
    "error",
]
ProposalStatus = Literal[
    "draft",
    "awaiting_confirmation",
    "confirmed",
    "executing",
    "executed",
    "cancelled",
    "expired",
    "stale",
    "conflict",
    "failed",
]
ReviewDecision = Literal["approve", "reject", "correct", "keep_human_review"]
ReviewNextAction = Literal[
    "none",
    "targeted_rerun",
    "manual_investigation",
    "close_without_rerun",
]


class ReviewChatOpenRequest(FrozenReviewChatModel):
    created_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ReviewChatThreadResponse(FrozenReviewChatModel):
    thread_id: str
    run_id: str
    status: Literal["open", "closed", "archived"]
    context_hash: str
    base_review_version: int
    created_at: datetime


class ReviewChatDocumentContext(FrozenReviewChatModel):
    document_version_id: str | None = Field(default=None, min_length=1, max_length=80)
    document_type: Literal["work_order", "incident_report"] | None = None
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_document_reference(self) -> "ReviewChatDocumentContext":
        if self.document_version_id is None and self.document_type is None:
            raise ValueError("document_version_id or document_type is required")
        return self


class ReviewChatMessageRequest(FrozenReviewChatModel):
    content: str = Field(min_length=1, max_length=8000)
    created_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    document_context: ReviewChatDocumentContext | None = None
    incident_id: str | None = Field(default=None, min_length=1, max_length=80)
    citation_ids: tuple[str, ...] = Field(default=())


class ReviewChatMessageResponse(FrozenReviewChatModel):
    message_id: str
    thread_id: str
    sequence: int
    role: ChatRole
    message_kind: ChatMessageKind
    content: str
    structured_payload: dict[str, object]
    citations: tuple[dict[str, str], ...]
    context_hash: str
    created_at: datetime


class ReviewChatMessagePage(FrozenReviewChatModel):
    items: tuple[ReviewChatMessageResponse, ...]


class ReviewChatProposalResponse(FrozenReviewChatModel):
    proposal_id: str
    thread_id: str
    run_id: str
    expected_review_version: int
    context_hash: str
    status: ProposalStatus
    decision: ReviewDecision
    next_action: ReviewNextAction
    reason: str
    reason_category: str | None
    disposition: str | None
    correction: dict[str, str] | None
    target_stage: str | None
    revision: dict[str, str] | None = None
    expires_at: datetime


class ReviewChatSubmissionResponse(FrozenReviewChatModel):
    operator_message: ReviewChatMessageResponse
    assistant_message: ReviewChatMessageResponse
    proposal: ReviewChatProposalResponse | None = None


class ReviewChatConfirmRequest(FrozenReviewChatModel):
    confirmed_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    expected_proposal_status: Literal["awaiting_confirmation"]
    expected_review_version: int = Field(ge=0)


class ReviewChatConfirmationResponse(FrozenReviewChatModel):
    proposal_id: str
    status: ProposalStatus
    review_id: str | None = None
    child_run_id: str | None = None
    target_stage: str | None = None


class ReviewChatCancelRequest(FrozenReviewChatModel):
    cancelled_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
