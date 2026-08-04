from __future__ import annotations

from importlib import import_module
import sys
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

demo_ai_history_routes = import_module("demo_ai_history_routes")


class _ResetResult:
    def __init__(self, value: int = 0) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class _ResetConnection:
    def __init__(self, *, active_runs: int = 0) -> None:
        self.statements: list[str] = []
        self.active_runs = active_runs

    async def __aenter__(self) -> _ResetConnection:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: object) -> _ResetResult:
        query = str(statement)
        self.statements.append(query)
        if "WHERE status IN ('queued', 'running')" in query:
            return _ResetResult(self.active_runs)
        if "count(*) FROM public.agent_runs" in query:
            return _ResetResult(3)
        if "count(*) FROM public.review_chat_messages" in query:
            return _ResetResult(5)
        if "count(*) FROM public.agent_run_artifacts" in query:
            return _ResetResult(2)
        return _ResetResult()


class _ResetEngine:
    def __init__(self, *, active_runs: int = 0) -> None:
        self.connection = _ResetConnection(active_runs=active_runs)

    def begin(self) -> _ResetConnection:
        return self.connection


@pytest.mark.anyio
async def test_demo_reset_uses_the_privileged_function_and_returns_counts() -> None:
    engine = _ResetEngine()
    app = FastAPI()
    app.include_router(demo_ai_history_routes.make_demo_ai_history_router(engine, enabled=True))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/demo/ai-history/reset")

    assert response.status_code == 200
    assert response.json()["deleted_runs"] == 3
    assert response.json()["deleted_chat_messages"] == 5
    assert response.json()["deleted_artifacts"] == 2
    assert engine.connection.statements == [
        "SELECT pg_catalog.pg_advisory_xact_lock(82420260718)",
        "LOCK TABLE public.agent_runs IN ACCESS EXCLUSIVE MODE",
        "SELECT count(*) FROM public.agent_runs WHERE status IN ('queued', 'running')",
        "SELECT count(*) FROM public.agent_runs",
        "SELECT count(*) FROM public.review_chat_messages",
        "SELECT count(*) FROM public.agent_run_artifacts",
        "SELECT heatgrid_admin.reset_demo_ai_history()",
    ]
    assert all("TRUNCATE" not in statement for statement in engine.connection.statements)


@pytest.mark.anyio
async def test_demo_reset_remains_unavailable_when_the_feature_is_disabled() -> None:
    engine = _ResetEngine()
    app = FastAPI()
    app.include_router(demo_ai_history_routes.make_demo_ai_history_router(engine, enabled=False))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/demo/ai-history/reset")

    assert response.status_code == 404
    assert response.json() == {"detail": "demo reset is disabled"}
    assert engine.connection.statements == []


@pytest.mark.anyio
async def test_demo_reset_rejects_running_analysis_before_counting_or_deleting() -> None:
    engine = _ResetEngine(active_runs=1)
    app = FastAPI()
    app.include_router(demo_ai_history_routes.make_demo_ai_history_router(engine, enabled=True))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/demo/ai-history/reset")

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "AI 분석이 진행 중입니다. 분석이 완료된 뒤 "
            "누적 기록을 초기화해 주세요."
        )
    }
    assert engine.connection.statements == [
        "SELECT pg_catalog.pg_advisory_xact_lock(82420260718)",
        "LOCK TABLE public.agent_runs IN ACCESS EXCLUSIVE MODE",
        "SELECT count(*) FROM public.agent_runs WHERE status IN ('queued', 'running')",
    ]
