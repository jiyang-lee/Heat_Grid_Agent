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

RUN_ID = "00000000-0000-0000-0000-000000002101"
ALERT_ID = "00000000-0000-0000-0000-000000002201"
CARD_ID = "00000000-0000-0000-0000-000000002301"
DECISION_ID = "00000000-0000-0000-0000-000000002401"
EPISODE_ID = "00000000-0000-0000-0000-000000002501"

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="HEATGRID_REVIEW_CHAT_TEST_DATABASE_URL is required",
)


@pytest.mark.anyio
async def test_proposal_does_not_write_a_review_until_confirmation() -> None:
    from review_chat_api_models import (
        ReviewChatConfirmRequest,
        ReviewChatMessageRequest,
        ReviewChatOpenRequest,
    )
    from review_chat_service import (
        confirm_review_chat_proposal,
        open_review_chat,
        submit_review_chat_message,
    )

    engine = create_async_engine(str(DATABASE_URL))
    suffix = str(uuid4())
    try:
        await _seed_chat_run(engine)
        async with engine.connect() as connection:
            run_id = await connection.scalar(
                text("SELECT run_id::text FROM agent_runs WHERE run_id = :run_id"),
                {"run_id": RUN_ID},
            )
            assert run_id == RUN_ID
            before = await connection.scalar(
                text("SELECT count(*) FROM agent_run_reviews WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        thread = await open_review_chat(
            engine,
            run_id,
            ReviewChatOpenRequest(
                created_by="chat-test",
                idempotency_key=f"open-{suffix}",
            ),
        )
        cited = await submit_review_chat_message(
            engine,
            thread.thread_id,
            ReviewChatMessageRequest(
                content="이 사건 근거를 요약해줘",
                created_by="chat-test",
                idempotency_key=f"incident-citation-{suffix}",
                incident_id=EPISODE_ID,
                citation_ids=(f"episode:{EPISODE_ID}",),
            ),
        )
        assert cited.operator_message.structured_payload["incident_id"] == EPISODE_ID
        assert cited.operator_message.structured_payload["citation_ids"] == [
            f"episode:{EPISODE_ID}"
        ]
        async with engine.connect() as connection:
            proposals_before = await connection.scalar(
                text(
                    "SELECT count(*) FROM review_chat_action_proposals "
                    "WHERE thread_id = :thread_id"
                ),
                {"thread_id": thread.thread_id},
            )
        submission = await submit_review_chat_message(
            engine,
            thread.thread_id,
            ReviewChatMessageRequest(
                content="거절. RAG 문서가 현재 설비와 관련 없습니다.",
                created_by="chat-test",
                idempotency_key=f"message-{suffix}",
            ),
        )
        assert submission.proposal is not None
        async with engine.connect() as connection:
            proposal_count = await connection.scalar(
                text("SELECT count(*) FROM review_chat_action_proposals WHERE thread_id = :thread_id"),
                {"thread_id": thread.thread_id},
            )
            before_confirm = await connection.scalar(
                text("SELECT count(*) FROM agent_run_reviews WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        assert proposal_count == proposals_before + 1
        assert before_confirm == before

        confirmation, _child = await confirm_review_chat_proposal(
            engine,
            submission.proposal.proposal_id,
            ReviewChatConfirmRequest(
                confirmed_by="chat-test",
                idempotency_key=f"confirm-{suffix}",
                expected_proposal_status="awaiting_confirmation",
                expected_review_version=submission.proposal.expected_review_version,
            ),
            rag_quality_enabled=False,
        )
        repeated, _child = await confirm_review_chat_proposal(
            engine,
            submission.proposal.proposal_id,
            ReviewChatConfirmRequest(
                confirmed_by="chat-test",
                idempotency_key=f"confirm-repeat-{suffix}",
                expected_proposal_status="awaiting_confirmation",
                expected_review_version=submission.proposal.expected_review_version,
            ),
            rag_quality_enabled=False,
        )
        async with engine.connect() as connection:
            after = await connection.scalar(
                text("SELECT count(*) FROM agent_run_reviews WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        assert confirmation.status == "executed"
        assert repeated.review_id == confirmation.review_id
        assert after == before + 1
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_followup_message_reuses_the_previous_operator_scope() -> None:
    from review_chat_api_models import (
        ReviewChatCancelRequest,
        ReviewChatMessageRequest,
        ReviewChatOpenRequest,
    )
    from review_chat_service import (
        cancel_review_chat_proposal,
        list_review_chat_messages,
        open_review_chat,
        submit_review_chat_message,
    )

    engine = create_async_engine(str(DATABASE_URL))
    suffix = str(uuid4())
    try:
        await _seed_chat_run(engine)
        thread = await open_review_chat(
            engine,
            RUN_ID,
            ReviewChatOpenRequest(created_by="chat-test", idempotency_key=f"followup-open-{suffix}"),
        )
        earlier_question = "현재 최종 결과가 뭐야?"
        explained = await submit_review_chat_message(
            engine,
            thread.thread_id,
            ReviewChatMessageRequest(
                content=earlier_question,
                created_by="chat-test",
                idempotency_key=f"followup-question-{suffix}",
            ),
        )
        assert explained.proposal is None
        first = await submit_review_chat_message(
            engine,
            thread.thread_id,
            ReviewChatMessageRequest(
                content=f"안전 확인 2번째 항목만 보호구 기준으로 수정해줘 {suffix}",
                created_by="chat-test",
                idempotency_key=f"followup-first-{suffix}",
            ),
        )
        assert first.proposal is not None
        await cancel_review_chat_proposal(
            engine,
            first.proposal.proposal_id,
            ReviewChatCancelRequest(cancelled_by="chat-test", idempotency_key=f"followup-cancel-{suffix}"),
        )

        followup_content = "그 항목을 조금 더 짧게 정리해줘"
        followup = await submit_review_chat_message(
            engine,
            thread.thread_id,
            ReviewChatMessageRequest(
                content=followup_content,
                created_by="chat-test",
                idempotency_key=f"followup-second-{suffix}",
            ),
        )

        assert followup.proposal is not None
        assert followup.proposal.reason == followup_content
        assert followup.proposal.correction is not None
        assert "안전 확인 2번째 항목" in followup.proposal.correction["instruction"]
        assert followup_content in followup.proposal.correction["instruction"]
        recalled = await submit_review_chat_message(
            engine,
            thread.thread_id,
            ReviewChatMessageRequest(
                content="방금 뭐라고 수정해 달라고 했어?",
                created_by="chat-test",
                idempotency_key=f"followup-recall-{suffix}",
            ),
        )
        assert recalled.proposal is None
        assert earlier_question in recalled.assistant_message.content
        assert "안전 확인 2번째 항목" in recalled.assistant_message.content
        assert followup_content in recalled.assistant_message.content
        messages = await list_review_chat_messages(engine, thread.thread_id, after_sequence=0, limit=100)
        assert any(
            message.role == "operator" and message.content == followup_content
            for message in messages.items
        )
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
                "windows.substation_id, 'high', 'review chat test' "
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
                ") SELECT :episode_id, 'review-chat-test', windows.manufacturer_id, "
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
                "CAST('{\"summary\":\"review chat parent\"}' AS jsonb), 'native_v2', 'unavailable'"
                " FROM priority_cards JOIN priority_decisions USING (priority_decision_id) "
                "JOIN windows USING (window_id) WHERE card_id = :card_id "
                "ON CONFLICT (run_id) DO NOTHING"
            ),
            {"run_id": RUN_ID, "alert_id": ALERT_ID, "card_id": CARD_ID},
        )
