from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from incident_document_api_models import (
    DocumentType,
    IncidentDocumentApproveRequest,
    IncidentDocumentEditRequest,
    IncidentDocumentGenerateRequest,
    IncidentDocumentPage,
    IncidentDocumentResponse,
    WorkOrderFieldPatchRequest,
    WorkOrderStructuredContent,
)
from incident_document_repository import (
    IncidentDocumentRepository,
)
from incident_document_repository_errors import (
    IncidentDocumentConflictError,
    IncidentDocumentNotFoundError,
    InvalidIncidentCitationError,
)
from work_order_xlsx import render_work_order_xlsx

if TYPE_CHECKING:
    from settings import Settings


def make_incident_document_router(
    repository: IncidentDocumentRepository,
    *,
    settings: "Settings",
    prefix: str = "/api",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["incident-documents"])

    @router.post(
        "/incidents/{episode_id}/documents/{document_type}/generate",
        response_model=IncidentDocumentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def generate_document(
        episode_id: UUID,
        document_type: DocumentType,
        request: IncidentDocumentGenerateRequest,
        response: Response,
    ) -> IncidentDocumentResponse:
        document = await _map_errors(
            repository.generate_document(
                str(episode_id),
                document_type,
                request,
                model_available=settings.openai_api_key is not None,
            )
        )
        if document.status == "failed" and document.retryable:
            response.status_code = status.HTTP_202_ACCEPTED
        return document

    @router.get(
        "/incidents/{episode_id}/documents",
        response_model=IncidentDocumentPage,
    )
    async def list_documents(episode_id: UUID) -> IncidentDocumentPage:
        return await _map_errors(repository.list_documents(str(episode_id)))

    @router.get("/incidents/{episode_id}/documents/work_order/versions/{version}/xlsx")
    async def download_work_order_xlsx(episode_id: UUID, version: int) -> Response:
        documents = await _map_errors(repository.list_documents(str(episode_id)))
        document = next(
            (
                item
                for item in documents.items
                if item.document_type == "work_order" and item.version == version
            ),
            None,
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="work order version was not found")
        if not isinstance(document.content, WorkOrderStructuredContent):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="structured work order is required")
        file_name = f"heatgrid-work-order-{document.content.header.document_number}-v{version}.xlsx"
        return Response(
            content=render_work_order_xlsx(
                document.content,
                status_label={
                    "draft": "검토 중",
                    "ai_reviewed": "AI 검토 완료",
                    "approved": "최종 승인",
                    "failed": "생성 실패",
                }.get(document.status, document.content.header.status),
            ),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=\"{file_name}\""},
        )

    @router.put(
        "/incidents/{episode_id}/documents/{document_type}/versions/{version}",
        response_model=IncidentDocumentResponse,
    )
    async def edit_document(
        episode_id: UUID,
        document_type: DocumentType,
        version: int,
        request: IncidentDocumentEditRequest,
    ) -> IncidentDocumentResponse:
        return await _map_errors(
            repository.edit_document(str(episode_id), document_type, version, request)
        )

    @router.patch(
        "/incidents/{episode_id}/documents/work_order/versions/{version}/field",
        response_model=IncidentDocumentResponse,
    )
    async def patch_work_order_field(
        episode_id: UUID,
        version: int,
        request: WorkOrderFieldPatchRequest,
    ) -> IncidentDocumentResponse:
        return await _map_errors(
            repository.patch_work_order_field(str(episode_id), version, request)
        )

    @router.post(
        "/incidents/{episode_id}/documents/{document_type}/approve",
        response_model=IncidentDocumentResponse,
    )
    async def approve_document(
        episode_id: UUID,
        document_type: DocumentType,
        request: IncidentDocumentApproveRequest,
    ) -> IncidentDocumentResponse:
        return await _map_errors(
            repository.approve_document(str(episode_id), document_type, request)
        )

    return router


async def _map_errors(awaitable):
    try:
        return await awaitable
    except IncidentDocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IncidentDocumentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidIncidentCitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
