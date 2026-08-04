from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
DATABASE_URL = os.getenv(
    "HEATGRID_INCIDENT_DOCUMENT_TEST_DATABASE_URL",
    os.getenv(
        "HEATGRID_DATABASE_URL",
        "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops",
    ),
)
sys.path.insert(0, str(BACKEND))

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="an incident document test database URL is required",
)


@pytest.mark.anyio
async def test_failed_generation_can_retry_after_model_key_recovers() -> None:
    from incident_document_repository import PostgresIncidentDocumentRepository
    from incident_document_routes import make_incident_document_router
    from settings import Settings

    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    episode_id = await _seed_episode(engine)
    failed_app = FastAPI()
    failed_app.include_router(
        make_incident_document_router(
            PostgresIncidentDocumentRepository(engine),
            settings=Settings(OPENAI_API_KEY=None),
        )
    )
    recovered_app = FastAPI()
    recovered_app.include_router(
        make_incident_document_router(
            PostgresIncidentDocumentRepository(engine),
            settings=Settings(OPENAI_API_KEY=SecretStr("test-key")),
        )
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=failed_app), base_url="http://test") as client:
            failed = await client.post(
                f"/api/incidents/{episode_id}/documents/incident_report/generate",
                json={
                    "created_by": "operator",
                    "idempotency_key": f"missing-key-{uuid4()}",
                    "evidence_ids": [f"episode:{episode_id}"],
                },
            )
        async with AsyncClient(transport=ASGITransport(app=recovered_app), base_url="http://test") as client:
            recovered = await client.post(
                f"/api/incidents/{episode_id}/documents/incident_report/generate",
                json={
                    "created_by": "operator",
                    "idempotency_key": f"recovered-{uuid4()}",
                    "evidence_ids": [f"episode:{episode_id}"],
                },
            )

        assert failed.status_code == 202
        assert failed.json()["version"] == 1
        assert recovered.status_code == 201
        assert recovered.json()["version"] == 2
        assert recovered.json()["status"] == "draft"
        assert recovered.json()["parent_document_version_id"] == failed.json()["document_version_id"]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_incident_document_mutations_are_idempotent_and_detect_mismatch() -> None:
    from incident_document_repository import PostgresIncidentDocumentRepository
    from incident_document_routes import make_incident_document_router
    from settings import Settings

    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    app = FastAPI()
    app.include_router(
        make_incident_document_router(
            PostgresIncidentDocumentRepository(engine),
            settings=Settings(OPENAI_API_KEY=SecretStr("test-key")),
        )
    )
    episode_id = await _seed_episode(engine)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            generated, generated_repeat, generated_mismatch = await _generate_idempotency_probe(client, episode_id)
            edited, edited_repeat = await _edit_idempotency_probe(client, episode_id)
            noted, noted_repeat = await _note_idempotency_probe(client, episode_id)
            approved, approved_repeat, approved_mismatch = await _approve_idempotency_probe(client, episode_id)

        audit_counts = await _document_audit_counts(
            engine,
            generated.json()["document_version_id"],
            edited.json()["document_version_id"],
        )
        assert generated.status_code == 201
        assert generated_repeat.json()["document_version_id"] == generated.json()["document_version_id"]
        assert generated_mismatch.status_code == 409
        assert edited.status_code == 200
        assert edited_repeat.json()["document_version_id"] == edited.json()["document_version_id"]
        assert noted.status_code == 200
        assert noted_repeat.json()["document_version_id"] == noted.json()["document_version_id"]
        assert approved.status_code == 200
        assert approved_repeat.json()["approved_at"] == approved.json()["approved_at"]
        assert approved_mismatch.status_code == 409
        assert audit_counts == {
            "v1_ai_review": 1,
            "v2_ai_review": 1,
            "v2_operator_note": 1,
            "v2_approval": 1,
        }
    finally:
        await engine.dispose()


async def _generate_idempotency_probe(client: AsyncClient, episode_id: str):
    key = f"generate-{uuid4()}"
    payload = {
        "created_by": "operator",
        "idempotency_key": key,
        "evidence_ids": [f"episode:{episode_id}"],
    }
    path = f"/api/incidents/{episode_id}/documents/work_order/generate"
    return (
        await client.post(path, json=payload),
        await client.post(path, json=payload),
        await client.post(path, json={**payload, "evidence_ids": []}),
    )


async def _edit_idempotency_probe(client: AsyncClient, episode_id: str):
    key = f"edit-{uuid4()}"
    payload = {
        "expected_version": 1,
        "edited_by": "operator",
        "idempotency_key": key,
        "body": "Idempotent edited body",
        "evidence_ids": [f"episode:{episode_id}"],
    }
    path = f"/api/incidents/{episode_id}/documents/work_order/versions/1"
    return await client.put(path, json=payload), await client.put(path, json=payload)


async def _note_idempotency_probe(client: AsyncClient, episode_id: str):
    key = f"note-{uuid4()}"
    payload = {
        "expected_version": 2,
        "edited_by": "operator",
        "idempotency_key": key,
        "note": "hold for shift review",
    }
    path = f"/api/incidents/{episode_id}/documents/work_order/versions/2"
    return await client.put(path, json=payload), await client.put(path, json=payload)


async def _approve_idempotency_probe(client: AsyncClient, episode_id: str):
    key = f"approve-{uuid4()}"
    payload = {
        "expected_version": 2,
        "approved_by": "operator",
        "idempotency_key": key,
        "note": "approved for operator controlled send",
    }
    path = f"/api/incidents/{episode_id}/documents/work_order/approve"
    return (
        await client.post(path, json=payload),
        await client.post(path, json=payload),
        await client.post(path, json={**payload, "note": "different approval note"}),
    )


async def _document_audit_counts(
    engine: AsyncEngine,
    first_document_version_id: str,
    second_document_version_id: str,
) -> dict[str, int]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT document_version_id::text, review_type, count(*) AS count "
                "FROM incident_document_reviews "
                "WHERE document_version_id IN (:first_id, :second_id) "
                "GROUP BY document_version_id, review_type"
            ),
            {"first_id": first_document_version_id, "second_id": second_document_version_id},
        )
    rows = result.mappings().all()
    counts: dict[str, int] = {}
    for row in rows:
        prefix = "v1" if row["document_version_id"] == first_document_version_id else "v2"
        counts[f"{prefix}_{row['review_type']}"] = int(row["count"])
    return counts


async def _seed_episode(engine: AsyncEngine) -> str:
    suffix = uuid4().hex[:12]
    manufacturer_id = f"incident-doc-{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO substations (manufacturer_id, substation_id, configuration_type) "
                "VALUES (:manufacturer_id, 7701, 'qa') "
                "ON CONFLICT (manufacturer_id, substation_id) DO NOTHING"
            ),
            {"manufacturer_id": manufacturer_id},
        )
        episode_id = await connection.scalar(
            text(
                "INSERT INTO anomaly_episodes "
                "(stream_key, manufacturer_id, substation_id, lifecycle_status, "
                "severity, alert_id, opened_at) "
                "VALUES (:stream_key, :manufacturer_id, 7701, 'open', 'high', "
                ":alert_id, now()) "
                "RETURNING episode_id::text"
            ),
            {
                "stream_key": f"incident-doc:{suffix}",
                "manufacturer_id": manufacturer_id,
                "alert_id": str(uuid4()),
            },
        )
    assert isinstance(episode_id, str)
    return episode_id
