from __future__ import annotations

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_review_api_models import (
    PolicyCandidateDecisionRequest,
    PolicyCandidatePage,
    PolicyCandidateResponse,
    PolicyCandidateStatus,
)


class StalePolicyCandidateVersionError(RuntimeError):
    def __init__(self, candidate_id: str) -> None:
        super().__init__("policy candidate version is stale")
        self.candidate_id = candidate_id

    def __str__(self) -> str:
        return "policy candidate version is stale"


async def list_policy_candidates(
    engine: AsyncEngine,
    *,
    status: PolicyCandidateStatus | None = None,
    limit: int = 100,
) -> PolicyCandidatePage:
    filters: list[str] = []
    params: dict[str, str | int] = {"limit": max(1, min(limit, 100))}
    if status is not None:
        filters.append("status = :status")
        params["status"] = status
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT "
                + _candidate_columns()
                + f" FROM agent_policy_candidates {where} "
                "ORDER BY created_at DESC, candidate_id DESC LIMIT :limit"
            ),
            params,
        )
    return PolicyCandidatePage(
        items=tuple(_candidate_from_row(row) for row in result.mappings().all())
    )


async def decide_policy_candidate(
    engine: AsyncEngine,
    candidate_id: str,
    request: PolicyCandidateDecisionRequest,
    *,
    decision: PolicyCandidateStatus,
) -> PolicyCandidateResponse | None:
    async with engine.begin() as connection:
        existing = await _get_candidate(connection, candidate_id)
        if existing is None:
            return None
        if existing.version != request.expected_version:
            raise StalePolicyCandidateVersionError(candidate_id)
        history = (
            *existing.decision_history,
            {
                "version": existing.version + 1,
                "decision": decision,
                "reviewer": request.reviewer,
                "reason": request.reason,
            },
        )
        result = await connection.execute(
            text(
                "UPDATE agent_policy_candidates SET "
                "status = :status, version = version + 1, "
                "decision_history = CAST(:decision_history AS jsonb), "
                "updated_at = now() "
                "WHERE candidate_id = :candidate_id AND version = :expected_version "
                "RETURNING "
                + _candidate_columns()
            ),
            {
                "candidate_id": candidate_id,
                "expected_version": request.expected_version,
                "status": decision,
                "decision_history": _json(history),
            },
        )
    row = result.mappings().one_or_none()
    if row is None:
        raise StalePolicyCandidateVersionError(candidate_id)
    return _candidate_from_row(row)


async def _get_candidate(
    connection: AsyncConnection,
    candidate_id: str,
) -> PolicyCandidateResponse | None:
    result = await connection.execute(
        text(
            "SELECT "
            + _candidate_columns()
            + " FROM agent_policy_candidates WHERE candidate_id = :candidate_id"
        ),
        {"candidate_id": candidate_id},
    )
    row = result.mappings().one_or_none()
    return None if row is None else _candidate_from_row(row)


def _candidate_columns() -> str:
    return (
        "candidate_id, source_review_id, status, version, scope, "
        "CAST(proposal AS text) AS proposal, "
        "CAST(supporting_evidence AS text) AS supporting_evidence, "
        "CAST(decision_history AS text) AS decision_history, created_at, updated_at"
    )


def _candidate_from_row(row: RowMapping) -> PolicyCandidateResponse:
    return PolicyCandidateResponse(
        candidate_id=str(row["candidate_id"]),
        source_review_id=str(row["source_review_id"]),
        status=row["status"],
        version=int(row["version"]),
        scope=str(row["scope"]),
        proposal=orjson.loads(row["proposal"]),
        supporting_evidence_ids=tuple(orjson.loads(row["supporting_evidence"])),
        decision_history=tuple(orjson.loads(row["decision_history"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _json(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
