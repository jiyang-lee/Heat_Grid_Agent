from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Final

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import create_async_engine


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))


@pytest.mark.anyio
async def test_agent_run_list_returns_typed_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        AgentRunListItem,
        AgentRunListPage,
    )

    async def fake_list_agent_runs(_engine, _filters) -> AgentRunListPage:
        return AgentRunListPage(
            items=(
                AgentRunListItem(
                    run_id="00000000-0000-0000-0000-000000000002",
                    status="completed",
                    alert_id="00000000-0000-0000-0000-000000000003",
                    card_id="00000000-0000-0000-0000-000000000004",
                    priority="high",
                    operator_review_status="pending",
                    worker_status="completed",
                    review_snapshot_status="available",
                    created_at=datetime(2026, 7, 14, tzinfo=UTC),
                    updated_at=datetime(2026, 7, 14, tzinfo=UTC),
                ),
            ),
        )

    monkeypatch.setattr(agent_review_routes, "list_agent_runs", fake_list_agent_runs)
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/agent-runs", params={"status": "completed"})

    assert response.status_code == 200
    assert response.json()["items"][0]["review_snapshot_status"] == "available"
    await engine.dispose()


@pytest.mark.anyio
async def test_agent_run_list_rejects_malformed_cursor_without_querying_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    async def fail_list_agent_runs(_engine, _filters):
        raise AssertionError("repository must not be called")

    monkeypatch.setattr(agent_review_routes, "list_agent_runs", fail_list_agent_runs)
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/agent-runs", params={"cursor": "broken!"})

    assert response.status_code == 422
    assert response.json()["detail"] == "agent run cursor is malformed"
    await engine.dispose()


@pytest.mark.anyio
async def test_agent_run_list_rejects_naive_period_without_querying_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    async def fail_list_agent_runs(_engine, _filters):
        raise AssertionError("repository must not be called")

    monkeypatch.setattr(agent_review_routes, "list_agent_runs", fail_list_agent_runs)
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/agent-runs",
            params={
                "created_from": "2026-07-14T00:00:00",
                "created_to": "2026-07-15T00:00:00Z",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "created_from and created_to must include UTC offsets"
    await engine.dispose()


@pytest.mark.anyio
async def test_agent_run_review_returns_404_only_for_unknown_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    async def fake_get_review_snapshot(_engine, _run_id):
        return None

    monkeypatch.setattr(
        agent_review_routes,
        "get_review_snapshot",
        fake_get_review_snapshot,
    )
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/agent-runs/00000000-0000-0000-0000-000000000099/review"
        )

    assert response.status_code == 404
    await engine.dispose()


@pytest.mark.anyio
async def test_agent_run_review_rejects_malformed_uuid_without_querying_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    async def fail_get_review_snapshot(_engine, _run_id):
        raise AssertionError("repository must not be called")

    monkeypatch.setattr(
        agent_review_routes,
        "get_review_snapshot",
        fail_get_review_snapshot,
    )
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/agent-runs/not-a-uuid/review")

    assert response.status_code == 422
    await engine.dispose()


@pytest.mark.anyio
async def test_agent_run_evaluations_returns_typed_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        AgentRunEvaluationItem,
        AgentRunEvaluationPage,
    )

    async def fake_list_agent_run_evaluations(_engine, _filters) -> AgentRunEvaluationPage:
        return AgentRunEvaluationPage(
            items=(
                AgentRunEvaluationItem(
                    run_id="00000000-0000-0000-0000-000000000002",
                    status="completed",
                    alert_id="00000000-0000-0000-0000-000000000003",
                    card_id="00000000-0000-0000-0000-000000000004",
                    operator_review_status="pending",
                    worker_status="completed",
                    citation_coverage="complete",
                    input_validity="valid",
                    parent_handling="used_as_support",
                    evidence_completeness="complete",
                    review_snapshot_status="available",
                    created_at=datetime(2026, 7, 14, tzinfo=UTC),
                    updated_at=datetime(2026, 7, 14, tzinfo=UTC),
                ),
            ),
        )

    monkeypatch.setattr(
        agent_review_routes,
        "list_agent_run_evaluations",
        fake_list_agent_run_evaluations,
    )
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/agent-run-evaluations",
            params={"worker_status": "completed"},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["parent_handling"] == "used_as_support"
    await engine.dispose()


@pytest.mark.anyio
async def test_operator_review_submit_maps_stale_version_to_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    async def stale_submit_operator_review(_engine, _run_id, _request, **_kwargs):
        raise agent_review_routes.StaleReviewVersionError(
            run_id="00000000-0000-0000-0000-000000000002"
        )

    monkeypatch.setattr(
        agent_review_routes,
        "submit_operator_review",
        stale_submit_operator_review,
    )
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/agent-runs/00000000-0000-0000-0000-000000000002/reviews",
            json={
                "expected_review_version": 0,
                "idempotency_key": "submit-1",
                "decision": "approve",
                "reviewer": "operator",
                "reason": "confirmed",
                "disposition": "normal_observation",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "review version is stale"
    await engine.dispose()


@pytest.mark.anyio
async def test_policy_candidate_action_returns_404_for_unknown_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    async def missing_decide_policy_candidate(_engine, _candidate_id, _request, *, decision):
        return None

    monkeypatch.setattr(
        agent_review_routes,
        "decide_policy_candidate",
        missing_decide_policy_candidate,
    )
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/agent-policy-candidates/00000000-0000-0000-0000-000000000002/approve",
            json={
                "expected_version": 1,
                "reviewer": "operator",
                "reason": "approved",
            },
        )

    assert response.status_code == 404
    await engine.dispose()
