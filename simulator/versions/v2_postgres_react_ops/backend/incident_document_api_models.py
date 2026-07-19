from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal["work_order", "incident_report"]
DocumentStatus = Literal["draft", "ai_reviewed", "approved", "failed"]
ReviewState = Literal["none", "pending_ai_review", "operator_noted", "approved", "failed"]


class FrozenIncidentDocumentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IncidentEvidenceCitation(FrozenIncidentDocumentModel):
    citation_id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)


class IncidentDocumentContent(FrozenIncidentDocumentModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    actions: tuple[str, ...] = Field(default=())
    evidence: tuple[IncidentEvidenceCitation, ...] = Field(default=())
    safety_notes: str = Field(default="", max_length=4000)


class IncidentDocumentGenerateRequest(FrozenIncidentDocumentModel):
    created_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    evidence_ids: tuple[str, ...] = Field(default=())


class IncidentDocumentEditRequest(FrozenIncidentDocumentModel):
    expected_version: int = Field(ge=1)
    edited_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    actions: tuple[str, ...] | None = None
    evidence_ids: tuple[str, ...] | None = None
    safety_notes: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, min_length=1, max_length=4000)


class IncidentDocumentApproveRequest(FrozenIncidentDocumentModel):
    expected_version: int = Field(ge=1)
    approved_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=4000)


class IncidentDocumentResponse(FrozenIncidentDocumentModel):
    document_version_id: str
    episode_id: str
    document_type: DocumentType
    version: int
    parent_document_version_id: str | None
    status: DocumentStatus
    review_state: ReviewState
    retryable: bool
    content: IncidentDocumentContent
    content_hash: str
    created_by: str
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None


class IncidentDocumentPage(FrozenIncidentDocumentModel):
    items: tuple[IncidentDocumentResponse, ...]
