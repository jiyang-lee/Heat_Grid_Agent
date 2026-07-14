from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_review_api_models import (
    OperatorReviewHistoryResponse,
    OperatorReviewRecordResponse,
    OperatorReviewSubmitRequest,
)


class StaleReviewVersionError(RuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__("review version is stale")
        self.run_id = run_id

    def __str__(self) -> str:
        return "review version is stale"


class UnknownRunError(RuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__("run_id was not found")
        self.run_id = run_id

    def __str__(self) -> str:
        return "run_id was not found"


class IdempotencyConflictError(RuntimeError):
    def __str__(self) -> str:
        return "idempotency key was already used with a different request"


@dataclass(frozen=True, slots=True)
class ReviewRecordInput:
    run_id: str | None
    review_task_id: str | None
    subject_type: str
    subject_key: str
    decision: Literal["approve", "correct", "reject", "keep_human_review"]
    reviewer: str
    reason: str
    reason_category: str | None
    idempotency_key: str
    request_hash: str
    disposition: str | None
    correction: dict[str, str] | None
    evidence_annotations: tuple[dict[str, str | None], ...]
    operator_labels: tuple[str, ...]
    review_contract_version: int = 2
    expected_review_version: int | None = None
    legacy_status_override: Literal[
        "approved", "corrected", "rejected", "pending"
    ] | None = None


async def submit_operator_review(
    engine: AsyncEngine,
    run_id: str,
    request: OperatorReviewSubmitRequest,
) -> OperatorReviewRecordResponse:
    async with engine.begin() as connection:
        return await record_review(
            connection,
            ReviewRecordInput(
                run_id=run_id,
                review_task_id=None,
                subject_type="agent_run",
                subject_key=run_id,
                decision=request.decision,
                reviewer=request.reviewer,
                reason=request.reason,
                reason_category=request.reason_category,
                idempotency_key=request.idempotency_key,
                request_hash=_request_hash(request),
                disposition=request.disposition,
                correction=request.correction,
                evidence_annotations=request.evidence_annotations,
                operator_labels=request.operator_labels,
                expected_review_version=request.expected_review_version,
            ),
        )


async def record_subject_review(
    connection: AsyncConnection,
    *,
    subject_type: str,
    subject_key: str,
    decision: Literal["approve", "correct", "reject"],
    reviewer: str,
    reason: str,
    request_payload: object,
    idempotency_key: str,
) -> OperatorReviewRecordResponse:
    await _lock_review_subject(connection, subject_type, subject_key)
    task_result = await connection.execute(
        text(
            "SELECT task_id FROM human_review_tasks "
            "WHERE subject_type = :subject_type AND subject_key = :subject_key "
            "AND status = 'pending' ORDER BY created_at, task_id LIMIT 1 FOR UPDATE"
        ),
        {"subject_type": subject_type, "subject_key": subject_key},
    )
    task_id = task_result.scalar_one_or_none()
    request_hash = sha256(
        orjson.dumps(request_payload, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    return await record_review(
        connection,
        ReviewRecordInput(
            run_id=None,
            review_task_id=None if task_id is None else str(task_id),
            subject_type=subject_type,
            subject_key=subject_key,
            decision=decision,
            reviewer=reviewer,
            reason=reason or "operator review",
            reason_category="operator_reject" if decision == "reject" else None,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            disposition=None,
            correction=None,
            evidence_annotations=(),
            operator_labels=(),
        ),
    )


async def record_review(
    connection: AsyncConnection,
    request: ReviewRecordInput,
) -> OperatorReviewRecordResponse:
    if request.subject_type == "agent_run" and request.run_id is None:
        raise ValueError("agent_run reviews require run_id")
    if request.subject_type == "agent_run" and request.subject_key != request.run_id:
        raise ValueError("agent_run subject_key must match run_id")
    if request.subject_type != "agent_run" and request.run_id is not None:
        raise ValueError("non-run reviews cannot reference run_id")
    if request.run_id is not None and not await _run_exists(connection, request.run_id):
        raise UnknownRunError(request.run_id)
    await _lock_review_subject(connection, request.subject_type, request.subject_key)
    existing = await _select_review_by_idempotency(
        connection,
        idempotency_key=request.idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request.request_hash:
            raise IdempotencyConflictError()
        return existing
    review_task_id = await _lock_or_create_review_task(connection, request)
    latest_version = await _latest_review_version(
        connection,
        subject_type=request.subject_type,
        subject_key=request.subject_key,
    )
    if (
        request.expected_review_version is not None
        and latest_version != request.expected_review_version
    ):
        raise StaleReviewVersionError(request.subject_key)
    try:
        async with connection.begin_nested():
            review = await _insert_review(
                connection,
                request=request,
                review_task_id=review_task_id,
                review_version=latest_version + 1,
            )
    except IntegrityError as exc:
        duplicate = await _select_review_by_idempotency(
            connection,
            idempotency_key=request.idempotency_key,
        )
        if duplicate is not None:
            if duplicate.request_hash != request.request_hash:
                raise IdempotencyConflictError() from exc
            return duplicate
        raise StaleReviewVersionError(request.subject_key) from exc
    await _complete_review_task(connection, review)
    await _sync_legacy_run_review_status(
        connection,
        review,
        request.legacy_status_override,
    )
    if review.decision == "correct":
        await _create_policy_candidate(connection, review)
    return review


async def list_operator_reviews(
    engine: AsyncEngine,
    run_id: str,
) -> OperatorReviewHistoryResponse | None:
    async with engine.connect() as connection:
        if not await _run_exists(connection, run_id):
            return None
        result = await connection.execute(
            text(
                "SELECT "
                + _review_columns()
                + " FROM agent_run_reviews WHERE run_id = :run_id "
                "ORDER BY review_version ASC"
            ),
            {"run_id": run_id},
        )
    return OperatorReviewHistoryResponse(
        run_id=run_id,
        items=tuple(_review_from_row(row) for row in result.mappings().all()),
    )


async def _run_exists(connection: AsyncConnection, run_id: str) -> bool:
    result = await connection.execute(
        text("SELECT 1 FROM agent_runs WHERE run_id = :run_id"),
        {"run_id": run_id},
    )
    return result.scalar_one_or_none() is not None


async def _lock_review_subject(
    connection: AsyncConnection,
    subject_type: str,
    subject_key: str,
) -> None:
    await connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"review:{subject_type}:{subject_key}"},
    )


async def _lock_or_create_review_task(
    connection: AsyncConnection,
    request: ReviewRecordInput,
) -> str:
    if request.review_task_id is not None:
        task = await _lock_review_task(connection, request.review_task_id)
        _validate_review_task(task, request)
        return str(task["task_id"])

    if request.run_id is not None:
        result = await connection.execute(
            text(
                "SELECT review_task_id FROM agent_runs WHERE run_id = :run_id FOR UPDATE"
            ),
            {"run_id": request.run_id},
        )
        current_task_id = result.scalar_one_or_none()
        if current_task_id is not None:
            task = await _lock_review_task(connection, str(current_task_id))
            already_used = await connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM agent_run_reviews "
                    "WHERE review_task_id = :review_task_id)"
                ),
                {"review_task_id": current_task_id},
            )
            if not already_used and task["status"] == "pending":
                _validate_review_task(task, request)
                return str(current_task_id)

    task_id = str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO human_review_tasks ("
            "task_id, task_type, status, risk_level, title, run_id, payload, "
            "operation_key, subject_type, subject_key"
            ") VALUES ("
            ":task_id, :task_type, 'pending', 'medium', :title, :run_id, "
            "CAST(:payload AS jsonb), :operation_key, :subject_type, :subject_key"
            ")"
        ),
        {
            "task_id": task_id,
            "task_type": f"{request.subject_type}_review",
            "title": f"Review {request.subject_type} {request.subject_key}",
            "run_id": request.run_id,
            "payload": _json(
                {
                    "payload_source": "operator_review_submission",
                    "subject_type": request.subject_type,
                    "subject_key": request.subject_key,
                }
            ),
            "operation_key": f"operator-review:{request.idempotency_key}",
            "subject_type": request.subject_type,
            "subject_key": request.subject_key,
        },
    )
    await _lock_review_task(connection, task_id)
    return task_id


async def _lock_review_task(
    connection: AsyncConnection,
    review_task_id: str,
) -> RowMapping:
    result = await connection.execute(
        text(
            "SELECT task_id, status, subject_type, subject_key, run_id "
            "FROM human_review_tasks WHERE task_id = :task_id FOR UPDATE"
        ),
        {"task_id": review_task_id},
    )
    task = result.mappings().one_or_none()
    if task is None:
        raise ValueError("review_task_id was not found")
    return task


def _validate_review_task(task: RowMapping, request: ReviewRecordInput) -> None:
    if task["status"] != "pending":
        raise ValueError("review task is not pending")
    if task["subject_type"] != request.subject_type:
        raise ValueError("review task subject_type does not match")
    if task["subject_key"] != request.subject_key:
        raise ValueError("review task subject_key does not match")
    task_run_id = None if task["run_id"] is None else str(task["run_id"])
    if task_run_id != request.run_id:
        raise ValueError("review task run_id does not match")


async def _complete_review_task(
    connection: AsyncConnection,
    review: OperatorReviewRecordResponse,
) -> None:
    status = {
        "approve": "approved",
        "correct": "corrected",
        "reject": "rejected",
        "keep_human_review": "rejected",
    }[review.decision]
    await connection.execute(
        text(
            "UPDATE human_review_tasks SET status = :status, reviewed_by = :reviewer, "
            "resolution = CAST(:resolution AS jsonb), reviewed_at = now() "
            "WHERE task_id = :task_id"
        ),
        {
            "status": status,
            "reviewer": review.reviewer,
            "resolution": _json(
                {
                    "review_id": review.review_id,
                    "decision": review.decision,
                    "reason": review.reason,
                    "reason_category": review.reason_category,
                    "correction": review.correction,
                }
            ),
            "task_id": review.review_task_id,
        },
    )
    if review.run_id is not None:
        await connection.execute(
            text(
                "UPDATE agent_runs SET review_task_id = :review_task_id "
                "WHERE run_id = :run_id"
            ),
            {"review_task_id": review.review_task_id, "run_id": review.run_id},
        )


async def _latest_review_version(
    connection: AsyncConnection,
    *,
    subject_type: str,
    subject_key: str,
) -> int:
    result = await connection.execute(
        text(
            "SELECT COALESCE(max(review_version), 0) FROM agent_run_reviews "
            "WHERE subject_type = :subject_type AND subject_key = :subject_key"
        ),
        {"subject_type": subject_type, "subject_key": subject_key},
    )
    return int(result.scalar_one())


async def _select_review_by_idempotency(
    connection: AsyncConnection,
    *,
    idempotency_key: str,
) -> OperatorReviewRecordResponse | None:
    result = await connection.execute(
        text(
            "SELECT "
            + _review_columns()
            + " FROM agent_run_reviews "
            "WHERE idempotency_key = :idempotency_key"
        ),
        {"idempotency_key": idempotency_key},
    )
    row = result.mappings().one_or_none()
    return None if row is None else _review_from_row(row)


async def _insert_review(
    connection: AsyncConnection,
    *,
    request: ReviewRecordInput,
    review_task_id: str,
    review_version: int,
) -> OperatorReviewRecordResponse:
    result = await connection.execute(
        text(
            "INSERT INTO agent_run_reviews ("
            "review_task_id, run_id, subject_type, subject_key, review_contract_version, "
            "review_version, idempotency_key, request_hash, decision, reviewer, reason, "
            "reason_category, disposition, correction, evidence_annotations, operator_labels"
            ") VALUES ("
            ":review_task_id, :run_id, :subject_type, :subject_key, :review_contract_version, "
            ":review_version, :idempotency_key, :request_hash, :decision, :reviewer, "
            ":reason, :reason_category, :disposition, CAST(:correction AS jsonb), "
            "CAST(:evidence_annotations AS jsonb), CAST(:operator_labels AS jsonb)"
            ") RETURNING "
            + _review_columns()
        ),
        {
            "review_task_id": review_task_id,
            "run_id": request.run_id,
            "subject_type": request.subject_type,
            "subject_key": request.subject_key,
            "review_contract_version": request.review_contract_version,
            "review_version": review_version,
            "idempotency_key": request.idempotency_key,
            "request_hash": request.request_hash,
            "decision": request.decision,
            "reviewer": request.reviewer,
            "reason": request.reason,
            "reason_category": request.reason_category,
            "disposition": request.disposition,
            "correction": None
            if request.correction is None
            else _json(request.correction),
            "evidence_annotations": _json(request.evidence_annotations),
            "operator_labels": _json(request.operator_labels),
        },
    )
    return _review_from_row(result.mappings().one())


async def _sync_legacy_run_review_status(
    connection: AsyncConnection,
    review: OperatorReviewRecordResponse,
    legacy_status_override: Literal[
        "approved", "corrected", "rejected", "pending"
    ] | None = None,
) -> None:
    if review.run_id is None:
        return
    status = legacy_status_override or _legacy_review_status(review.decision)
    await connection.execute(
        text(
            "UPDATE agent_runs SET review_status = :status, updated_at = now() "
            "WHERE run_id = :run_id"
        ),
        {"run_id": review.run_id, "status": status},
    )


def _legacy_review_status(
    decision: Literal["approve", "correct", "reject", "keep_human_review"],
) -> Literal["approved", "corrected", "pending"]:
    match decision:
        case "approve":
            return "approved"
        case "correct":
            return "corrected"
        case "reject" | "keep_human_review":
            return "pending"


async def _create_policy_candidate(
    connection: AsyncConnection,
    review: OperatorReviewRecordResponse,
) -> None:
    proposal = {
        "scope": "human_review_route",
        "operation": "set",
        "target": "force_human_review",
        "value": True,
    }
    history = (
        {
            "version": 1,
            "decision": "created",
            "reviewer": review.reviewer,
            "reason": review.reason,
            "created_at": review.created_at.isoformat(),
        },
    )
    await connection.execute(
        text(
            "INSERT INTO agent_policy_candidates ("
            "source_review_id, scope, proposal, supporting_evidence, decision_history"
            ") VALUES ("
            ":source_review_id, 'human_review_route', CAST(:proposal AS jsonb), "
            "CAST(:supporting_evidence AS jsonb), CAST(:decision_history AS jsonb)"
            ") ON CONFLICT (source_review_id) DO NOTHING"
        ),
        {
            "source_review_id": review.review_id,
            "proposal": _json(proposal),
            "supporting_evidence": _json(
                tuple(
                    item["evidence_id"]
                    for item in review.evidence_annotations
                    if item.get("evidence_id")
                )
            ),
            "decision_history": _json(history),
        },
    )


def _request_hash(request: OperatorReviewSubmitRequest) -> str:
    payload = orjson.dumps(request.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


def _review_columns() -> str:
    return (
        "review_id, review_task_id, run_id, subject_type, subject_key, "
        "review_contract_version, review_version, idempotency_key, request_hash, decision, "
        "reviewer, reason, reason_category, disposition, CAST(correction AS text) AS correction, "
        "CAST(evidence_annotations AS text) AS evidence_annotations, "
        "CAST(operator_labels AS text) AS operator_labels, created_at"
    )


def _review_from_row(row: RowMapping) -> OperatorReviewRecordResponse:
    return OperatorReviewRecordResponse(
        review_id=str(row["review_id"]),
        review_task_id=str(row["review_task_id"]),
        run_id=None if row["run_id"] is None else str(row["run_id"]),
        subject_type=str(row["subject_type"]),
        subject_key=str(row["subject_key"]),
        review_contract_version=int(row["review_contract_version"]),
        review_version=int(row["review_version"]),
        idempotency_key=str(row["idempotency_key"]),
        request_hash=str(row["request_hash"]),
        decision=row["decision"],
        reviewer=str(row["reviewer"]),
        reason=str(row["reason"]),
        reason_category=row["reason_category"],
        disposition=row["disposition"],
        correction=orjson.loads(row["correction"]) if row["correction"] else None,
        evidence_annotations=tuple(orjson.loads(row["evidence_annotations"])),
        operator_labels=tuple(orjson.loads(row["operator_labels"])),
        created_at=row["created_at"],
    )


def _json(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
