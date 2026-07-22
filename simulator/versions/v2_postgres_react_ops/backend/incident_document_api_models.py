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


PROTOTYPE_DISCLAIMER = (
    "본 문서는 프로토타입 AI가 생성한 초안입니다. 실제 현장 적용 전 "
    "기계설비유지관리자와 안전관리자의 검토가 필요합니다."
)

WorkOrderKind = Literal["site_check", "maintenance"]
ChecklistResult = Literal["pass", "fail", "not_applicable", "pending"]


class WorkOrderHeader(FrozenIncidentDocumentModel):
    document_number: str = Field(min_length=1, max_length=80)
    issued_at: datetime
    priority: str = Field(min_length=1, max_length=40)
    assignee: str | None = Field(default=None, max_length=120)
    target_building: str = Field(min_length=1, max_length=200)
    mechanical_room: str | None = Field(default=None, max_length=200)
    equipment_type: str = Field(min_length=1, max_length=120)
    work_type: str = Field(min_length=1, max_length=120)
    issue_reason: str = Field(default="현장 확인 필요", min_length=1, max_length=1000)
    status: str = Field(default="검토 중", min_length=1, max_length=40)


class WorkOrderChecklistItem(FrozenIncidentDocumentModel):
    seq: int = Field(ge=1)
    instrument_or_target: str = Field(min_length=1, max_length=200)
    check_or_task_action: str = Field(min_length=1, max_length=400)
    pass_fail_criteria: str | None = Field(default=None, max_length=400)
    parts_or_tools: str | None = Field(default=None, max_length=400)
    completion_condition: str | None = Field(default=None, max_length=400)
    result: ChecklistResult = "pending"
    measured_before: str | None = Field(default=None, max_length=200)
    measured_after: str | None = Field(default=None, max_length=200)
    checked_by: str | None = Field(default=None, max_length=120)
    signature: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=400)


class BooleanChecklistItem(FrozenIncidentDocumentModel):
    label: str = Field(min_length=1, max_length=200)
    checked: bool = False


SAFETY_PERMIT_QUESTIONS: tuple[str, ...] = (
    "용접·용단·연마 등 불꽃 또는 고열이 발생하는가?",
    "탱크·피트·덕트 등 환기가 불충분한 공간에 출입하는가?",
    "전원 차단·잠금·표시 또는 전기반 작업이 필요한가?",
    "바닥·지반·배관 매설부 굴착이 필요한가?",
    "압력계통 개방, 고온수·증기 접촉 가능성이 있는가?",
    "펌프·모터·열교환기 부품의 인양이 필요한가?",
)


class SafetyPermitQuestion(FrozenIncidentDocumentModel):
    question: str = Field(min_length=1, max_length=200)
    applicable: bool = False
    required_action: str | None = Field(default=None, max_length=400)


class SafetyPermitPrecheck(FrozenIncidentDocumentModel):
    questions: tuple[SafetyPermitQuestion, ...] = Field(min_length=6, max_length=6)
    permit_required: bool = False


WorkOrderPatchSection = Literal[
    "purpose",
    "risk_and_evidence",
    "restriction_or_prep_checklist",
    "checklist",
    "commissioning_checklist",
    "outcome_and_followup",
    "safety_permit_precheck",
]


class WorkOrderFieldPatchRequest(FrozenIncidentDocumentModel):
    expected_version: int = Field(ge=1)
    edited_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    target_section: WorkOrderPatchSection
    target_seq: int = Field(ge=1)
    target_field: str = Field(min_length=1, max_length=60)
    new_value: str = Field(default="", max_length=400)


class WorkOrderStructuredContent(FrozenIncidentDocumentModel):
    work_order_kind: WorkOrderKind
    header: WorkOrderHeader
    purpose: str = Field(min_length=1, max_length=2000)
    risk_and_evidence: str = Field(min_length=1, max_length=3000)
    restriction_or_prep_checklist: tuple[BooleanChecklistItem, ...] = Field(default=())
    checklist: tuple[WorkOrderChecklistItem, ...] = Field(default=())
    commissioning_checklist: tuple[WorkOrderChecklistItem, ...] = Field(default=())
    outcome_and_followup: str = Field(min_length=1, max_length=2000)
    safety_permit_precheck: SafetyPermitPrecheck
    disclaimer: str = Field(default=PROTOTYPE_DISCLAIMER)


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
    content: IncidentDocumentContent | WorkOrderStructuredContent
    content_hash: str
    created_by: str
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None


class IncidentDocumentPage(FrozenIncidentDocumentModel):
    items: tuple[IncidentDocumentResponse, ...]
