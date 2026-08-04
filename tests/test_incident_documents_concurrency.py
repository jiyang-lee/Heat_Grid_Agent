from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import anyio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
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
async def test_concurrent_same_key_generate_replays_single_document_version() -> None:
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
    key = f"concurrent-generate-{uuid4()}"
    path = f"/api/incidents/{episode_id}/documents/work_order/generate"
    payload = {
        "created_by": "operator",
        "idempotency_key": key,
        "evidence_ids": [f"episode:{episode_id}"],
    }
    try:
        first, second = await _post_pair(app, path, payload)
        generated_id = first.json()["document_version_id"]
        counts = await _document_counts(engine, episode_id, generated_id)

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["document_version_id"] == generated_id
        assert counts == {"versions": 1, "ai_review": 1}
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_concurrent_same_key_note_only_replays_single_audit_row() -> None:
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
    document_version_id = await _generate_work_order(app, episode_id)
    key = f"concurrent-note-{uuid4()}"
    path = f"/api/incidents/{episode_id}/documents/work_order/versions/1"
    payload = {
        "expected_version": 1,
        "edited_by": "operator",
        "idempotency_key": key,
        "note": "hold until shift lead review",
    }
    try:
        first, second = await _put_pair(app, path, payload)
        counts = await _document_counts(engine, episode_id, document_version_id)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["document_version_id"] == document_version_id
        assert counts == {"versions": 1, "ai_review": 1, "operator_note": 1}
    finally:
        await engine.dispose()


async def _post_pair(app: FastAPI, path: str, payload: dict[str, object]) -> tuple[Response, Response]:
    responses: list[Response | None] = [None, None]
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(_post_into, app, path, payload, responses, 0)
        task_group.start_soon(_post_into, app, path, payload, responses, 1)
    first, second = responses
    assert first is not None
    assert second is not None
    return first, second


async def _put_pair(app: FastAPI, path: str, payload: dict[str, object]) -> tuple[Response, Response]:
    responses: list[Response | None] = [None, None]
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(_put_into, app, path, payload, responses, 0)
        task_group.start_soon(_put_into, app, path, payload, responses, 1)
    first, second = responses
    assert first is not None
    assert second is not None
    return first, second


async def _post_into(
    app: FastAPI,
    path: str,
    payload: dict[str, object],
    responses: list[Response | None],
    index: int,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses[index] = await client.post(path, json=payload)


async def _put_into(
    app: FastAPI,
    path: str,
    payload: dict[str, object],
    responses: list[Response | None],
    index: int,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses[index] = await client.put(path, json=payload)


async def _generate_work_order(app: FastAPI, episode_id: str) -> str:
    payload = {
        "created_by": "operator",
        "idempotency_key": f"generate-{uuid4()}",
        "evidence_ids": [f"episode:{episode_id}"],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/incidents/{episode_id}/documents/work_order/generate",
            json=payload,
        )
    assert response.status_code == 201
    document_version_id = response.json()["document_version_id"]
    assert isinstance(document_version_id, str)
    return document_version_id


async def _document_counts(
    engine: AsyncEngine,
    episode_id: str,
    document_version_id: str,
) -> dict[str, int]:
    async with engine.connect() as connection:
        version_count = await connection.scalar(
            text(
                "SELECT count(*) FROM incident_document_versions "
                "WHERE episode_id = :episode_id AND document_type = 'work_order'"
            ),
            {"episode_id": episode_id},
        )
        reviews = await connection.execute(
            text(
                "SELECT review_type, count(*) AS count "
                "FROM incident_document_reviews "
                "WHERE document_version_id = :document_version_id "
                "GROUP BY review_type"
            ),
            {"document_version_id": document_version_id},
        )
    counts = {"versions": int(version_count or 0)}
    counts.update({str(row["review_type"]): int(row["count"]) for row in reviews.mappings().all()})
    return counts


async def _seed_episode(engine: AsyncEngine) -> str:
    suffix = uuid4().hex[:12]
    manufacturer_id = f"incident-doc-concurrent-{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO substations (manufacturer_id, substation_id, configuration_type) "
                "VALUES (:manufacturer_id, 7702, 'qa') "
                "ON CONFLICT (manufacturer_id, substation_id) DO NOTHING"
            ),
            {"manufacturer_id": manufacturer_id},
        )
        episode_id = await connection.scalar(
            text(
                "INSERT INTO anomaly_episodes "
                "(stream_key, manufacturer_id, substation_id, lifecycle_status, "
                "severity, alert_id, opened_at) "
                "VALUES (:stream_key, :manufacturer_id, 7702, 'open', 'high', "
                ":alert_id, now()) "
                "RETURNING episode_id::text"
            ),
            {
                "stream_key": f"incident-doc-concurrent:{suffix}",
                "manufacturer_id": manufacturer_id,
                "alert_id": str(uuid4()),
            },
        )
    assert isinstance(episode_id, str)
    return episode_id
