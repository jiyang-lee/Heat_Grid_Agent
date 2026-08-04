from __future__ import annotations

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from incident_document_api_models import DocumentType
from incident_document_content import dump_json, hash_json
from incident_document_repository_errors import IncidentDocumentConflictError


async def begin_idempotent_operation(
    connection: AsyncConnection,
    *,
    operation_scope: str,
    idempotency_key: str,
    request_hash: str,
) -> str | None:
    await connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:operation_scope), hashtext(:idempotency_key))"),
        {"operation_scope": operation_scope, "idempotency_key": idempotency_key},
    )
    result = await connection.execute(
        text(
            "SELECT request_hash, status, CAST(response_payload AS text) AS response_payload "
            "FROM operation_idempotency_keys "
            "WHERE operation_scope = :operation_scope AND idempotency_key = :idempotency_key"
        ),
        {"operation_scope": operation_scope, "idempotency_key": idempotency_key},
    )
    row = result.mappings().one_or_none()
    if row is None:
        await connection.execute(
            text(
                "INSERT INTO operation_idempotency_keys ("
                "operation_scope, idempotency_key, request_hash, status"
                ") VALUES (:operation_scope, :idempotency_key, :request_hash, 'running')"
            ),
            {
                "operation_scope": operation_scope,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
            },
        )
        return None
    if row["request_hash"] != request_hash:
        raise IncidentDocumentConflictError("idempotency key was already used with a different payload")
    if row["status"] == "completed":
        return _document_id_from_payload(row["response_payload"])
    await connection.execute(
        text(
            "UPDATE operation_idempotency_keys "
            "SET status = 'running', response_payload = NULL, completed_at = NULL "
            "WHERE operation_scope = :operation_scope AND idempotency_key = :idempotency_key"
        ),
        {"operation_scope": operation_scope, "idempotency_key": idempotency_key},
    )
    return None


async def complete_idempotency(
    connection: AsyncConnection,
    *,
    operation_scope: str,
    idempotency_key: str,
    request_hash: str,
    document_version_id: str,
) -> None:
    result = await connection.execute(
        text(
            "UPDATE operation_idempotency_keys "
            "SET response_payload = CAST(:response_payload AS jsonb), "
            "status = 'completed', completed_at = now() "
            "WHERE operation_scope = :operation_scope "
            "AND idempotency_key = :idempotency_key "
            "AND request_hash = :request_hash "
            "RETURNING request_hash"
        ),
        {
            "operation_scope": operation_scope,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "response_payload": dump_json({"document_version_id": document_version_id}),
        },
    )
    if result.scalar_one_or_none() is not None:
        return
    raise IncidentDocumentConflictError("idempotent operation was not reserved")


async def idempotency_document_id(
    connection: AsyncConnection,
    *,
    operation_scope: str,
    idempotency_key: str,
    request_hash: str,
) -> str | None:
    result = await connection.execute(
        text(
            "SELECT request_hash, status, CAST(response_payload AS text) AS response_payload "
            "FROM operation_idempotency_keys "
            "WHERE operation_scope = :operation_scope AND idempotency_key = :idempotency_key"
        ),
        {"operation_scope": operation_scope, "idempotency_key": idempotency_key},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    if row["request_hash"] != request_hash:
        raise IncidentDocumentConflictError("idempotency key was already used with a different payload")
    if row["status"] != "completed" or row["response_payload"] is None:
        raise IncidentDocumentConflictError("idempotent operation is incomplete")
    return _document_id_from_payload(row["response_payload"])


def _document_id_from_payload(response_payload: object) -> str:
    if not isinstance(response_payload, str):
        raise IncidentDocumentConflictError("idempotent operation response is malformed")
    payload = orjson.loads(response_payload)
    document_version_id = payload.get("document_version_id") if isinstance(payload, dict) else None
    if not isinstance(document_version_id, str):
        raise IncidentDocumentConflictError("idempotent operation response is malformed")
    return document_version_id


def operation_scope(operation: str, episode_id: str, document_type: DocumentType) -> str:
    return f"incident_document:{operation}:{episode_id}:{document_type}"


def request_hash(
    operation: str,
    episode_id: str,
    document_type: DocumentType,
    payload: dict[str, object],
) -> str:
    return hash_json(
        {
            "operation": operation,
            "episode_id": episode_id,
            "document_type": document_type,
            "payload": payload,
        }
    )
