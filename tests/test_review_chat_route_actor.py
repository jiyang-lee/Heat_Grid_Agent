from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.routing import APIRoute


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))


def _endpoint(router, path: str, method: str = "POST"):
    return next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )


def test_mutating_routes_replace_client_actor_with_server_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import review_chat_routes
    from operations_policy_api_models import CurrentUserResponse
    from review_chat_api_models import (
        ReviewChatCancelRequest,
        ReviewChatConfirmRequest,
        ReviewChatConfirmationResponse,
        ReviewChatMessageRequest,
        ReviewChatOpenRequest,
    )
    from settings import Settings

    captured: dict[str, str] = {}

    async def fake_open(_engine, _run_id: str, request):
        captured["created_by_open"] = request.created_by
        return {"ok": True}

    async def fake_submit(_engine, _thread_id: str, request, **_kwargs):
        captured["created_by_message"] = request.created_by
        return {"ok": True}

    async def fake_confirm(_engine, proposal_id: str, request, **_kwargs):
        captured["confirmed_by"] = request.confirmed_by
        return (
            ReviewChatConfirmationResponse(
                proposal_id=proposal_id,
                status="cancelled",
            ),
            None,
        )

    async def fake_cancel(_engine, proposal_id: str, request):
        captured["cancelled_by"] = request.cancelled_by
        return ReviewChatConfirmationResponse(
            proposal_id=proposal_id,
            status="cancelled",
        )

    monkeypatch.setattr(review_chat_routes, "open_review_chat", fake_open)
    monkeypatch.setattr(review_chat_routes, "submit_review_chat_message", fake_submit)
    monkeypatch.setattr(review_chat_routes, "confirm_review_chat_proposal", fake_confirm)
    monkeypatch.setattr(review_chat_routes, "cancel_review_chat_proposal", fake_cancel)

    router = review_chat_routes.make_review_chat_router(object(), Settings())
    user = CurrentUserResponse(
        user_id="trusted-operator",
        display_name="운영자",
        capabilities=("admin",),
        auth_mode="fixed",
    )
    run_id = UUID("00000000-0000-0000-0000-000000000001")
    thread_id = UUID("00000000-0000-0000-0000-000000000002")
    proposal_id = UUID("00000000-0000-0000-0000-000000000003")

    async def exercise_routes() -> None:
        await _endpoint(
            router,
            "/api/agent-runs/{run_id}/review-chat/threads",
        )(
            run_id,
            ReviewChatOpenRequest(
                created_by="forged-admin",
                idempotency_key="open-key",
            ),
            user,
        )
        await _endpoint(
            router,
            "/api/review-chat/threads/{thread_id}/messages",
        )(
            thread_id,
            ReviewChatMessageRequest(
                content="안전 확인을 짧게 수정해줘",
                created_by="forged-admin",
                idempotency_key="message-key",
            ),
            user,
        )
        await _endpoint(
            router,
            "/api/review-chat/proposals/{proposal_id}/confirm",
        )(
            proposal_id,
            ReviewChatConfirmRequest(
                confirmed_by="forged-admin",
                idempotency_key="confirm-key",
                expected_proposal_status="awaiting_confirmation",
                expected_review_version=0,
            ),
            user,
        )
        await _endpoint(
            router,
            "/api/review-chat/proposals/{proposal_id}/cancel",
        )(
            proposal_id,
            ReviewChatCancelRequest(
                cancelled_by="forged-admin",
                idempotency_key="cancel-key",
            ),
            user,
        )

    asyncio.run(exercise_routes())

    assert captured == {
        "created_by_open": "trusted-operator",
        "created_by_message": "trusted-operator",
        "confirmed_by": "trusted-operator",
        "cancelled_by": "trusted-operator",
    }
