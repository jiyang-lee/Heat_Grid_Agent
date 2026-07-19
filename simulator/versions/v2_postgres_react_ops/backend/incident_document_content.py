from __future__ import annotations

from hashlib import sha256

import orjson
from sqlalchemy.engine import RowMapping

from incident_document_api_models import (
    DocumentStatus,
    DocumentType,
    IncidentDocumentContent,
    IncidentDocumentEditRequest,
    IncidentEvidenceCitation,
)
from incident_document_repository_errors import IncidentDocumentConflictError


def content_from_row(row: RowMapping) -> IncidentDocumentContent:
    value = row["content"]
    payload = orjson.loads(value) if isinstance(value, str) else value
    return IncidentDocumentContent.model_validate(payload)


def generated_content(
    document_type: DocumentType,
    citations: tuple[IncidentEvidenceCitation, ...],
    *,
    model_available: bool,
) -> IncidentDocumentContent:
    if not model_available:
        return IncidentDocumentContent(
            title="AI generation retry required",
            body="Model credential is missing. No field action result is inferred.",
            actions=(),
            evidence=citations,
            safety_notes="Operator review is required before any transmission.",
        )
    match document_type:
        case "work_order":
            return IncidentDocumentContent(
                title="Incident inspection work order",
                body="Review anomaly evidence and inspect the affected machine room before field transmission.",
                actions=("Verify sensor trend against local equipment state.",),
                evidence=citations,
                safety_notes="Do not energize or isolate equipment without the field safety procedure.",
            )
        case "incident_report":
            return IncidentDocumentContent(
                title="Incident observation report",
                body="This report records observed anomaly evidence and operator decisions only.",
                actions=("Preserve sensor/model evidence for shift handover.",),
                evidence=citations,
                safety_notes="Repair outcome is unknown until separately observed.",
            )


def has_content_edit(request: IncidentDocumentEditRequest) -> bool:
    return any(
        item is not None
        for item in (
            request.title,
            request.body,
            request.actions,
            request.evidence_ids,
            request.safety_notes,
        )
    )


def document_status(value: str) -> DocumentStatus:
    match value:
        case "draft":
            return "draft"
        case "ai_reviewed":
            return "ai_reviewed"
        case "approved":
            return "approved"
        case "failed":
            return "failed"
        case _:
            raise IncidentDocumentConflictError(f"unknown document status: {value}")


def hash_json(value: dict[str, object]) -> str:
    return sha256(orjson.dumps(value, option=orjson.OPT_SORT_KEYS)).hexdigest()


def dump_json(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
