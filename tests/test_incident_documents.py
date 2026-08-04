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
async def test_incident_document_review_edit_approve_and_conflict_flow() -> None:
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
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Given: an operator manually starts analysis for an active incident.
            generated = await client.post(
                f"/api/incidents/{episode_id}/documents/work_order/generate",
                json={
                    "created_by": "operator",
                    "idempotency_key": f"gen-{uuid4()}",
                    "evidence_ids": [f"episode:{episode_id}"],
                },
            )

            # Then: a draft v1 work order is created with cited incident evidence.
            assert generated.status_code == 201
            first = generated.json()
            assert first["version"] == 1
            assert first["status"] == "draft"
            assert first["content"]["evidence"][0]["citation_id"] == f"episode:{episode_id}"

            report = await client.post(
                f"/api/incidents/{episode_id}/documents/incident_report/generate",
                json={
                    "created_by": "operator",
                    "idempotency_key": f"report-{uuid4()}",
                    "evidence_ids": [f"episode:{episode_id}"],
                    "content": {
                        "title": "열교환기 이상 분석 보고서",
                        "body": "공급온도 저하와 유량 변동을 현장 측정값으로 확인합니다.",
                        "actions": ["열교환기 입출구 온도를 기록합니다."],
                        "evidence": [],
                        "safety_notes": "운전 설정값은 변경하지 않습니다.",
                    },
                },
            )

            assert report.status_code == 201
            report_v1 = report.json()
            assert report_v1["version"] == 1
            assert report_v1["content"]["title"] == "열교환기 이상 분석 보고서"
            assert report_v1["content"]["body"] == "공급온도 저하와 유량 변동을 현장 측정값으로 확인합니다."

            # When: content fields are edited.
            edited = await client.put(
                f"/api/incidents/{episode_id}/documents/work_order/versions/1",
                json={
                    "expected_version": 1,
                    "edited_by": "operator",
                    "idempotency_key": f"edit-{uuid4()}",
                    "title": "Pump room inspection order",
                    "body": "Check differential pressure trend and valve status.",
                    "actions": ["Inspect pump bearing temperature"],
                    "safety_notes": "Use lockout procedure before physical inspection.",
                    "evidence_ids": [f"episode:{episode_id}"],
                },
            )

            # Then: v2 is appended and queued for AI re-review.
            assert edited.status_code == 200
            second = edited.json()
            assert second["version"] == 2
            assert second["parent_document_version_id"] == first["document_version_id"]
            assert second["review_state"] == "pending_ai_review"

            # When: an operator adds only a review note.
            noted = await client.put(
                f"/api/incidents/{episode_id}/documents/work_order/versions/2",
                json={
                    "expected_version": 2,
                    "edited_by": "operator",
                    "idempotency_key": f"note-{uuid4()}",
                    "note": "현장 확인 전 전송 보류",
                },
            )

            # Then: no new version is created; only audit history changes.
            assert noted.status_code == 200
            assert noted.json()["version"] == 2
            page = await client.get(f"/api/incidents/{episode_id}/documents")
            assert page.status_code == 200
            versions = [
                item["version"]
                for item in page.json()["items"]
                if item["document_type"] == "work_order"
            ]
            assert versions == [2, 1]

            stale = await client.post(
                f"/api/incidents/{episode_id}/documents/work_order/approve",
                json={
                    "expected_version": 1,
                    "approved_by": "operator",
                    "idempotency_key": f"approve-stale-{uuid4()}",
                    "note": "stale approval",
                },
            )
            assert stale.status_code == 409

            approved = await client.post(
                f"/api/incidents/{episode_id}/documents/work_order/approve",
                json={
                    "expected_version": 2,
                    "approved_by": "operator",
                    "idempotency_key": f"approve-{uuid4()}",
                    "note": "approved for dispatch review",
                },
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "approved"

            after_approval = await client.put(
                f"/api/incidents/{episode_id}/documents/work_order/versions/2",
                json={
                    "expected_version": 2,
                    "edited_by": "operator",
                    "idempotency_key": f"post-approval-{uuid4()}",
                    "body": "mutate approved document",
                },
            )
            assert after_approval.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_incident_document_invalid_citation_and_missing_key_retryable_failure() -> None:
    from incident_document_repository import PostgresIncidentDocumentRepository
    from incident_document_routes import make_incident_document_router
    from settings import Settings

    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    app = FastAPI()
    app.include_router(
        make_incident_document_router(
            PostgresIncidentDocumentRepository(engine),
            settings=Settings(OPENAI_API_KEY=None),
        )
    )
    episode_id = await _seed_episode(engine)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Given: an operator cites evidence outside the incident context.
            invalid = await client.post(
                f"/api/incidents/{episode_id}/documents/work_order/generate",
                json={
                    "created_by": "operator",
                    "idempotency_key": f"invalid-{uuid4()}",
                    "evidence_ids": ["procedure:unknown"],
                },
            )

            # Then: the boundary rejects the unsupported citation.
            assert invalid.status_code == 422

            # When: model-backed generation is requested without an API key.
            failed = await client.post(
                f"/api/incidents/{episode_id}/documents/incident_report/generate",
                json={
                    "created_by": "operator",
                    "idempotency_key": f"missing-key-{uuid4()}",
                    "evidence_ids": [f"episode:{episode_id}"],
                },
            )

            # Then: a retryable failed version is visible and avoids repair-success claims.
            assert failed.status_code == 202
            body = failed.json()
            assert body["status"] == "failed"
            assert body["retryable"] is True
            assert "repair completed" not in body["content"]["body"].casefold()
            assert "restored" not in body["content"]["body"].casefold()
    finally:
        await engine.dispose()


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
