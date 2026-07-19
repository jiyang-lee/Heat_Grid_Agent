from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
DATABASE_URL = os.getenv("HEATGRID_REVIEW_CHAT_TEST_DATABASE_URL")
sys.path.insert(0, str(BACKEND))

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="HEATGRID_REVIEW_CHAT_TEST_DATABASE_URL is required",
)


@pytest.mark.anyio
async def test_route_rejects_fabricated_document_body_and_base_version() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, episode_id = await _seed_run(engine)
        document = await _insert_document(engine, episode_id, 1, "stored work order body")
        thread_id = await _open_thread(app, run_id)

        response = await _submit(
            app,
            thread_id,
            {
                "content": "위험성 및 근거를 더 자세하게 보강해줘",
                "created_by": "operator",
                "idempotency_key": f"fabricated-{uuid4()}",
                "incident_id": episode_id,
                "document_context": {
                    "document_version_id": document["document_version_id"],
                    "expected_version": 1,
                    "base_version": "999",
                    "current_body": "fabricated body",
                },
            },
        )

        assert response.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_route_rejects_nonexistent_document_version() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, episode_id = await _seed_run(engine)
        thread_id = await _open_thread(app, run_id)

        response = await _submit(
            app,
            thread_id,
            {
                "content": "위험성 및 근거를 더 자세하게 보강해줘",
                "created_by": "operator",
                "idempotency_key": f"missing-document-{uuid4()}",
                "incident_id": episode_id,
                "document_context": {
                    "document_version_id": str(uuid4()),
                    "expected_version": 1,
                },
            },
        )

        assert response.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_route_rejects_foreign_incident_document_version() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, episode_id = await _seed_run(engine)
        foreign_episode_id = await _insert_episode(engine)
        foreign = await _insert_document(engine, foreign_episode_id, 1, "foreign document body")
        thread_id = await _open_thread(app, run_id)

        response = await _submit(
            app,
            thread_id,
            {
                "content": "위험성 및 근거를 더 자세하게 보강해줘",
                "created_by": "operator",
                "idempotency_key": f"foreign-document-{uuid4()}",
                "incident_id": episode_id,
                "document_context": {
                    "document_version_id": foreign["document_version_id"],
                    "expected_version": 1,
                },
            },
        )

        assert response.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_route_rejects_stale_document_version() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, episode_id = await _seed_run(engine)
        stale = await _insert_document(engine, episode_id, 1, "stale work order body")
        await _insert_document(engine, episode_id, 2, "current work order body")
        thread_id = await _open_thread(app, run_id)

        response = await _submit(
            app,
            thread_id,
            {
                "content": "위험성 및 근거를 더 자세하게 보강해줘",
                "created_by": "operator",
                "idempotency_key": f"stale-document-{uuid4()}",
                "incident_id": episode_id,
                "document_context": {
                    "document_version_id": stale["document_version_id"],
                    "expected_version": 1,
                },
            },
        )

        assert response.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_route_creates_proposal_from_canonical_document_context() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, episode_id = await _seed_run(engine)
        document = await _insert_document(engine, episode_id, 1, "canonical stored work order body")
        thread_id = await _open_thread(app, run_id)

        response = await _submit(
            app,
            thread_id,
            {
                "content": "위험성 및 근거를 더 자세하게 보강해줘",
                "created_by": "operator",
                "idempotency_key": f"valid-document-{uuid4()}",
                "incident_id": episode_id,
                "document_context": {
                    "document_version_id": document["document_version_id"],
                    "expected_version": 1,
                },
            },
        )
        body = response.json()
        correction = body["proposal"]["correction"]
        operator_payload = body["operator_message"]["structured_payload"]["document_context"]

        assert response.status_code == 202
        assert correction["document_version_id"] == document["document_version_id"]
        assert correction["base_content_hash"] == document["content_hash"]
        assert correction["current_body"] == "canonical stored work order body"
        assert correction["base_version"] == "1"
        assert operator_payload["document_version_id"] == document["document_version_id"]
        assert operator_payload["content_hash"] == document["content_hash"]
        assert body["operator_message"]["citations"][0]["document_version_id"] == document["document_version_id"]
    finally:
        await engine.dispose()


def _app(engine: AsyncEngine) -> FastAPI:
    from review_chat_routes import make_review_chat_router
    from settings import Settings

    app = FastAPI()
    app.include_router(make_review_chat_router(engine, settings=Settings(OPENAI_API_KEY=SecretStr("test-key"))))
    return app


async def _open_thread(app: FastAPI, run_id: str) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/agent-runs/{run_id}/review-chat/threads",
            json={"created_by": "operator", "idempotency_key": f"open-{uuid4()}"},
        )
    assert response.status_code == 200
    thread_id = response.json()["thread_id"]
    assert isinstance(thread_id, str)
    return thread_id


async def _submit(app: FastAPI, thread_id: str, payload: dict[str, object]) -> Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(f"/api/review-chat/threads/{thread_id}/messages", json=payload)


async def _seed_run(engine: AsyncEngine) -> tuple[str, str]:
    ids = {name: str(uuid4()) for name in ("run_id", "alert_id", "card_id", "decision_id")}
    episode_id = await _insert_episode(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO priority_decisions (priority_decision_id, window_id, priority_level) "
                "VALUES (:decision_id, (SELECT window_id FROM windows "
                "ORDER BY window_end DESC, window_id LIMIT 1), 'high')"
            ),
            ids,
        )
        await connection.execute(
            text(
                "INSERT INTO priority_cards (card_id, priority_decision_id, review_required) "
                "VALUES (:card_id, :decision_id, true)"
            ),
            ids,
        )
        await connection.execute(
            text(
                "INSERT INTO ops_alert_queue ("
                "alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
                "priority_level, enqueue_reason, episode_id"
                ") SELECT :alert_id, :card_id, windows.substation_uid, windows.manufacturer_id, "
                "windows.substation_id, 'high', 'review chat document test', :episode_id "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id"
            ),
            {**ids, "episode_id": episode_id},
        )
        await connection.execute(
            text(
                "UPDATE anomaly_episodes SET alert_id = :alert_id "
                "WHERE episode_id = :episode_id"
            ),
            {**ids, "episode_id": episode_id},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_runs ("
                "run_id, alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
                "root_run_id, lineage_depth, status, ops_output, input_snapshot_origin, "
                "input_snapshot_status"
                ") SELECT :run_id, :alert_id, :card_id, windows.substation_uid, "
                "windows.manufacturer_id, windows.substation_id, :run_id, 0, 'completed', "
                "CAST('{\"summary\":\"review chat document context\"}' AS jsonb), "
                "'native_v2', 'unavailable' "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id"
            ),
            ids,
        )
    return ids["run_id"], episode_id


async def _insert_episode(engine: AsyncEngine) -> str:
    episode_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO anomaly_episodes ("
                "episode_id, stream_key, manufacturer_id, substation_id, "
                "lifecycle_status, severity, alert_id, opened_at"
                ") SELECT :episode_id, :stream_key, windows.manufacturer_id, "
                "windows.substation_id, 'open', 'high', :alert_id, now() "
                "FROM windows ORDER BY window_end DESC, window_id LIMIT 1"
            ),
            {"episode_id": episode_id, "stream_key": f"review-chat-document:{uuid4()}", "alert_id": str(uuid4())},
        )
    return episode_id


async def _insert_document(
    engine: AsyncEngine,
    episode_id: str,
    version: int,
    body: str,
) -> dict[str, str]:
    from incident_document_content import dump_json, hash_json

    content: dict[str, object] = {
        "title": "Work order",
        "body": body,
        "actions": ["inspect affected machine room"],
        "evidence": [{"citation_id": f"episode:{episode_id}", "label": "Anomaly episode evidence"}],
        "safety_notes": "Follow field safety procedure.",
    }
    content_hash = hash_json(content)
    async with engine.begin() as connection:
        parent_document_version_id = None
        if version > 1:
            parent_document_version_id = await connection.scalar(
                text(
                    "SELECT document_version_id::text FROM incident_document_versions "
                    "WHERE episode_id = :episode_id AND document_type = 'work_order' "
                    "AND version = :version"
                ),
                {"episode_id": episode_id, "version": version - 1},
            )
        assert version == 1 or isinstance(parent_document_version_id, str)
        document_version_id = await connection.scalar(
            text(
                "INSERT INTO incident_document_versions ("
                "document_version_id, episode_id, document_type, version, "
                "parent_document_version_id, status, content, content_hash, created_by"
                ") VALUES (:document_version_id, :episode_id, 'work_order', :version, "
                ":parent_document_version_id, 'draft', CAST(:content AS jsonb), :content_hash, 'operator') "
                "RETURNING document_version_id::text"
            ),
            {
                "document_version_id": str(uuid4()),
                "episode_id": episode_id,
                "version": version,
                "parent_document_version_id": parent_document_version_id,
                "content": dump_json(content),
                "content_hash": content_hash,
            },
        )
    assert isinstance(document_version_id, str)
    return {"document_version_id": document_version_id, "content_hash": content_hash}
