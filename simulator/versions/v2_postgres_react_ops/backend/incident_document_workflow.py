from __future__ import annotations

from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from incident_document_api_models import (
    IncidentDocumentContent,
    IncidentDocumentEditRequest,
    IncidentDocumentResponse,
    IncidentEvidenceCitation,
)
from incident_document_store import insert_review, response_from_row


async def record_generation_review(
    connection: AsyncConnection,
    *,
    document_version_id: str,
    model_available: bool,
    evidence: tuple[IncidentEvidenceCitation, ...],
) -> None:
    await insert_review(
        connection,
        document_version_id=document_version_id,
        review_type="ai_review",
        decision="pending" if model_available else "failed",
        note=(
            "AI review queued for generated draft."
            if model_available
            else "OPENAI_API_KEY is missing; generation can be retried."
        ),
        actor="system",
        evidence=evidence,
    )


async def append_note_or_current(
    connection: AsyncConnection,
    current: RowMapping,
    request: IncidentDocumentEditRequest,
    content: IncidentDocumentContent,
) -> IncidentDocumentResponse:
    if request.note is not None:
        await insert_review(
            connection,
            document_version_id=str(current["document_version_id"]),
            review_type="operator_note",
            decision="pending",
            note=request.note,
            actor=request.edited_by,
            evidence=content.evidence,
        )
    return await response_from_row(connection, current)


def edited_content(
    content: IncidentDocumentContent,
    request: IncidentDocumentEditRequest,
    evidence: tuple[IncidentEvidenceCitation, ...],
) -> IncidentDocumentContent:
    return IncidentDocumentContent(
        title=content.title if request.title is None else request.title,
        body=content.body if request.body is None else request.body,
        actions=content.actions if request.actions is None else request.actions,
        evidence=evidence,
        safety_notes=content.safety_notes if request.safety_notes is None else request.safety_notes,
    )
