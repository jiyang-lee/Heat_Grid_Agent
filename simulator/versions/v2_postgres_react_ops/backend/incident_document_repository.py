from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from incident_document_api_models import DocumentType, IncidentDocumentApproveRequest, IncidentDocumentEditRequest
from incident_document_api_models import IncidentDocumentContent, IncidentDocumentGenerateRequest, IncidentDocumentPage, IncidentDocumentResponse
from incident_document_api_models import IncidentEvidenceCitation
from incident_document_api_models import WorkOrderFieldPatchRequest, WorkOrderStructuredContent
from incident_document_content import content_from_row, generated_content, has_content_edit
from incident_document_idempotency import begin_idempotent_operation, complete_idempotency
from incident_document_idempotency import operation_scope, request_hash
from incident_document_repository_errors import IncidentDocumentConflictError, IncidentDocumentNotFoundError
from incident_document_store import (
    document_by_id, document_columns, has_approval, insert_review, insert_version,
    latest_version, require_episode, response_from_row, validate_citations,
)
from incident_document_workflow import append_note_or_current, edited_content, record_generation_review
from work_order_generation import WorkOrderPatchError, apply_work_order_patch


class IncidentDocumentRepository(Protocol):
    async def generate_document(
        self,
        episode_id: str,
        document_type: DocumentType,
        request: IncidentDocumentGenerateRequest,
        *,
        model_available: bool,
    ) -> IncidentDocumentResponse: ...

    async def edit_document(
        self,
        episode_id: str,
        document_type: DocumentType,
        version: int,
        request: IncidentDocumentEditRequest,
    ) -> IncidentDocumentResponse: ...

    async def approve_document(
        self,
        episode_id: str,
        document_type: DocumentType,
        request: IncidentDocumentApproveRequest,
    ) -> IncidentDocumentResponse: ...

    async def list_documents(self, episode_id: str) -> IncidentDocumentPage: ...

    async def patch_work_order_field(
        self,
        episode_id: str,
        version: int,
        request: WorkOrderFieldPatchRequest,
    ) -> IncidentDocumentResponse: ...


@dataclass(frozen=True, slots=True)
class PostgresIncidentDocumentRepository:
    engine: AsyncEngine

    async def generate_document(
        self,
        episode_id: str,
        document_type: DocumentType,
        request: IncidentDocumentGenerateRequest,
        *,
        model_available: bool,
    ) -> IncidentDocumentResponse:
        async with self.engine.begin() as connection:
            citations = await validate_citations(connection, episode_id, request.evidence_ids)
            payload_hash = request_hash(
                "generate",
                episode_id,
                document_type,
                request.model_dump(mode="json"),
            )
            scope = operation_scope("generate", episode_id, document_type)
            existing_id = await begin_idempotent_operation(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
            )
            if existing_id is not None:
                return await response_from_row(connection, await document_by_id(connection, existing_id))
            latest = await latest_version(connection, episode_id, document_type)
            if latest is not None and (str(latest["status"]) != "failed" or not model_available):
                return await response_from_row(connection, latest)
            next_version = 1 if latest is None else int(latest["version"]) + 1
            parent_id = None if latest is None else str(latest["document_version_id"])
            status = "draft" if model_available else "failed"
            content = _generated_or_supplied_content(
                document_type,
                request.content,
                citations,
                model_available=model_available,
            )
            row = await insert_version(
                connection,
                episode_id=episode_id,
                document_type=document_type,
                version=next_version,
                parent_document_version_id=parent_id,
                status=status,
                content=content,
                actor=request.created_by,
            )
            await record_generation_review(
                connection,
                document_version_id=str(row["document_version_id"]),
                model_available=model_available,
                evidence=content.evidence,
            )
            await complete_idempotency(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
                document_version_id=str(row["document_version_id"]),
            )
            return await response_from_row(connection, row)

    async def edit_document(
        self,
        episode_id: str,
        document_type: DocumentType,
        version: int,
        request: IncidentDocumentEditRequest,
    ) -> IncidentDocumentResponse:
        async with self.engine.begin() as connection:
            payload_hash = request_hash(
                "edit",
                episode_id,
                document_type,
                {"version": version, "payload": request.model_dump(mode="json")},
            )
            scope = operation_scope("edit", episode_id, document_type)
            existing_id = await begin_idempotent_operation(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
            )
            if existing_id is not None:
                return await response_from_row(connection, await document_by_id(connection, existing_id))
            current = await latest_version(connection, episode_id, document_type)
            if current is None or int(current["version"]) != version:
                raise IncidentDocumentConflictError("document version is no longer current")
            if version != request.expected_version:
                raise IncidentDocumentConflictError("expected document version is stale")
            if await has_approval(connection, str(current["document_version_id"])):
                raise IncidentDocumentConflictError("approved document versions are immutable")
            content = content_from_row(current)
            if isinstance(content, WorkOrderStructuredContent):
                raise IncidentDocumentConflictError(
                    "structured work orders must be edited via the work-order field API"
                )
            if not has_content_edit(request):
                response = await append_note_or_current(connection, current, request, content)
                await complete_idempotency(
                    connection,
                    operation_scope=scope,
                    idempotency_key=request.idempotency_key,
                    request_hash=payload_hash,
                    document_version_id=response.document_version_id,
                )
                return response
            evidence = content.evidence
            if request.evidence_ids is not None:
                evidence = await validate_citations(connection, episode_id, request.evidence_ids)
            next_content = edited_content(content, request, evidence)
            row = await insert_version(
                connection,
                episode_id=episode_id,
                document_type=document_type,
                version=version + 1,
                parent_document_version_id=str(current["document_version_id"]),
                status="draft",
                content=next_content,
                actor=request.edited_by,
            )
            await insert_review(
                connection,
                document_version_id=str(row["document_version_id"]),
                review_type="ai_review",
                decision="pending",
                note="Content changed; AI re-review is required.",
                actor="system",
                evidence=next_content.evidence,
            )
            await complete_idempotency(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
                document_version_id=str(row["document_version_id"]),
            )
            return await response_from_row(connection, row)

    async def approve_document(
        self,
        episode_id: str,
        document_type: DocumentType,
        request: IncidentDocumentApproveRequest,
    ) -> IncidentDocumentResponse:
        async with self.engine.begin() as connection:
            payload_hash = request_hash(
                "approve",
                episode_id,
                document_type,
                request.model_dump(mode="json"),
            )
            scope = operation_scope("approve", episode_id, document_type)
            existing_id = await begin_idempotent_operation(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
            )
            if existing_id is not None:
                return await response_from_row(connection, await document_by_id(connection, existing_id))
            current = await latest_version(connection, episode_id, document_type)
            if current is None:
                raise IncidentDocumentNotFoundError(episode_id)
            if int(current["version"]) != request.expected_version:
                raise IncidentDocumentConflictError("expected document version is stale")
            document_version_id = str(current["document_version_id"])
            if not await has_approval(connection, document_version_id):
                approved_content = content_from_row(current)
                evidence = (
                    ()
                    if isinstance(approved_content, WorkOrderStructuredContent)
                    else approved_content.evidence
                )
                await insert_review(
                    connection,
                    document_version_id=document_version_id,
                    review_type="approval",
                    decision="approved",
                    note=request.note,
                    actor=request.approved_by,
                    evidence=evidence,
                )
            await complete_idempotency(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
                document_version_id=document_version_id,
            )
            return await response_from_row(connection, current)

    async def list_documents(self, episode_id: str) -> IncidentDocumentPage:
        async with self.engine.connect() as connection:
            await require_episode(connection, episode_id)
            result = await connection.execute(
                text(
                    "SELECT " + document_columns() + " FROM incident_document_versions "
                    "WHERE episode_id = :episode_id "
                    "ORDER BY document_type, version DESC"
                ),
                {"episode_id": episode_id},
            )
            rows = result.mappings().all()
            items = tuple([await response_from_row(connection, row) for row in rows])
        return IncidentDocumentPage(items=items)


def _generated_or_supplied_content(
    document_type: DocumentType,
    supplied: IncidentDocumentContent | None,
    citations: tuple[IncidentEvidenceCitation, ...],
    *,
    model_available: bool,
) -> IncidentDocumentContent:
    if supplied is None:
        return generated_content(document_type, citations, model_available=model_available)
    return IncidentDocumentContent(
        title=supplied.title,
        body=supplied.body,
        actions=supplied.actions,
        evidence=citations,
        safety_notes=supplied.safety_notes,
    )

    async def patch_work_order_field(
        self,
        episode_id: str,
        version: int,
        request: WorkOrderFieldPatchRequest,
    ) -> IncidentDocumentResponse:
        async with self.engine.begin() as connection:
            payload_hash = request_hash(
                "patch-work-order-field",
                episode_id,
                "work_order",
                request.model_dump(mode="json"),
            )
            scope = operation_scope("patch-work-order-field", episode_id, "work_order")
            existing_id = await begin_idempotent_operation(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
            )
            if existing_id is not None:
                return await response_from_row(connection, await document_by_id(connection, existing_id))
            current = await latest_version(connection, episode_id, "work_order")
            if current is None or int(current["version"]) != version:
                raise IncidentDocumentConflictError("document version is no longer current")
            if version != request.expected_version:
                raise IncidentDocumentConflictError("expected document version is stale")
            content = content_from_row(current)
            if not isinstance(content, WorkOrderStructuredContent):
                raise IncidentDocumentConflictError(
                    "only structured work orders support field-level patches"
                )
            try:
                next_content = apply_work_order_patch(content, request)
            except WorkOrderPatchError as exc:
                raise IncidentDocumentConflictError(str(exc)) from exc
            row = await insert_version(
                connection,
                episode_id=episode_id,
                document_type="work_order",
                version=version + 1,
                parent_document_version_id=str(current["document_version_id"]),
                status="draft",
                content=next_content,
                actor=request.edited_by,
            )
            await insert_review(
                connection,
                document_version_id=str(row["document_version_id"]),
                review_type="operator_note",
                decision="pending",
                note=(
                    f"필드 수정: {request.target_section}[{request.target_seq}]."
                    f"{request.target_field} = {request.new_value}"
                ),
                actor=request.edited_by,
                evidence=(),
            )
            await complete_idempotency(
                connection,
                operation_scope=scope,
                idempotency_key=request.idempotency_key,
                request_hash=payload_hash,
                document_version_id=str(row["document_version_id"]),
            )
            return await response_from_row(connection, row)
