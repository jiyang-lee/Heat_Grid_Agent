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


def _make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _make_app(monkeypatch: pytest.MonkeyPatch, **fakes) -> FastAPI:
    from simulator.versions.v2_postgres_react_ops.backend import agent_review_routes

    for name, fake in fakes.items():
        monkeypatch.setattr(agent_review_routes, name, fake)
    app = FastAPI()
    engine = create_async_engine("postgresql+asyncpg://test:test@127.0.0.1:1/test")
    app.include_router(agent_review_routes.make_agent_review_router(engine))
    return app


@pytest.mark.anyio
async def test_agent_run_list_serializes_enrichment_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                    priority="urgent",
                    operator_review_status="pending",
                    worker_status="completed",
                    review_snapshot_status="available",
                    created_at=datetime(2026, 7, 15, tzinfo=UTC),
                    updated_at=datetime(2026, 7, 15, tzinfo=UTC),
                    manufacturer_id="manufacturer 1",
                    substation_id=7,
                    substation_uid="00000000-0000-0000-0000-00000000000a",
                    alert_reason="공급온도 급감",
                    current_stage="fault_analysis",
                    has_result=True,
                    report_artifact_count=2,
                    latest_report_name="anomaly_report.md",
                ),
            ),
            total_count=1,
        )

    app = _make_app(monkeypatch, list_agent_runs=fake_list_agent_runs)
    async with _make_client(app) as client:
        response = await client.get(
            "/api/agent-runs",
            params={"substation_id": 7, "search": "공급온도"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    item = payload["items"][0]
    assert item["substation_id"] == 7
    assert item["alert_reason"] == "공급온도 급감"
    assert item["current_stage"] == "fault_analysis"
    assert item["has_result"] is True
    assert item["report_artifact_count"] == 2
    assert item["latest_report_name"] == "anomaly_report.md"


@pytest.mark.anyio
async def test_agent_run_list_passes_new_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        AgentRunListPage,
    )

    captured = {}

    async def fake_list_agent_runs(_engine, filters) -> AgentRunListPage:
        captured["filters"] = filters
        return AgentRunListPage(items=(), total_count=0)

    app = _make_app(monkeypatch, list_agent_runs=fake_list_agent_runs)
    async with _make_client(app) as client:
        response = await client.get(
            "/api/agent-runs",
            params={"substation_id": 12, "search": "run-check", "limit": 10},
        )

    assert response.status_code == 200
    assert captured["filters"].substation_id == 12
    assert captured["filters"].search == "run-check"
    assert captured["filters"].limit == 10


@pytest.mark.anyio
async def test_work_orders_returns_typed_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        WorkOrderListItem,
        WorkOrderListPage,
    )

    async def fake_list_work_orders(_engine, filters) -> WorkOrderListPage:
        assert filters.operator_review_status == "pending"
        return WorkOrderListPage(
            items=(
                WorkOrderListItem(
                    run_id="00000000-0000-0000-0000-000000000002",
                    priority="urgent",
                    alert_reason="공급온도 급감 및 보충 유량 증가",
                    manufacturer_id="manufacturer 1",
                    substation_id=1,
                    substation_uid="00000000-0000-0000-0000-00000000000a",
                    operator_review_status="pending",
                    created_at=datetime(2026, 7, 15, tzinfo=UTC),
                ),
            ),
            total_count=1,
        )

    app = _make_app(monkeypatch, list_work_orders=fake_list_work_orders)
    async with _make_client(app) as client:
        response = await client.get(
            "/api/work-orders", params={"operator_review_status": "pending"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["run_id"] == "00000000-0000-0000-0000-000000000002"
    assert payload["items"][0]["operator_review_status"] == "pending"


@pytest.mark.anyio
async def test_agent_reports_returns_typed_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        AgentReportListItem,
        AgentReportListPage,
    )

    async def fake_list_agent_reports(_engine, filters) -> AgentReportListPage:
        assert filters.search == "보고서"
        return AgentReportListPage(
            items=(
                AgentReportListItem(
                    artifact_id="00000000-0000-0000-0000-00000000000b",
                    run_id="00000000-0000-0000-0000-000000000002",
                    kind="anomaly_report",
                    name="ops_action_report.md",
                    uri="/artifacts/run/ops_action_report.md",
                    priority="high",
                    manufacturer_id="manufacturer 1",
                    substation_id=3,
                    substation_uid=None,
                    operator_review_status="approved",
                    created_at=datetime(2026, 7, 15, tzinfo=UTC),
                ),
            ),
            total_count=1,
        )

    app = _make_app(monkeypatch, list_agent_reports=fake_list_agent_reports)
    async with _make_client(app) as client:
        response = await client.get("/api/agent-reports", params={"search": "보고서"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["kind"] == "anomaly_report"
    assert payload["items"][0]["operator_review_status"] == "approved"


@pytest.mark.anyio
async def test_work_orders_rejects_naive_datetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        WorkOrderListPage,
    )

    async def fake_list_work_orders(_engine, _filters) -> WorkOrderListPage:
        return WorkOrderListPage(items=(), total_count=0)

    app = _make_app(monkeypatch, list_work_orders=fake_list_work_orders)
    async with _make_client(app) as client:
        response = await client.get(
            "/api/work-orders", params={"created_from": "2026-07-15T00:00:00"}
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_agent_reports_rejects_malformed_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_review_api_models import (
        AgentReportListPage,
    )

    async def fake_list_agent_reports(_engine, _filters) -> AgentReportListPage:
        return AgentReportListPage(items=(), total_count=0)

    app = _make_app(monkeypatch, list_agent_reports=fake_list_agent_reports)
    async with _make_client(app) as client:
        response = await client.get(
            "/api/agent-reports", params={"cursor": "not-a-cursor"}
        )

    assert response.status_code == 422


def test_escape_like_treats_pattern_chars_as_literals() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_run_listing_repository import (
        escape_like,
    )

    assert escape_like("100%_done\\") == "100\\%\\_done\\\\"
