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
