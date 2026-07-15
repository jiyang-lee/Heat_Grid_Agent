from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
DATABASE_URL = os.getenv("HEATGRID_REVIEW_CHAT_TEST_DATABASE_URL")
sys.path.insert(0, str(BACKEND))

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
        async with engine.connect() as connection:
            run_id = await connection.scalar(
                text("SELECT run_id::text FROM agent_runs ORDER BY created_at LIMIT 1")
            )
            assert isinstance(run_id, str)
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
