from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING
from uuid import UUID

import orjson
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_execution_repository import AGENT_GRAPH_TASK_KEY_V2
from agent_operator_review_repository import (
    IdempotencyConflictError,
    StaleReviewVersionError,
)
from agent_rerun_repository import TargetedChildRun, mark_rerun_scheduled
from incident_document_repository import PostgresIncidentDocumentRepository
from incident_document_routes import make_incident_document_router

if TYPE_CHECKING:
    from settings import Settings
    from heatgrid_ops.agent.graph import AgentGraphInvoker
    from heatgrid_ops.agent.services import AgentRuntime
from review_chat_api_models import (
    ReviewChatCancelRequest,
    ReviewChatConfirmRequest,
    ReviewChatConfirmationResponse,
    ReviewChatMessagePage,
    ReviewChatMessageRequest,
    ReviewChatOpenRequest,
    ReviewChatProposalPage,
    ReviewChatSubmissionResponse,
    ReviewChatThreadResponse,
)
from review_chat_service import (
    ReviewChatConflictError,
    ReviewChatNotFoundError,
    cancel_review_chat_proposal,
    confirm_review_chat_proposal,
    list_review_chat_events,
    list_review_chat_messages,
    list_pending_review_chat_proposals,
    open_review_chat,
    submit_review_chat_message,
)


def make_review_chat_router(
    engine: AsyncEngine,
    settings: "Settings | None" = None,
    runtime: "AgentRuntime | None" = None,
    graph_provider: Callable[[], "AgentGraphInvoker | None"] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    if settings is None:
        from settings import Settings

        settings = Settings()
    active_settings = settings
    active_runtime = runtime
    router.include_router(
        make_incident_document_router(
            PostgresIncidentDocumentRepository(engine),
            settings=active_settings,
            prefix="",
        )
    )

    def _runtime() -> "AgentRuntime":
        nonlocal active_runtime
        if active_runtime is None:
            from agent_runtime_factory import create_agent_runtime

            active_runtime = create_agent_runtime(active_settings, engine)
        return active_runtime

    def schedule_child(child: TargetedChildRun) -> None:
        from agent_runner import schedule_reserved_agent_graph
        from heatgrid_ops.agent.contracts import AgentRunRequest

        schedule_reserved_agent_graph(
            engine,
            AgentRunRequest(
                run_id=child.run_id,
                alert_id=child.alert_id,
                card_id=child.card_id,
            ),
            runtime=_runtime(),
            graph=None if graph_provider is None else graph_provider(),
            task_key=AGENT_GRAPH_TASK_KEY_V2,
        )

    @router.post(
        "/agent-runs/{run_id}/review-chat/threads",
        response_model=ReviewChatThreadResponse,
    )
    async def open_thread(
        run_id: UUID,
        request: ReviewChatOpenRequest,
    ) -> ReviewChatThreadResponse:
        return await _map_errors(open_review_chat(engine, str(run_id), request))

    @router.get(
        "/review-chat/threads/{thread_id}/messages",
        response_model=ReviewChatMessagePage,
    )
    async def messages(
        thread_id: UUID,
        after_sequence: int = Query(default=0, ge=0),
        before_sequence: int | None = Query(default=None, ge=1),
        limit: int = Query(default=100, ge=1, le=100),
    ) -> ReviewChatMessagePage:
        return await _map_errors(
            list_review_chat_messages(
                engine,
                str(thread_id),
                after_sequence=after_sequence,
                before_sequence=before_sequence,
                limit=limit,
            )
        )

    @router.get(
        "/review-chat/threads/{thread_id}/proposals/pending",
        response_model=ReviewChatProposalPage,
    )
    async def pending_proposals(thread_id: UUID) -> ReviewChatProposalPage:
        return await _map_errors(
            list_pending_review_chat_proposals(engine, str(thread_id))
        )

    @router.post(
        "/review-chat/threads/{thread_id}/messages",
        response_model=ReviewChatSubmissionResponse,
        status_code=202,
    )
    async def submit_message(
        thread_id: UUID,
        request: ReviewChatMessageRequest,
    ) -> ReviewChatSubmissionResponse:
        key = active_settings.openai_api_key
        return await _map_errors(
            submit_review_chat_message(
                engine,
                str(thread_id),
                request,
                api_key=None if key is None else key.get_secret_value(),
                model=active_settings.natural_chat_model,
            )
        )

    @router.get("/review-chat/threads/{thread_id}/events")
    async def events(
        thread_id: UUID,
        after_event_id: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            records = await _map_errors(
                list_review_chat_events(
                    engine,
                    str(thread_id),
                    after_event_id=after_event_id,
                )
            )
            for record in records:
                yield (
                    f"id: {record['event_id']}\n"
                    f"event: {record['event_type']}\n"
                    f"data: {orjson.dumps(record['payload']).decode('utf-8')}\n\n"
                )
            yield ": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.post(
        "/review-chat/proposals/{proposal_id}/confirm",
        response_model=ReviewChatConfirmationResponse,
    )
    async def confirm(
        proposal_id: UUID,
        request: ReviewChatConfirmRequest,
    ) -> ReviewChatConfirmationResponse:
        result, child = await _map_errors(
            confirm_review_chat_proposal(
                engine,
                str(proposal_id),
                request,
                rag_quality_enabled=active_settings.rag_quality_enabled,
            )
        )
        if child is not None:
            try:
                schedule_child(child)
            except Exception:  # The review is already committed; scheduling is retryable.
                try:
                    await mark_rerun_scheduled(engine, child, scheduled=False)
                except Exception:
                    pass
                result = result.model_copy(update={"rerun_status": "schedule_failed"})
            else:
                try:
                    await mark_rerun_scheduled(engine, child, scheduled=True)
                except Exception:
                    result = result.model_copy(update={"rerun_status": "schedule_failed"})
                else:
                    result = result.model_copy(update={"rerun_status": "scheduled"})
        return result

    @router.post(
        "/review-chat/proposals/{proposal_id}/cancel",
        response_model=ReviewChatConfirmationResponse,
    )
    async def cancel(
        proposal_id: UUID,
        request: ReviewChatCancelRequest,
    ) -> ReviewChatConfirmationResponse:
        return await _map_errors(cancel_review_chat_proposal(engine, str(proposal_id), request))

    return router


async def _map_errors(awaitable):
    try:
        return await awaitable
    except ReviewChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        IdempotencyConflictError,
        ReviewChatConflictError,
        StaleReviewVersionError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
