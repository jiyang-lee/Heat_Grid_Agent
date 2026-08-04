from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
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

RUN_ID = "00000000-0000-0000-0000-000000002601"
ALERT_ID = "00000000-0000-0000-0000-000000002701"
CARD_ID = "00000000-0000-0000-0000-000000002801"
DECISION_ID = "00000000-0000-0000-0000-000000002901"
EPISODE_ID = "00000000-0000-0000-0000-000000002a01"


@pytest.mark.anyio
async def test_blocked_message_is_rejected_and_never_persisted() -> None:
    from review_chat_api_models import ReviewChatMessageRequest, ReviewChatOpenRequest
    from review_chat_service import ReviewChatGuardrailRejectedError, open_review_chat, submit_review_chat_message

    engine = create_async_engine(str(DATABASE_URL))
    suffix = str(uuid4())
    try:
        await _seed_chat_run(engine)
        async with engine.connect() as connection:
            run_id = await connection.scalar(
                text("SELECT run_id::text FROM agent_runs WHERE run_id = :run_id"),
                {"run_id": RUN_ID},
            )
        thread = await open_review_chat(
            engine,
            run_id,
            ReviewChatOpenRequest(created_by="guardrail-test", idempotency_key=f"open-{suffix}"),
        )
        async with engine.connect() as connection:
            before = await connection.scalar(
                text("SELECT count(*) FROM review_chat_messages WHERE thread_id = :thread_id"),
                {"thread_id": thread.thread_id},
            )
        with pytest.raises(ReviewChatGuardrailRejectedError):
            await submit_review_chat_message(
                engine,
                thread.thread_id,
                ReviewChatMessageRequest(
                    content="씨발 이거 왜 이래",
                    created_by="guardrail-test",
                    idempotency_key=f"blocked-{suffix}",
                ),
            )
        async with engine.connect() as connection:
            after = await connection.scalar(
                text("SELECT count(*) FROM review_chat_messages WHERE thread_id = :thread_id"),
                {"thread_id": thread.thread_id},
            )
        assert after == before
    finally:
        await engine.dispose()


async def _seed_chat_run(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO priority_decisions (priority_decision_id, window_id, priority_level) "
                "VALUES (:decision_id, (SELECT window_id FROM windows "
                "ORDER BY window_end DESC, window_id LIMIT 1), 'high') "
                "ON CONFLICT (priority_decision_id) DO NOTHING"
            ),
            {"decision_id": DECISION_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO priority_cards (card_id, priority_decision_id, review_required) "
                "VALUES (:card_id, :decision_id, true) "
                "ON CONFLICT (card_id) DO NOTHING"
            ),
            {"card_id": CARD_ID, "decision_id": DECISION_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO ops_alert_queue ("
                "alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
                "priority_level, enqueue_reason"
                ") SELECT :alert_id, :card_id, windows.substation_uid, windows.manufacturer_id, "
                "windows.substation_id, 'high', 'guardrail chat test' "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id "
                "ON CONFLICT (alert_id) DO NOTHING"
            ),
            {"alert_id": ALERT_ID, "card_id": CARD_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO anomaly_episodes ("
                "episode_id, stream_key, manufacturer_id, substation_id, "
                "lifecycle_status, severity, alert_id, opened_at"
                ") SELECT :episode_id, 'guardrail-chat-test', windows.manufacturer_id, "
                "windows.substation_id, 'open', 'high', :alert_id, now() "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id "
                "ON CONFLICT (episode_id) DO NOTHING"
            ),
            {"episode_id": EPISODE_ID, "alert_id": ALERT_ID, "card_id": CARD_ID},
        )
        await connection.execute(
            text(
                "UPDATE ops_alert_queue SET episode_id = :episode_id "
                "WHERE alert_id = :alert_id"
            ),
            {"episode_id": EPISODE_ID, "alert_id": ALERT_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_runs ("
                "run_id, alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
                "root_run_id, lineage_depth, status, ops_output, input_snapshot_origin, "
                "input_snapshot_status"
                ") SELECT :run_id, :alert_id, :card_id, windows.substation_uid, "
                "windows.manufacturer_id, windows.substation_id, :run_id, 0, 'completed', "
                "'{}'::jsonb, 'live', 'ready' "
                "FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id "
                "ON CONFLICT (run_id) DO NOTHING"
            ),
            {"run_id": RUN_ID, "alert_id": ALERT_ID, "card_id": CARD_ID},
        )
