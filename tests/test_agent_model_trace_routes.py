from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.anyio
async def test_trace_routes_expose_tool_free_report_cost(
) -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    import agent_quality_routes

    engine = _TraceEngine()
    app = FastAPI()
    app.include_router(agent_quality_routes.make_agent_quality_router(engine))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/agent-runs/run-1/cost-breakdown")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run-1",
        "model_call_count": 1,
        "tool_call_count": 0,
        "input_tokens": 12,
        "output_tokens": 3,
        "total_tokens": 15,
    }


class _TraceResult:
    def __init__(self, row: dict[str, int] | None = None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> int:
        return 1

    def mappings(self) -> _TraceResult:
        return self

    def one(self) -> dict[str, int]:
        assert self._row is not None
        return self._row


class _TraceConnection:
    async def __aenter__(self) -> _TraceConnection:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: object, _parameters: object) -> _TraceResult:
        if "count(*) AS model_call_count" in str(statement):
            return _TraceResult(
                {
                    "model_call_count": 1,
                    "tool_call_count": 0,
                    "input_tokens": 12,
                    "output_tokens": 3,
                    "total_tokens": 15,
                }
            )
        return _TraceResult()


class _TraceEngine:
    def connect(self) -> _TraceConnection:
        return _TraceConnection()
