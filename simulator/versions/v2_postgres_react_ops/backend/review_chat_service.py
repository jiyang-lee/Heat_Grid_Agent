from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import re
from typing import Literal, cast
from uuid import uuid4

import orjson
from openai import AsyncOpenAI, OpenAIError
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_operator_review_repository import ReviewRecordInput, record_review
from agent_rerun_policy import TARGET_STAGE_BY_REASON
from agent_rerun_repository import TargetedChildRun, create_targeted_child_run
from review_chat_api_models import (
    ReviewChatCancelRequest,
    ReviewChatConfirmationResponse,
    ReviewChatConfirmRequest,
    ReviewChatDocumentContext,
    ReviewChatMessagePage,
    ReviewChatMessageRequest,
    ReviewChatMessageResponse,
    ReviewChatOpenRequest,
    ReviewChatProposalResponse,
    ReviewChatSubmissionResponse,
    ReviewChatThreadResponse,
)


PROMPT_VERSION = "review-chat.v1"
PROPOSAL_TTL = timedelta(minutes=15)


class ReviewChatNotFoundError(RuntimeError):
    def __str__(self) -> str:
        return "review chat resource was not found"


class ReviewChatConflictError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ReviewChatContext:
    run_id: str
    review_version: int
    context_hash: str
    output: dict[str, object]
    citations: tuple[dict[str, str], ...]
    review_snapshot_hash: str | None


@dataclass(frozen=True, slots=True)
class ParsedAction:
    kind: Literal["explain", "clarify", "proposal"]
    decision: Literal["approve", "reject", "correct", "keep_human_review"] | None
    reason: str
    reason_category: str | None
    next_action: Literal[
        "none", "targeted_rerun", "manual_investigation", "close_without_rerun"
    ]
    disposition: str | None
    correction: dict[str, str] | None
    confidence: float


async def open_review_chat(
    engine: AsyncEngine,
    run_id: str,
    request: ReviewChatOpenRequest,
) -> ReviewChatThreadResponse:
    async with engine.begin() as connection:
        context = await _context_for_run(connection, run_id)
        existing = await connection.execute(
            text(
                "SELECT thread_id, run_id, status, context_hash, base_review_version, created_at "
                "FROM review_chat_threads WHERE run_id = :run_id AND status = 'open'"
            ),
            {"run_id": run_id},
        )
        row = existing.mappings().one_or_none()
        if row is not None:
            return _thread_from_row(row)
        inserted = await connection.execute(
            text(
                "INSERT INTO review_chat_threads ("
                "thread_id, run_id, status, created_by, base_review_version, "
                "base_review_snapshot_hash, base_output_hash, context_hash, prompt_version"
                ") VALUES ("
                ":thread_id, :run_id, 'open', :created_by, :review_version, "
                ":snapshot_hash, :output_hash, :context_hash, :prompt_version"
                ") RETURNING thread_id, run_id, status, context_hash, base_review_version, created_at"
            ),
            {
                "thread_id": str(uuid4()),
                "run_id": run_id,
                "created_by": request.created_by,
                "review_version": context.review_version,
                "snapshot_hash": context.review_snapshot_hash,
                "output_hash": _hash(context.output),
                "context_hash": context.context_hash,
                "prompt_version": PROMPT_VERSION,
            },
        )
        row = inserted.mappings().one()
        await _event(
            connection,
            str(row["thread_id"]),
            "thread.opened",
            {"run_id": run_id, "created_by": request.created_by},
            f"review-chat-open:{run_id}",
        )
        return _thread_from_row(row)


async def list_review_chat_messages(
    engine: AsyncEngine,
    thread_id: str,
    *,
    after_sequence: int,
    limit: int,
) -> ReviewChatMessagePage:
    async with engine.connect() as connection:
        if not await _thread_exists(connection, thread_id):
            raise ReviewChatNotFoundError()
        result = await connection.execute(
            text(
                "SELECT " + _message_columns() + " FROM review_chat_messages "
                "WHERE thread_id = :thread_id AND sequence > :after_sequence "
                "ORDER BY sequence LIMIT :limit"
            ),
            {"thread_id": thread_id, "after_sequence": after_sequence, "limit": limit},
        )
    return ReviewChatMessagePage(items=tuple(_message_from_row(row) for row in result.mappings().all()))


async def submit_review_chat_message(
    engine: AsyncEngine,
    thread_id: str,
    request: ReviewChatMessageRequest,
    *,
    api_key: str | None = None,
    model: str = "gpt-5.4-mini",
) -> ReviewChatSubmissionResponse:
    async with engine.begin() as connection:
        thread = await _locked_thread(connection, thread_id)
        context = await _context_for_run(connection, str(thread["run_id"]))
        await _refresh_context(connection, thread, context)
        _validate_message_citations(context, request.incident_id, request.citation_ids)
        document_context = await _canonical_document_context(connection, context, request)
        existing = await _message_by_idempotency(connection, thread_id, request.idempotency_key)
        if existing is not None:
            expected_hash = _hash(
                {
                    "role": "operator",
                    "kind": "action_request" if _looks_like_action(request.content) else "question",
                    "content": request.content,
                    "payload": _message_payload(request, document_context),
                    "context_hash": context.context_hash,
                }
            )
            if await _message_hash_by_idempotency(connection, thread_id, request.idempotency_key) != expected_hash:
                raise ReviewChatConflictError("idempotency key was already used with a different message")
            return await _existing_submission(connection, existing)
        operator = await _append_message(
            connection,
            thread_id=thread_id,
            role="operator",
            message_kind="action_request" if _looks_like_action(request.content) else "question",
            content=request.content,
            structured_payload=_message_payload(request, document_context),
            citations=_message_citations(context, request, document_context),
            context_hash=context.context_hash,
            created_by=request.created_by,
            idempotency_key=request.idempotency_key,
        )
        await _event(
            connection,
            thread_id,
            "message.accepted",
            {"message_id": operator.message_id, "sequence": operator.sequence},
            f"review-chat-message:{thread_id}:{request.idempotency_key}",
        )
        parsed = parse_review_chat_intent(request.content, document_context)
        proposal: ReviewChatProposalResponse | None = None
        if parsed.kind == "proposal":
            proposal = await _create_proposal(connection, thread_id, operator, context, parsed)
            assistant = await _append_message(
                connection,
                thread_id=thread_id,
                role="assistant",
                message_kind="action_proposal",
                content=_proposal_message(parsed),
                structured_payload={"proposal_id": proposal.proposal_id},
                citations=context.citations,
                context_hash=context.context_hash,
                created_by=None,
                idempotency_key=None,
            )
        else:
            fallback = _clarification_message(parsed, context)
            assistant = await _append_message(
                connection,
                thread_id=thread_id,
                role="assistant",
                message_kind="explanation",
                content=await _natural_language_reply(
                    api_key=api_key,
                    model=model,
                    question=request.content,
                    context=context,
                    fallback=fallback,
                ),
                structured_payload={"mode": parsed.kind},
                citations=context.citations,
                context_hash=context.context_hash,
                created_by=None,
                idempotency_key=None,
            )
        await _event(
            connection,
            thread_id,
            "assistant.completed",
            {"message_id": assistant.message_id, "proposal_id": None if proposal is None else proposal.proposal_id},
            f"review-chat-assistant:{operator.message_id}",
        )
        return ReviewChatSubmissionResponse(
            operator_message=operator,
            assistant_message=assistant,
            proposal=proposal,
        )


async def _natural_language_reply(
    *,
    api_key: str | None,
    model: str,
    question: str,
    context: ReviewChatContext,
    fallback: str,
) -> str:
    if api_key is None:
        return _plain_chat_text(fallback)
    prompt = orjson.dumps(
        {
            "question": question,
            "ops_output": context.output,
            "citations": context.citations,
        }
    ).decode("utf-8")
    try:
        async with AsyncOpenAI(api_key=api_key) as client:
            response = await client.responses.create(
                model=model,
                input=(
                    "Answer in Korean using only the supplied operational context. "
                    "Do not approve, reject, or execute an action; explain the evidence and "
                    "tell the operator when confirmation is required. Use plain text only. "
                    "Do not use Markdown, asterisks, underscores, backticks, or headings.\n\n"
                    + prompt
                ),
            )
    except OpenAIError:
        return _plain_chat_text(fallback)
    reply = _plain_chat_text(response.output_text)
    return reply or _plain_chat_text(fallback)


async def confirm_review_chat_proposal(
    engine: AsyncEngine,
    proposal_id: str,
    request: ReviewChatConfirmRequest,
    *,
    rag_quality_enabled: bool,
) -> tuple[ReviewChatConfirmationResponse, TargetedChildRun | None]:
    async with engine.begin() as connection:
        proposal = await _locked_proposal(connection, proposal_id)
        if str(proposal["status"]) == "executed":
            return _confirmation_from_row(proposal), None
        if str(proposal["status"]) != request.expected_proposal_status:
            raise ReviewChatConflictError("proposal status is no longer confirmable")
        context = await _context_for_run(connection, str(proposal["run_id"]))
        if (
            context.context_hash != str(proposal["context_hash"])
            or context.review_version != request.expected_review_version
            or context.review_version != int(proposal["expected_review_version"])
        ):
            await _set_proposal_status(connection, proposal_id, "stale")
            await _event(
                connection,
                str(proposal["thread_id"]),
                "proposal.stale",
                {"proposal_id": proposal_id, "context_hash": context.context_hash},
                f"review-chat-stale:{proposal_id}:{context.context_hash}",
            )
            raise ReviewChatConflictError("proposal context or review version is stale")
        if proposal["expires_at"] <= datetime.now(UTC):
            await _set_proposal_status(connection, proposal_id, "expired")
            raise ReviewChatConflictError("proposal has expired")
        await _set_proposal_status(connection, proposal_id, "executing")
        review = await record_review(
            connection,
            ReviewRecordInput(
                run_id=str(proposal["run_id"]),
                review_task_id=None,
                subject_type="agent_run",
                subject_key=str(proposal["run_id"]),
                decision=proposal["decision"],
                reviewer=request.confirmed_by,
                reason=str(proposal["reason"]),
                reason_category=proposal["reason_category"],
                next_action=proposal["next_action"],
                idempotency_key=f"review-chat-confirm:{proposal_id}:{request.idempotency_key}",
                request_hash=_hash(
                    {
                        "proposal_id": proposal_id,
                        "confirmed_by": request.confirmed_by,
                        "idempotency_key": request.idempotency_key,
                    }
                ),
                disposition=proposal["disposition"],
                correction=_string_object(proposal["correction"]),
                evidence_annotations=(),
                operator_labels=("review_chat",),
                expected_review_version=request.expected_review_version,
            ),
        )
        child = None
        if proposal["next_action"] == "targeted_rerun":
            child = await create_targeted_child_run(
                connection,
                review=review,
                rag_quality_enabled=rag_quality_enabled,
            )
        await connection.execute(
            text(
                "UPDATE review_chat_action_proposals SET status = 'executed', confirmed_by = :confirmed_by, "
                "confirmed_at = now(), executed_review_id = :review_id, child_run_id = :child_run_id, "
                "updated_at = now() WHERE proposal_id = :proposal_id"
            ),
            {
                "proposal_id": proposal_id,
                "confirmed_by": request.confirmed_by,
                "review_id": review.review_id,
                "child_run_id": None if child is None else child.run_id,
            },
        )
        await _append_message(
            connection,
            thread_id=str(proposal["thread_id"]),
            role="system_event",
            message_kind="execution_result",
            content="검토 결정을 저장했습니다.",
            structured_payload={"proposal_id": proposal_id, "review_id": review.review_id},
            citations=(),
            context_hash=context.context_hash,
            created_by=request.confirmed_by,
            idempotency_key=f"review-chat-confirm-message:{proposal_id}:{request.idempotency_key}",
        )
        await _event(
            connection,
            str(proposal["thread_id"]),
            "review.executed",
            {"proposal_id": proposal_id, "review_id": review.review_id, "child_run_id": None if child is None else child.run_id},
            f"review-chat-confirm:{proposal_id}:{request.idempotency_key}",
        )
        return (
            ReviewChatConfirmationResponse(
                proposal_id=proposal_id,
                status="executed",
                review_id=review.review_id,
                child_run_id=None if child is None else child.run_id,
                target_stage=None if child is None else child.target_stage,
            ),
            child,
        )


async def cancel_review_chat_proposal(
    engine: AsyncEngine,
    proposal_id: str,
    request: ReviewChatCancelRequest,
) -> ReviewChatConfirmationResponse:
    async with engine.begin() as connection:
        proposal = await _locked_proposal(connection, proposal_id)
        if str(proposal["status"]) == "cancelled":
            return _confirmation_from_row(proposal)
        if str(proposal["status"]) != "awaiting_confirmation":
            raise ReviewChatConflictError("proposal is no longer cancellable")
        await _set_proposal_status(connection, proposal_id, "cancelled")
        await _event(
            connection,
            str(proposal["thread_id"]),
            "proposal.cancelled",
            {"proposal_id": proposal_id, "cancelled_by": request.cancelled_by},
            f"review-chat-cancel:{proposal_id}:{request.idempotency_key}",
        )
        return ReviewChatConfirmationResponse(proposal_id=proposal_id, status="cancelled")


async def list_review_chat_events(
    engine: AsyncEngine,
    thread_id: str,
    *,
    after_event_id: int,
) -> tuple[dict[str, object], ...]:
    async with engine.connect() as connection:
        if not await _thread_exists(connection, thread_id):
            raise ReviewChatNotFoundError()
        result = await connection.execute(
            text(
                "SELECT event_id, event_type, CAST(payload AS text) AS payload, created_at "
                "FROM review_chat_events WHERE thread_id = :thread_id "
                "AND event_id > :after_event_id ORDER BY event_id"
            ),
            {"thread_id": thread_id, "after_event_id": after_event_id},
        )
    return tuple(
        {
            "event_id": int(row["event_id"]),
            "event_type": str(row["event_type"]),
            "payload": orjson.loads(row["payload"]),
            "created_at": row["created_at"].isoformat(),
        }
        for row in result.mappings().all()
    )


def parse_review_chat_intent(
    content: str,
    document_context: dict[str, str] | None = None,
) -> ParsedAction:
    normalized = " ".join(content.casefold().split())
    injection = any(token in normalized for token in ("ignore previous", "system prompt", "도구 호출", "api key"))
    decisions = [
        decision
        for decision, tokens in {
            "approve": ("승인", "approve"),
            "reject": ("거절", "reject"),
            "correct": ("교정", "수정", "고쳐", "보강", "추가", "반영", "재작성", "다시 작성", "변경", "삭제", "correct"),
            "keep_human_review": ("보류", "더 볼", "계속 검토"),
        }.items()
        if any(token in normalized for token in tokens)
    ]
    if injection or len(decisions) > 1:
        return ParsedAction("clarify", None, "", None, "none", None, None, 0.0)
    if not decisions and _is_work_order_change_request(normalized, document_context):
        decisions.append("correct")
    if not decisions:
        return ParsedAction("explain", None, "", None, "none", None, None, 1.0)
    decision = cast(
        Literal["approve", "reject", "correct", "keep_human_review"],
        decisions[0],
    )
    category = _reason_category(normalized)
    if decision == "correct" and category is None and document_context is not None and document_context.get("document_type") == "work_order":
        category = "report_draft_issue"
    reason = _reason_from_content(content, decision)
    if decision == "reject" and category == "report_draft_issue":
        return ParsedAction("clarify", None, "", None, "none", None, None, 0.0)
    if decision == "reject" and (not reason or category is None):
        return ParsedAction("clarify", None, "", None, "none", None, None, 0.0)
    next_action: Literal[
        "none", "targeted_rerun", "manual_investigation", "close_without_rerun"
    ] = "none"
    if decision in {"reject", "correct"} and category in TARGET_STAGE_BY_REASON:
        next_action = "targeted_rerun"
    disposition = "inspection_recommended" if decision == "correct" else None
    correction = None
    if decision == "correct":
        correction = {"disposition": disposition or "inspection_recommended", "instruction": content}
        if document_context is not None:
            current_body = document_context.get("current_body", "")
            correction.update({
                "incident_id": document_context.get("incident_id", ""),
                "document_version_id": document_context.get("document_version_id", ""),
                "document_type": document_context.get("document_type", "work_order"),
                "base_version": document_context.get("base_version", "1"),
                "content_hash": document_context.get("content_hash", _hash(current_body)),
                "base_content_hash": document_context.get("base_content_hash", _hash(current_body)),
                "current_body": current_body,
                "target_area": "risk_evidence" if any(token in normalized for token in ("위험", "근거")) else "document_body",
            })
    return ParsedAction("proposal", decision, reason or "operator review", category, next_action, disposition, correction, 0.9)


async def _context_for_run(connection: AsyncConnection, run_id: str) -> ReviewChatContext:
    result = await connection.execute(
        text(
            "SELECT run_id, CAST(COALESCE(ops_output, '{}'::jsonb) AS text) AS ops_output, "
            "(SELECT snapshot_hash FROM agent_run_review_snapshots WHERE run_id = agent_runs.run_id) "
            "AS review_snapshot_hash FROM agent_runs WHERE run_id = :run_id"
        ),
        {"run_id": run_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ReviewChatNotFoundError()
    reviews = await connection.execute(
        text("SELECT COALESCE(max(review_version), 0) FROM agent_run_reviews WHERE run_id = :run_id"),
        {"run_id": run_id},
    )
    stages = await connection.execute(
        text(
            "SELECT stage_snapshot_id, stage_name, output_hash FROM agent_stage_snapshots "
            "WHERE run_id = :run_id ORDER BY stage_name, attempt"
        ),
        {"run_id": run_id},
    )
    citations = tuple(
        {
            "citation_id": f"stage:{item['stage_snapshot_id']}",
            "stage_snapshot_id": str(item["stage_snapshot_id"]),
            "stage_name": str(item["stage_name"]),
            "snapshot_hash": str(item["output_hash"]),
        }
        for item in stages.mappings().all()
    )
    incident_citations = await _incident_citations_for_run(connection, run_id)
    citations = citations + incident_citations
    output = _json_object(row["ops_output"])
    review_version = int(reviews.scalar_one())
    context_hash = _hash(
        {
            "run_id": run_id,
            "final_output_hash": _hash(output),
            "review_snapshot_hash": row["review_snapshot_hash"],
            "ordered_stage_snapshot_hashes": [item["snapshot_hash"] for item in citations],
            "review_version": review_version,
        }
    )
    return ReviewChatContext(
        run_id=run_id,
        review_version=review_version,
        context_hash=context_hash,
        output=output,
        citations=citations,
        review_snapshot_hash=None if row["review_snapshot_hash"] is None else str(row["review_snapshot_hash"]),
    )


async def _incident_citations_for_run(
    connection: AsyncConnection,
    run_id: str,
) -> tuple[dict[str, str], ...]:
    schema_ready = await connection.scalar(
        text(
            "SELECT to_regclass('public.anomaly_episodes') IS NOT NULL "
            "AND EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'ops_alert_queue' "
            "AND column_name = 'episode_id'"
            ")"
        )
    )
    if schema_ready is not True:
        return ()
    result = await connection.execute(
        text(
            "SELECT e.episode_id::text AS episode_id, q.alert_id::text AS alert_id "
            "FROM agent_runs r JOIN ops_alert_queue q ON q.alert_id = r.alert_id "
            "JOIN anomaly_episodes e ON e.episode_id = q.episode_id "
            "WHERE r.run_id = :run_id"
        ),
        {"run_id": run_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return ()
    episode_id = str(row["episode_id"])
    alert_id = str(row["alert_id"])
    document_result = await connection.execute(
        text(
            "SELECT document_version_id::text AS document_version_id, document_type, "
            "version, content_hash FROM incident_document_versions "
            "WHERE episode_id = :episode_id ORDER BY document_type, version"
        ),
        {"episode_id": episode_id},
    )
    documents = tuple(
        {
            "citation_id": f"document:{item['document_version_id']}",
            "document_version_id": str(item["document_version_id"]),
            "document_type": str(item["document_type"]),
            "version": str(item["version"]),
            "snapshot_hash": str(item["content_hash"]),
            "content_hash": str(item["content_hash"]),
        }
        for item in document_result.mappings().all()
    )
    return (
        {
            "citation_id": f"episode:{episode_id}",
            "episode_id": episode_id,
            "alert_id": alert_id,
            "snapshot_hash": _hash({"episode_id": episode_id, "alert_id": alert_id}),
        },
        {
            "citation_id": f"alert:{alert_id}",
            "alert_id": alert_id,
            "snapshot_hash": _hash({"alert_id": alert_id}),
        },
    ) + documents


def _validate_message_citations(
    context: ReviewChatContext,
    incident_id: str | None,
    citation_ids: tuple[str, ...],
) -> None:
    if incident_id is None and not citation_ids:
        return
    allowed = {
        item["citation_id"]
        for item in context.citations
        if "citation_id" in item
    }
    if incident_id is not None and f"episode:{incident_id}" not in allowed:
        raise ReviewChatConflictError("incident context does not belong to this thread")
    for citation_id in citation_ids:
        if citation_id not in allowed:
            raise ReviewChatConflictError(f"unsupported citation id: {citation_id}")


async def _canonical_document_context(
    connection: AsyncConnection,
    context: ReviewChatContext,
    request: ReviewChatMessageRequest,
) -> dict[str, str] | None:
    document_context = request.document_context
    if document_context is None:
        return None
    row = await _document_context_row(connection, context, request.incident_id, document_context)
    document_version_id = str(row["document_version_id"])
    if f"document:{document_version_id}" not in _allowed_citation_ids(context):
        raise ReviewChatConflictError("document context does not belong to this thread")
    version = int(row["version"])
    if version != document_context.expected_version:
        raise ReviewChatConflictError("document version is stale")
    latest = await connection.scalar(
        text(
            "SELECT COALESCE(max(version), 0) FROM incident_document_versions "
            "WHERE episode_id = :episode_id AND document_type = :document_type"
        ),
        {"episode_id": row["episode_id"], "document_type": row["document_type"]},
    )
    if int(latest or 0) != version:
        raise ReviewChatConflictError("document version is stale")
    content = _json_object(row["content"])
    body = content.get("body")
    if not isinstance(body, str):
        raise ReviewChatConflictError("document content is malformed")
    content_hash = str(row["content_hash"])
    return {
        "incident_id": str(row["episode_id"]),
        "document_version_id": document_version_id,
        "document_type": str(row["document_type"]),
        "base_version": str(version),
        "expected_version": str(document_context.expected_version),
        "base_content_hash": content_hash,
        "content_hash": content_hash,
        "current_body": body,
    }


async def _document_context_row(
    connection: AsyncConnection,
    context: ReviewChatContext,
    incident_id: str | None,
    document_context: ReviewChatDocumentContext,
) -> RowMapping:
    if document_context.document_version_id is not None:
        result = await connection.execute(
            text(
                "SELECT document_version_id::text AS document_version_id, episode_id::text AS episode_id, "
                "document_type, version, CAST(content AS text) AS content, content_hash "
                "FROM incident_document_versions WHERE document_version_id = :document_version_id"
            ),
            {"document_version_id": document_context.document_version_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ReviewChatNotFoundError()
        return row
    episode_id = _document_episode_id(context, incident_id)
    result = await connection.execute(
        text(
            "SELECT document_version_id::text AS document_version_id, episode_id::text AS episode_id, "
            "document_type, version, CAST(content AS text) AS content, content_hash "
            "FROM incident_document_versions "
            "WHERE episode_id = :episode_id AND document_type = :document_type "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"episode_id": episode_id, "document_type": document_context.document_type},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ReviewChatNotFoundError()
    return row


def _document_episode_id(context: ReviewChatContext, incident_id: str | None) -> str:
    if incident_id is not None:
        return incident_id
    episode_ids = {
        item["episode_id"]
        for item in context.citations
        if item.get("citation_id", "").startswith("episode:") and "episode_id" in item
    }
    if len(episode_ids) != 1:
        raise ReviewChatConflictError("incident context is required for document lookup")
    return next(iter(episode_ids))


def _allowed_citation_ids(context: ReviewChatContext) -> set[str]:
    return {item["citation_id"] for item in context.citations if "citation_id" in item}


def _message_citations(
    context: ReviewChatContext,
    request: ReviewChatMessageRequest,
    document_context: dict[str, str] | None,
) -> tuple[dict[str, str], ...]:
    wanted = set(request.citation_ids)
    if request.incident_id is not None:
        wanted.add(f"episode:{request.incident_id}")
    if document_context is not None:
        wanted.add(f"document:{document_context['document_version_id']}")
    return tuple(item for item in context.citations if item.get("citation_id") in wanted)


def _message_payload(
    request: ReviewChatMessageRequest,
    document_context: dict[str, str] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if document_context is not None:
        payload["document_context"] = document_context
    if request.incident_id is not None:
        payload["incident_id"] = request.incident_id
    if request.citation_ids:
        payload["citation_ids"] = request.citation_ids
    return payload


async def _refresh_context(
    connection: AsyncConnection,
    thread: RowMapping,
    context: ReviewChatContext,
) -> None:
    if str(thread["context_hash"]) == context.context_hash:
        return
    await connection.execute(
        text(
            "UPDATE review_chat_threads SET context_hash = :context_hash, updated_at = now() "
            "WHERE thread_id = :thread_id"
        ),
        {"thread_id": thread["thread_id"], "context_hash": context.context_hash},
    )
    await connection.execute(
        text(
            "UPDATE review_chat_action_proposals SET status = 'stale', updated_at = now() "
            "WHERE thread_id = :thread_id AND status = 'awaiting_confirmation'"
        ),
        {"thread_id": thread["thread_id"]},
    )
    await _event(
        connection,
        str(thread["thread_id"]),
        "proposal.stale",
        {"context_hash": context.context_hash},
        f"review-chat-context:{thread['thread_id']}:{context.context_hash}",
    )


async def _create_proposal(
    connection: AsyncConnection,
    thread_id: str,
    operator: ReviewChatMessageResponse,
    context: ReviewChatContext,
    parsed: ParsedAction,
) -> ReviewChatProposalResponse:
    assert parsed.decision is not None
    proposal_id = str(uuid4())
    expires_at = datetime.now(UTC) + PROPOSAL_TTL
    proposal_hash = _hash(
        {
            "thread_id": thread_id,
            "source_message_id": operator.message_id,
            "context_hash": context.context_hash,
            "decision": parsed.decision,
            "next_action": parsed.next_action,
            "reason": parsed.reason,
            "reason_category": parsed.reason_category,
            "correction": parsed.correction,
        }
    )
    await connection.execute(
        text(
            "INSERT INTO review_chat_action_proposals ("
            "proposal_id, thread_id, source_message_id, run_id, expected_review_version, "
            "context_hash, proposal_hash, status, decision, next_action, reason, reason_category, "
            "disposition, correction, parser_confidence, expires_at"
            ") VALUES ("
            ":proposal_id, :thread_id, :source_message_id, :run_id, :review_version, "
            ":context_hash, :proposal_hash, 'awaiting_confirmation', :decision, :next_action, "
            ":reason, :reason_category, :disposition, CAST(:correction AS jsonb), "
            ":confidence, :expires_at)"
        ),
        {
            "proposal_id": proposal_id,
            "thread_id": thread_id,
            "source_message_id": operator.message_id,
            "run_id": context.run_id,
            "review_version": context.review_version,
            "context_hash": context.context_hash,
            "proposal_hash": proposal_hash,
            "decision": parsed.decision,
            "next_action": parsed.next_action,
            "reason": parsed.reason,
            "reason_category": parsed.reason_category,
            "disposition": parsed.disposition,
            "correction": None if parsed.correction is None else _dump(parsed.correction),
            "confidence": parsed.confidence,
            "expires_at": expires_at,
        },
    )
    await _event(
        connection,
        thread_id,
        "proposal.created",
        {"proposal_id": proposal_id, "decision": parsed.decision},
        f"review-chat-proposal:{proposal_id}",
    )
    return ReviewChatProposalResponse(
        proposal_id=proposal_id,
        thread_id=thread_id,
        run_id=context.run_id,
        expected_review_version=context.review_version,
        context_hash=context.context_hash,
        status="awaiting_confirmation",
        decision=parsed.decision,
        next_action=parsed.next_action,
        reason=parsed.reason,
        reason_category=parsed.reason_category,
        disposition=parsed.disposition,
        correction=parsed.correction,
        target_stage=TARGET_STAGE_BY_REASON.get(parsed.reason_category or ""),
        revision=parsed.correction,
        expires_at=expires_at,
    )


async def _append_message(
    connection: AsyncConnection,
    *,
    thread_id: str,
    role: str,
    message_kind: str,
    content: str,
    structured_payload: dict[str, object],
    citations: tuple[dict[str, str], ...],
    context_hash: str,
    created_by: str | None,
    idempotency_key: str | None,
) -> ReviewChatMessageResponse:
    sequence_result = await connection.execute(
        text("SELECT COALESCE(max(sequence), 0) + 1 FROM review_chat_messages WHERE thread_id = :thread_id"),
        {"thread_id": thread_id},
    )
    sequence = int(sequence_result.scalar_one())
    message_id = str(uuid4())
    result = await connection.execute(
        text(
            "INSERT INTO review_chat_messages ("
            "message_id, thread_id, sequence, role, message_kind, content, structured_payload, "
            "citations, context_hash, prompt_version, idempotency_key, message_hash, created_by"
            ") VALUES ("
            ":message_id, :thread_id, :sequence, :role, :message_kind, :content, "
            "CAST(:structured_payload AS jsonb), CAST(:citations AS jsonb), :context_hash, "
            ":prompt_version, :idempotency_key, :message_hash, :created_by"
            ") RETURNING " + _message_columns()
        ),
        {
            "message_id": message_id,
            "thread_id": thread_id,
            "sequence": sequence,
            "role": role,
            "message_kind": message_kind,
            "content": content,
            "structured_payload": _dump(structured_payload),
            "citations": _dump(citations),
            "context_hash": context_hash,
            "prompt_version": PROMPT_VERSION,
            "idempotency_key": idempotency_key,
            "message_hash": _hash(
                {"role": role, "kind": message_kind, "content": content, "payload": structured_payload, "context_hash": context_hash}
            ),
            "created_by": created_by,
        },
    )
    return _message_from_row(result.mappings().one())


async def _existing_submission(
    connection: AsyncConnection,
    operator: ReviewChatMessageResponse,
) -> ReviewChatSubmissionResponse:
    result = await connection.execute(
        text(
            "SELECT " + _message_columns() + " FROM review_chat_messages "
            "WHERE thread_id = :thread_id AND sequence = :sequence"
        ),
        {"thread_id": operator.thread_id, "sequence": operator.sequence + 1},
    )
    assistant_row = result.mappings().one_or_none()
    if assistant_row is None:
        raise ReviewChatConflictError("idempotent message is incomplete")
    assistant = _message_from_row(assistant_row)
    return ReviewChatSubmissionResponse(operator_message=operator, assistant_message=assistant)


async def _message_by_idempotency(
    connection: AsyncConnection,
    thread_id: str,
    idempotency_key: str,
) -> ReviewChatMessageResponse | None:
    result = await connection.execute(
        text(
            "SELECT " + _message_columns() + " FROM review_chat_messages "
            "WHERE thread_id = :thread_id AND idempotency_key = :idempotency_key"
        ),
        {"thread_id": thread_id, "idempotency_key": idempotency_key},
    )
    row = result.mappings().one_or_none()
    return None if row is None else _message_from_row(row)


async def _message_hash_by_idempotency(
    connection: AsyncConnection,
    thread_id: str,
    idempotency_key: str,
) -> str | None:
    result = await connection.execute(
        text(
            "SELECT message_hash FROM review_chat_messages "
            "WHERE thread_id = :thread_id AND idempotency_key = :idempotency_key"
        ),
        {"thread_id": thread_id, "idempotency_key": idempotency_key},
    )
    value = result.scalar_one_or_none()
    return None if value is None else str(value)


async def _locked_thread(connection: AsyncConnection, thread_id: str) -> RowMapping:
    result = await connection.execute(
        text("SELECT * FROM review_chat_threads WHERE thread_id = :thread_id FOR UPDATE"),
        {"thread_id": thread_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ReviewChatNotFoundError()
    if str(row["status"]) != "open":
        raise ReviewChatConflictError("review chat thread is not open")
    return row


async def _locked_proposal(connection: AsyncConnection, proposal_id: str) -> RowMapping:
    result = await connection.execute(
        text("SELECT * FROM review_chat_action_proposals WHERE proposal_id = :proposal_id FOR UPDATE"),
        {"proposal_id": proposal_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ReviewChatNotFoundError()
    return row


async def _thread_exists(connection: AsyncConnection, thread_id: str) -> bool:
    result = await connection.execute(
        text("SELECT 1 FROM review_chat_threads WHERE thread_id = :thread_id"),
        {"thread_id": thread_id},
    )
    return result.scalar_one_or_none() is not None


async def _set_proposal_status(
    connection: AsyncConnection,
    proposal_id: str,
    status: str,
) -> None:
    await connection.execute(
        text(
            "UPDATE review_chat_action_proposals SET status = :status, updated_at = now() "
            "WHERE proposal_id = :proposal_id"
        ),
        {"proposal_id": proposal_id, "status": status},
    )


async def _event(
    connection: AsyncConnection,
    thread_id: str,
    event_type: str,
    payload: dict[str, object],
    operation_key: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO review_chat_events (thread_id, event_type, payload, operation_key) "
            "VALUES (:thread_id, :event_type, CAST(:payload AS jsonb), :operation_key) "
            "ON CONFLICT (operation_key) WHERE operation_key IS NOT NULL DO NOTHING"
        ),
        {"thread_id": thread_id, "event_type": event_type, "payload": _dump(payload), "operation_key": operation_key},
    )


def _thread_from_row(row: RowMapping) -> ReviewChatThreadResponse:
    return ReviewChatThreadResponse(
        thread_id=str(row["thread_id"]),
        run_id=str(row["run_id"]),
        status=row["status"],
        context_hash=str(row["context_hash"]),
        base_review_version=int(row["base_review_version"]),
        created_at=row["created_at"],
    )


def _message_from_row(row: RowMapping) -> ReviewChatMessageResponse:
    return ReviewChatMessageResponse(
        message_id=str(row["message_id"]),
        thread_id=str(row["thread_id"]),
        sequence=int(row["sequence"]),
        role=row["role"],
        message_kind=row["message_kind"],
        content=str(row["content"]),
        structured_payload=_json_object(row["structured_payload"]),
        citations=tuple(orjson.loads(row["citations"])),
        context_hash=str(row["context_hash"]),
        created_at=row["created_at"],
    )


def _confirmation_from_row(row: RowMapping) -> ReviewChatConfirmationResponse:
    return ReviewChatConfirmationResponse(
        proposal_id=str(row["proposal_id"]),
        status=row["status"],
        review_id=None if row["executed_review_id"] is None else str(row["executed_review_id"]),
        child_run_id=None if row["child_run_id"] is None else str(row["child_run_id"]),
        target_stage=None,
    )


def _message_columns() -> str:
    return (
        "message_id, thread_id, sequence, role, message_kind, content, "
        "CAST(structured_payload AS text) AS structured_payload, CAST(citations AS text) AS citations, "
        "context_hash, message_hash, created_at"
    )


def _looks_like_action(content: str) -> bool:
    return parse_review_chat_intent(content).kind != "explain"


def _is_work_order_change_request(
    normalized: str,
    document_context: dict[str, str] | None,
) -> bool:
    if not normalized or document_context is None or document_context.get("document_type") != "work_order":
        return False
    if normalized.endswith("?"):
        return False
    question_markers = ("왜", "어떻게", "무엇", "무슨", "알려", "설명", "보여", "확인해줘")
    return not any(marker in normalized for marker in question_markers)


def _reason_category(normalized: str) -> str | None:
    mapping = (
        (("위험", "근거", "보강", "재작성", "다시 작성"), "report_draft_issue"),
        (("rag", "검색", "문서"), "rag_retrieval_issue"),
        (("날씨", "기상"), "weather_context_issue"),
        (("모델", "예측", "ml"), "ml_prediction_issue"),
        (("고장", "fault"), "fault_analysis_issue"),
        (("해석",), "rag_interpretation_issue"),
        (("보고서", "summary", "action plan"), "report_draft_issue"),
        (("근거 부족", "증거 부족"), "insufficient_evidence"),
        (("정책",), "operational_policy_issue"),
    )
    for tokens, category in mapping:
        if any(token in normalized for token in tokens):
            return category
    return None


def _reason_from_content(content: str, decision: str) -> str:
    for token in ("승인", "거절", "교정", "수정", "고쳐", "approve", "reject", "correct"):
        content = content.replace(token, "")
    return content.strip(" .,!?")


def _clarification_message(parsed: ParsedAction, context: ReviewChatContext) -> str:
    if parsed.kind == "clarify":
        return "거절 사유와 하나의 검토 결정을 명확히 입력해 주세요. 제안은 별도 확정 전에는 실행되지 않습니다."
    summary = context.output.get("summary")
    if isinstance(summary, str) and summary:
        return f"현재 저장된 최종 결과는 다음과 같습니다: {summary}"
    return "저장된 Stage 결과와 최종 출력만 기준으로 설명할 수 있습니다."


def _proposal_message(parsed: ParsedAction) -> str:
    assert parsed.decision is not None
    action = "재실행" if parsed.next_action == "targeted_rerun" else "검토 이력 저장"
    return f"수정 제안을 만들었습니다. 확정 전에는 검토 결과나 후속 실행이 변경되지 않습니다. 확정하면 {action}합니다."


def _plain_chat_text(content: str) -> str:
    without_emphasis = re.sub(r"\*\*|__|`", "", content)
    return re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", without_emphasis).strip()


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, str):
        value = orjson.loads(value)
    return value if isinstance(value, dict) else {}


def _string_object(value: object) -> dict[str, str] | None:
    data = _json_object(value)
    if not data or any(not isinstance(key, str) or not isinstance(item, str) for key, item in data.items()):
        return None
    return cast(dict[str, str], data)


def _hash(value: object) -> str:
    return sha256(orjson.dumps(value, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _dump(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
