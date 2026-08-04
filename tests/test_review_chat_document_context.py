from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
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
async def test_route_accepts_an_explicit_historical_document_as_the_revision_parent() -> None:
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

        assert response.status_code == 202
        proposal = response.json()["proposal"]
        assert proposal["base_document_version_id"] == stale["document_version_id"]
        assert proposal["base_document_version"] == 1
        assert proposal["correction"]["latest_version_at_proposal"] == "2"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_confirmation_marks_a_proposal_stale_when_a_new_document_appears() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, episode_id = await _seed_run(engine)
        document = await _insert_document(engine, episode_id, 1, "proposal base body")
        thread_id = await _open_thread(app, run_id)
        submitted = await _submit(
            app,
            thread_id,
            {
                "content": "안전 확인 항목을 더 자세하게 수정해줘",
                "created_by": "operator",
                "idempotency_key": f"stale-proposal-{uuid4()}",
                "incident_id": episode_id,
                "document_context": {
                    "document_version_id": document["document_version_id"],
                    "expected_version": 1,
                },
            },
        )
        assert submitted.status_code == 202
        proposal = submitted.json()["proposal"]
        await _insert_document(engine, episode_id, 2, "newer body")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            confirmed = await client.post(
                f"/api/review-chat/proposals/{proposal['proposal_id']}/confirm",
                json={
                    "confirmed_by": "operator",
                    "idempotency_key": f"stale-confirm-{uuid4()}",
                    "expected_proposal_status": "awaiting_confirmation",
                    "expected_review_version": proposal["expected_review_version"],
                },
            )
            pending = await client.get(
                f"/api/review-chat/threads/{thread_id}/proposals/pending"
            )
        assert confirmed.status_code == 409
        assert pending.status_code == 200
        assert pending.json()["items"] == []
        async with engine.connect() as connection:
            status = await connection.scalar(
                text(
                    "SELECT status FROM review_chat_action_proposals "
                    "WHERE proposal_id = :proposal_id"
                ),
                {"proposal_id": proposal["proposal_id"]},
            )
        assert status == "stale"
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


@pytest.mark.anyio
async def test_explicit_rag_reevaluation_is_blocked_without_creating_a_document_version() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, _, _ = await _seed_legacy_run(engine)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            opened = await client.post(
                f"/api/agent-runs/{run_id}/review-chat/threads",
                json={"created_by": "operator", "idempotency_key": f"open-{uuid4()}"},
            )
            assert opened.status_code == 200
            thread = opened.json()
            submitted = await client.post(
                f"/api/review-chat/threads/{thread['thread_id']}/messages",
                json={
                    "content": "RAG 문서를 다시 검색해줘",
                    "created_by": "operator",
                    "idempotency_key": f"rag-message-{uuid4()}",
                    "incident_id": thread["incident_id"],
                    "document_context": {
                        "document_version_id": thread["document_version_id"],
                        "expected_version": 1,
                    },
                },
            )
            assert submitted.status_code == 202
            proposal = submitted.json()["proposal"]
            assert proposal["next_action"] == "targeted_rerun"
            assert proposal["target_stage"] == "rag_retrieval"
            assert proposal["draft_content"] is None

            confirmed = await client.post(
                f"/api/review-chat/proposals/{proposal['proposal_id']}/confirm",
                json={
                    "confirmed_by": "operator",
                    "idempotency_key": f"rag-confirm-{uuid4()}",
                    "expected_proposal_status": "awaiting_confirmation",
                    "expected_review_version": proposal["expected_review_version"],
                },
            )
            assert confirmed.status_code == 200
            confirmation = confirmed.json()
            assert confirmation["child_run_id"] is None
            assert confirmation["document_version_id"] is None
            assert confirmation["blocked_reason"] == "blocked_legacy_input_unavailable"

        async with engine.connect() as connection:
            version_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM incident_document_versions "
                    "WHERE episode_id = :episode_id AND document_type = 'work_order'"
                ),
                {"episode_id": thread["incident_id"]},
            )
        assert version_count == 1
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_legacy_run_bootstraps_document_recovers_proposal_and_persists_v2_v3() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        app = _app(engine)
        run_id, alert_id, card_id = await _seed_legacy_run(engine)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            opened = await client.post(
                f"/api/agent-runs/{run_id}/review-chat/threads",
                json={"created_by": "operator", "idempotency_key": f"open-{uuid4()}"},
            )
            assert opened.status_code == 200
            thread = opened.json()
            assert thread["incident_id"] is not None
            assert thread["document_version"] == 1
            assert "안전 확인" in thread["document_content"]

            child_run_id = await _insert_child_run(engine, run_id, alert_id, card_id)
            child_opened = await client.post(
                f"/api/agent-runs/{child_run_id}/review-chat/threads",
                json={"created_by": "operator", "idempotency_key": f"child-open-{uuid4()}"},
            )
            assert child_opened.status_code == 200
            assert child_opened.json()["thread_id"] == thread["thread_id"]
            assert child_opened.json()["run_id"] == run_id

            message_key = f"message-{uuid4()}"
            message_payload = {
                "content": "안전 확인 2번째 항목만 최신 보호구 기준으로 수정해줘",
                "created_by": "operator",
                "idempotency_key": message_key,
                "incident_id": thread["incident_id"],
                "document_context": {
                    "document_version_id": thread["document_version_id"],
                    "expected_version": 1,
                },
            }
            submitted = await client.post(
                f"/api/review-chat/threads/{thread['thread_id']}/messages",
                json=message_payload,
            )
            assert submitted.status_code == 202
            proposal = submitted.json()["proposal"]
            assert proposal["draft_content"] != thread["document_content"]
            assert proposal["change_summary"] == message_payload["content"]

            retried = await client.post(
                f"/api/review-chat/threads/{thread['thread_id']}/messages",
                json=message_payload,
            )
            assert retried.status_code == 202
            assert retried.json()["proposal"]["proposal_id"] == proposal["proposal_id"]
            pending = await client.get(
                f"/api/review-chat/threads/{thread['thread_id']}/proposals/pending"
            )
            assert pending.status_code == 200
            assert [item["proposal_id"] for item in pending.json()["items"]] == [proposal["proposal_id"]]

            confirmed_v2 = await client.post(
                f"/api/review-chat/proposals/{proposal['proposal_id']}/confirm",
                json={
                    "confirmed_by": "operator",
                    "idempotency_key": f"confirm-v2-{uuid4()}",
                    "expected_proposal_status": "awaiting_confirmation",
                    "expected_review_version": proposal["expected_review_version"],
                },
            )
            assert confirmed_v2.status_code == 200
            v2 = confirmed_v2.json()
            assert v2["document_version"] == 2
            assert v2["document_version_id"] is not None
            assert v2["child_run_id"] is None
            assert v2["blocked_reason"] is None
            retried_after_context_change = await client.post(
                f"/api/review-chat/threads/{thread['thread_id']}/messages",
                json=message_payload,
            )
            assert retried_after_context_change.status_code == 202
            assert retried_after_context_change.json()["proposal"]["status"] == "executed"

            selected_v1 = await client.post(
                f"/api/review-chat/threads/{thread['thread_id']}/messages",
                json={
                    "content": "작업 절차 1번째 항목만 더 짧게 수정해줘",
                    "created_by": "operator",
                    "idempotency_key": f"branch-message-{uuid4()}",
                    "incident_id": thread["incident_id"],
                    "document_context": {
                        "document_version_id": thread["document_version_id"],
                        "expected_version": 1,
                    },
                },
            )
            assert selected_v1.status_code == 202
            branch_proposal = selected_v1.json()["proposal"]
            confirmed_v3 = await client.post(
                f"/api/review-chat/proposals/{branch_proposal['proposal_id']}/confirm",
                json={
                    "confirmed_by": "operator",
                    "idempotency_key": f"confirm-v3-{uuid4()}",
                    "expected_proposal_status": "awaiting_confirmation",
                    "expected_review_version": branch_proposal["expected_review_version"],
                },
            )
            assert confirmed_v3.status_code == 200
            v3 = confirmed_v3.json()
            assert v3["document_version"] == 3

            over_limit = await client.post(
                f"/api/review-chat/threads/{thread['thread_id']}/messages",
                json={
                    "content": "제목만 간결하게 수정해줘",
                    "created_by": "operator",
                    "idempotency_key": f"limit-message-{uuid4()}",
                    "incident_id": thread["incident_id"],
                    "document_context": {
                        "document_version_id": v3["document_version_id"],
                        "expected_version": 3,
                    },
                },
            )
            limit_proposal = over_limit.json()["proposal"]
            limited = await client.post(
                f"/api/review-chat/proposals/{limit_proposal['proposal_id']}/confirm",
                json={
                    "confirmed_by": "operator",
                    "idempotency_key": f"confirm-limit-{uuid4()}",
                    "expected_proposal_status": "awaiting_confirmation",
                    "expected_review_version": limit_proposal["expected_review_version"],
                },
            )
            assert limited.status_code == 200
            assert limited.json()["blocked_reason"] == "document_version_limit_reached"
            assert limited.json()["incident_id"] == thread["incident_id"]
            assert limited.json()["document_version_id"] is None

        async with engine.connect() as connection:
            episode = await connection.execute(
                text(
                    "SELECT e.stream_key, q.episode_id::text AS episode_id "
                    "FROM ops_alert_queue q JOIN anomaly_episodes e ON e.episode_id = q.episode_id "
                    "WHERE q.alert_id = :alert_id"
                ),
                {"alert_id": alert_id},
            )
            episode_row = episode.mappings().one()
            versions = await connection.execute(
                text(
                    "SELECT version, parent_document_version_id::text AS parent_id, "
                    "CAST(content AS text) AS content "
                    "FROM incident_document_versions WHERE episode_id = :episode_id "
                    "AND document_type = 'work_order' ORDER BY version"
                ),
                {"episode_id": episode_row["episode_id"]},
            )
            version_rows = versions.mappings().all()
        assert episode_row["stream_key"] == f"review-chat:{alert_id}"
        assert [row["version"] for row in version_rows] == [1, 2, 3]
        assert version_rows[2]["parent_id"] == thread["document_version_id"]
        v2_content = json.loads(version_rows[1]["content"])
        v3_content = json.loads(version_rows[2]["content"])
        assert "최신 보호구 기준" in v2_content["safety_notes"]
        assert all(
            item in v2_content["body"]
            for item in v2_content["safety_notes"].splitlines()
        )
        assert v3_content["actions"]
        assert v3_content["actions"][0] in v3_content["body"]

        depth_two_run_id = await _insert_child_run(
            engine,
            child_run_id,
            alert_id,
            card_id,
            root_run_id=run_id,
            lineage_depth=2,
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE agent_runs SET updated_at = now() + interval '1 minute' "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        rollover_run_id = str(uuid4())
        from agent_run_repository import reserve_agent_run

        _, rollover_created = await reserve_agent_run(
            engine,
            run_id=rollover_run_id,
            alert_id=alert_id,
            card_id=card_id,
            force_new=True,
            requested_by="operator",
        )
        async with engine.connect() as connection:
            rollover = await connection.execute(
                text(
                    "SELECT parent_run_id::text AS parent_run_id, root_run_id::text AS root_run_id, "
                    "lineage_depth, trigger_type FROM agent_runs WHERE run_id = :run_id"
                ),
                {"run_id": rollover_run_id},
            )
            rollover_row = rollover.mappings().one()
        assert depth_two_run_id != rollover_run_id
        assert rollover_created is True
        assert rollover_row["parent_run_id"] is None
        assert rollover_row["root_run_id"] == rollover_run_id
        assert rollover_row["lineage_depth"] == 0
        assert rollover_row["trigger_type"] == "manual_rerun_rollover"
    finally:
        await engine.dispose()


def _app(engine: AsyncEngine) -> FastAPI:
    from review_chat_routes import make_review_chat_router
    from settings import Settings

    app = FastAPI()
    app.include_router(make_review_chat_router(engine, settings=Settings(OPENAI_API_KEY=None)))
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


async def _seed_legacy_run(engine: AsyncEngine) -> tuple[str, str, str]:
    ids = {name: str(uuid4()) for name in ("run_id", "alert_id", "card_id", "decision_id")}
    output = {
        "headline": "레거시 AI 작업지시서",
        "situation": "변전 설비의 온도 이상이 반복 감지되었습니다.",
        "evidence": [
            {"label": "온도 추세", "content": "최근 3개 구간에서 기준치를 초과했습니다."},
        ],
        "actions": [
            {"title": "현장 점검", "detail": "해당 설비의 발열 부위를 확인합니다."},
        ],
        "cautions": [
            "절연 보호구를 착용합니다.",
            "최신 보호구 기준을 확인합니다.",
        ],
    }
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
                "priority_level, enqueue_reason"
                ") SELECT :alert_id, :card_id, windows.substation_uid, windows.manufacturer_id, "
                "windows.substation_id, 'high', 'legacy review chat bootstrap test' "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id"
            ),
            ids,
        )
        await connection.execute(
            text(
                "INSERT INTO agent_runs ("
                "run_id, alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
                "root_run_id, lineage_depth, status, ops_output, input_snapshot_origin, "
                "input_snapshot_status"
                ") SELECT :run_id, :alert_id, :card_id, windows.substation_uid, "
                "windows.manufacturer_id, windows.substation_id, :run_id, 0, 'completed', "
                "CAST(:ops_output AS jsonb), 'legacy_v1', 'unavailable' "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id"
            ),
            {**ids, "ops_output": json.dumps(output, ensure_ascii=False)},
        )
    return ids["run_id"], ids["alert_id"], ids["card_id"]


async def _insert_child_run(
    engine: AsyncEngine,
    parent_run_id: str,
    alert_id: str,
    card_id: str,
    *,
    root_run_id: str | None = None,
    lineage_depth: int = 1,
) -> str:
    child_run_id = str(uuid4())
    root_run_id = root_run_id or parent_run_id
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO agent_runs ("
                "run_id, alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
                "parent_run_id, root_run_id, lineage_depth, trigger_type, status, ops_output, "
                "input_snapshot_origin, input_snapshot_status"
                ") SELECT :run_id, :alert_id, :card_id, q.substation_uid, q.manufacturer_id, "
                "q.substation_id, :parent_run_id, :root_run_id, :lineage_depth, 'targeted_rerun', "
                "'completed', CAST('{\"summary\":\"child review chat run\"}' AS jsonb), "
                "'legacy_v1', 'unavailable' FROM ops_alert_queue q WHERE q.alert_id = :alert_id"
            ),
            {
                "run_id": child_run_id,
                "alert_id": alert_id,
                "card_id": card_id,
                "parent_run_id": parent_run_id,
                "root_run_id": root_run_id,
                "lineage_depth": lineage_depth,
            },
        )
    return child_run_id


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
