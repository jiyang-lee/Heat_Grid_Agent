from __future__ import annotations

from hashlib import sha256
from typing import Literal

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


async def submit_operator_review(
    engine: AsyncEngine,
    run_id: str,
    request: OperatorReviewSubmitRequest,
) -> OperatorReviewRecordResponse:
    request_hash = _request_hash(request)
    async with engine.begin() as connection:
        if not await _run_exists(connection, run_id):
            raise UnknownRunError(run_id)
        existing = await _select_review_by_idempotency(
            connection,
            run_id=run_id,
            idempotency_key=request.idempotency_key,
        )
        if existing is not None:
            return existing
        latest_version = await _latest_review_version(connection, run_id)
        if latest_version != request.expected_review_version:
            raise StaleReviewVersionError(run_id)
        try:
            review = await _insert_review(
                connection,
                run_id=run_id,
                request=request,
                request_hash=request_hash,
                review_version=latest_version + 1,
            )
        except IntegrityError as exc:
            duplicate = await _select_review_by_idempotency(
                connection,
                run_id=run_id,
                idempotency_key=request.idempotency_key,
            )
            if duplicate is not None:
                return duplicate
            raise StaleReviewVersionError(run_id) from exc
        await _sync_legacy_run_review_status(connection, review)
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


async def _latest_review_version(connection: AsyncConnection, run_id: str) -> int:
    result = await connection.execute(
        text(
            "SELECT COALESCE(max(review_version), 0) FROM agent_run_reviews "
            "WHERE run_id = :run_id"
        ),
        {"run_id": run_id},
    )
    return int(result.scalar_one())


async def _select_review_by_idempotency(
    connection: AsyncConnection,
    *,
    run_id: str,
    idempotency_key: str,
) -> OperatorReviewRecordResponse | None:
    result = await connection.execute(
        text(
            "SELECT "
            + _review_columns()
            + " FROM agent_run_reviews "
            "WHERE run_id = :run_id AND idempotency_key = :idempotency_key"
        ),
        {"run_id": run_id, "idempotency_key": idempotency_key},
    )
    row = result.mappings().one_or_none()
    return None if row is None else _review_from_row(row)


async def _insert_review(
    connection: AsyncConnection,
    *,
    run_id: str,
    request: OperatorReviewSubmitRequest,
    request_hash: str,
    review_version: int,
) -> OperatorReviewRecordResponse:
    result = await connection.execute(
        text(
            "INSERT INTO agent_run_reviews ("
            "run_id, review_version, idempotency_key, request_hash, decision, "
            "reviewer, reason, disposition, correction, evidence_annotations, "
            "operator_labels"
            ") VALUES ("
            ":run_id, :review_version, :idempotency_key, :request_hash, "
            ":decision, :reviewer, :reason, :disposition, CAST(:correction AS jsonb), "
            "CAST(:evidence_annotations AS jsonb), CAST(:operator_labels AS jsonb)"
            ") RETURNING "
            + _review_columns()
        ),
        {
            "run_id": run_id,
            "review_version": review_version,
            "idempotency_key": request.idempotency_key,
            "request_hash": request_hash,
            "decision": request.decision,
            "reviewer": request.reviewer,
            "reason": request.reason,
            "disposition": request.disposition,
            "correction": _json(request.correction),
            "evidence_annotations": _json(request.evidence_annotations),
            "operator_labels": _json(request.operator_labels),
        },
    )
    return _review_from_row(result.mappings().one())


async def _sync_legacy_run_review_status(
    connection: AsyncConnection,
    review: OperatorReviewRecordResponse,
) -> None:
    status = _legacy_review_status(review.decision)
    await connection.execute(
        text(
            "UPDATE agent_runs SET review_status = :status, updated_at = now() "
            "WHERE run_id = :run_id"
        ),
        {"run_id": review.run_id, "status": status},
    )


def _legacy_review_status(
    decision: Literal["approve", "correct", "keep_human_review"],
) -> Literal["approved", "corrected", "pending"]:
    match decision:
        case "approve":
            return "approved"
        case "correct":
            return "corrected"
        case "keep_human_review":
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
        "review_id, run_id, review_version, idempotency_key, request_hash, decision, "
        "reviewer, reason, disposition, CAST(correction AS text) AS correction, "
        "CAST(evidence_annotations AS text) AS evidence_annotations, "
        "CAST(operator_labels AS text) AS operator_labels, created_at"
    )


def _review_from_row(row: RowMapping) -> OperatorReviewRecordResponse:
    return OperatorReviewRecordResponse(
        review_id=str(row["review_id"]),
        run_id=str(row["run_id"]),
        review_version=int(row["review_version"]),
        idempotency_key=str(row["idempotency_key"]),
        request_hash=str(row["request_hash"]),
        decision=row["decision"],
        reviewer=str(row["reviewer"]),
        reason=str(row["reason"]),
        disposition=row["disposition"],
        correction=orjson.loads(row["correction"]) if row["correction"] else None,
        evidence_annotations=tuple(orjson.loads(row["evidence_annotations"])),
        operator_labels=tuple(orjson.loads(row["operator_labels"])),
        created_at=row["created_at"],
    )


def _json(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
