from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from incident_document_api_models import (
    DocumentType,
    IncidentDocumentContent,
    IncidentDocumentResponse,
    IncidentEvidenceCitation,
    ReviewState,
)
from incident_document_content import content_from_row, document_status, dump_json, hash_json
from incident_document_repository_errors import (
    IncidentDocumentNotFoundError,
    InvalidIncidentCitationError,
)


async def require_episode(connection: AsyncConnection, episode_id: str) -> None:
    result = await connection.execute(
        text("SELECT 1 FROM anomaly_episodes WHERE episode_id = :episode_id"),
        {"episode_id": episode_id},
    )
    if result.scalar_one_or_none() is None:
        raise IncidentDocumentNotFoundError(episode_id)


async def latest_version(
    connection: AsyncConnection,
    episode_id: str,
    document_type: DocumentType,
) -> RowMapping | None:
    await require_episode(connection, episode_id)
    result = await connection.execute(
        text(
            "SELECT " + document_columns() + " FROM incident_document_versions "
            "WHERE episode_id = :episode_id AND document_type = :document_type "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"episode_id": episode_id, "document_type": document_type},
    )
    return result.mappings().one_or_none()


async def insert_version(
    connection: AsyncConnection,
    *,
    episode_id: str,
    document_type: DocumentType,
    version: int,
    parent_document_version_id: str | None,
    status: str,
    content: IncidentDocumentContent,
    actor: str,
) -> RowMapping:
    payload = content.model_dump(mode="json")
    result = await connection.execute(
        text(
            "INSERT INTO incident_document_versions ("
            "document_version_id, episode_id, document_type, version, "
            "parent_document_version_id, status, content, content_hash, created_by"
            ") VALUES ("
            ":document_version_id, :episode_id, :document_type, :version, "
            ":parent_document_version_id, :status, CAST(:content AS jsonb), "
            ":content_hash, :created_by"
            ") RETURNING " + document_columns()
        ),
        {
            "document_version_id": str(uuid4()),
            "episode_id": episode_id,
            "document_type": document_type,
            "version": version,
            "parent_document_version_id": parent_document_version_id,
            "status": status,
            "content": dump_json(payload),
            "content_hash": hash_json(payload),
            "created_by": actor,
        },
    )
    return result.mappings().one()


async def document_by_id(
    connection: AsyncConnection,
    document_version_id: str,
) -> RowMapping:
    result = await connection.execute(
        text(
            "SELECT " + document_columns() + " FROM incident_document_versions "
            "WHERE document_version_id = :document_version_id"
        ),
        {"document_version_id": document_version_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise IncidentDocumentNotFoundError(document_version_id)
    return row


async def insert_review(
    connection: AsyncConnection,
    *,
    document_version_id: str,
    review_type: str,
    decision: str,
    note: str,
    actor: str,
    evidence: tuple[IncidentEvidenceCitation, ...],
) -> None:
    await connection.execute(
        text(
            "INSERT INTO incident_document_reviews ("
            "document_review_id, document_version_id, review_type, decision, note, evidence, actor"
            ") VALUES ("
            ":document_review_id, :document_version_id, :review_type, :decision, "
            ":note, CAST(:evidence AS jsonb), :actor)"
        ),
        {
            "document_review_id": str(uuid4()),
            "document_version_id": document_version_id,
            "review_type": review_type,
            "decision": decision,
            "note": note,
            "evidence": dump_json([item.model_dump(mode="json") for item in evidence]),
            "actor": actor,
        },
    )


async def validate_citations(
    connection: AsyncConnection,
    episode_id: str,
    evidence_ids: tuple[str, ...],
) -> tuple[IncidentEvidenceCitation, ...]:
    await require_episode(connection, episode_id)
    allowed = await allowed_citation_ids(connection, episode_id)
    selected = evidence_ids or (f"episode:{episode_id}",)
    citations: list[IncidentEvidenceCitation] = []
    for citation_id in selected:
        label = allowed.get(citation_id)
        if label is None:
            raise InvalidIncidentCitationError(citation_id)
        citations.append(IncidentEvidenceCitation(citation_id=citation_id, label=label))
    return tuple(citations)


async def response_from_row(
    connection: AsyncConnection,
    row: RowMapping,
) -> IncidentDocumentResponse:
    document_version_id = str(row["document_version_id"])
    approval = await approval_row(connection, document_version_id)
    review = await review_state(connection, document_version_id, approval_exists=approval is not None)
    stored_status = str(row["status"])
    status = "approved" if approval is not None else document_status(stored_status)
    return IncidentDocumentResponse(
        document_version_id=document_version_id,
        episode_id=str(row["episode_id"]),
        document_type=row["document_type"],
        version=int(row["version"]),
        parent_document_version_id=None
        if row["parent_document_version_id"] is None
        else str(row["parent_document_version_id"]),
        status=status,
        review_state=review,
        retryable=stored_status == "failed",
        content=content_from_row(row),
        content_hash=str(row["content_hash"]),
        created_by=str(row["created_by"]),
        created_at=row["created_at"],
        approved_by=None if approval is None else str(approval["actor"]),
        approved_at=None if approval is None else approval["created_at"],
    )


async def has_approval(connection: AsyncConnection, document_version_id: str) -> bool:
    return await approval_row(connection, document_version_id) is not None


def document_columns() -> str:
    return (
        "document_version_id, episode_id, document_type, version, "
        "parent_document_version_id, status, CAST(content AS text) AS content, "
        "content_hash, created_by, created_at, approved_by, approved_at"
    )


async def allowed_citation_ids(
    connection: AsyncConnection,
    episode_id: str,
) -> dict[str, str]:
    result = await connection.execute(
        text(
            "SELECT e.episode_id::text AS episode_id, q.alert_id::text AS alert_id, "
            "r.run_id::text AS run_id FROM anomaly_episodes e "
            "LEFT JOIN ops_alert_queue q ON q.episode_id = e.episode_id "
            "LEFT JOIN agent_runs r ON r.alert_id = q.alert_id "
            "WHERE e.episode_id = :episode_id"
        ),
        {"episode_id": episode_id},
    )
    rows = result.mappings().all()
    if not rows:
        raise IncidentDocumentNotFoundError(episode_id)
    allowed = {f"episode:{episode_id}": "Anomaly episode evidence"}
    for row in rows:
        if row["alert_id"] is not None:
            allowed[f"alert:{row['alert_id']}"] = "Alert queue evidence"
        if row["run_id"] is not None:
            allowed[f"run:{row['run_id']}"] = "AI analysis run evidence"
    return allowed | await document_citation_ids(connection, episode_id)


async def document_citation_ids(
    connection: AsyncConnection,
    episode_id: str,
) -> dict[str, str]:
    result = await connection.execute(
        text(
            "SELECT document_version_id::text, document_type, version "
            "FROM incident_document_versions WHERE episode_id = :episode_id"
        ),
        {"episode_id": episode_id},
    )
    return {
        f"document:{row['document_version_id']}": f"{row['document_type']} v{row['version']}"
        for row in result.mappings().all()
    }


async def approval_row(connection: AsyncConnection, document_version_id: str) -> RowMapping | None:
    result = await connection.execute(
        text(
            "SELECT actor, created_at FROM incident_document_reviews "
            "WHERE document_version_id = :document_version_id "
            "AND review_type = 'approval' AND decision = 'approved' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"document_version_id": document_version_id},
    )
    return result.mappings().one_or_none()


async def review_state(
    connection: AsyncConnection,
    document_version_id: str,
    *,
    approval_exists: bool,
) -> ReviewState:
    if approval_exists:
        return "approved"
    result = await connection.execute(
        text(
            "SELECT review_type, decision FROM incident_document_reviews "
            "WHERE document_version_id = :document_version_id "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"document_version_id": document_version_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return "none"
    if row["decision"] == "failed":
        return "failed"
    if row["review_type"] == "operator_note":
        return "operator_noted"
    if row["review_type"] == "ai_review" and row["decision"] == "pending":
        return "pending_ai_review"
    return "none"
