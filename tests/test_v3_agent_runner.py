import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final
from uuid import uuid4

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
import pytest

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
SERVER_PATH: Final = BACKEND_DIR / "server.py"


def load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("v3_agent_runner_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("v2 서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def reset_contract_tables(module: ModuleType) -> None:
    async with module.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE agent_budget_ledger, agent_run_tasks, "
                "agent_run_actions, agent_run_artifacts, agent_run_events, "
                "agent_runs, ops_alert_queue CASCADE"
            )
        )


async def wait_for_agent_run(client: AsyncClient, run_id: str) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(f"/api/agent-runs/{run_id}")
        payload = response.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        await asyncio.sleep(0.025)
    raise AssertionError(f"agent run {run_id} did not finish")


@pytest.mark.anyio
async def test_agent_runner_records_failed_run_when_graph_node_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)
    from agent_runner import AgentRunRequest, run_agent_graph
    from schemas import SimulationResponse

    async def fail_simulation(_: str) -> SimulationResponse:
        raise HTTPException(status_code=500, detail="forced failure")

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alerts = await client.get("/api/alerts", params={"status": "open"})
    alert = alerts.json()[0]
    run_id = str(uuid4())

    run = await run_agent_graph(
        module.engine,
        AgentRunRequest(
            run_id=run_id,
            alert_id=alert["alert_id"],
            card_id=alert["card_id"],
        ),
        fail_simulation,
    )
    async with module.engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT event_type FROM agent_run_events "
                "WHERE run_id = :run_id ORDER BY event_id"
            ),
            {"run_id": run_id},
        )
    event_types = [str(row["event_type"]) for row in result.mappings().all()]

    assert run.status == "failed"
    assert run.error == "forced failure"
    assert event_types[-2:] == ["status_changed", "run_failed"]


@pytest.mark.anyio
async def test_agent_runner_keeps_completed_run_when_report_generation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alerts = await client.get("/api/alerts", params={"status": "open"})
        alert = alerts.json()[0]
        created = await client.post(
            "/api/agent-runs",
            json={"alert_id": alert["alert_id"]},
        )
        run_id = created.json()["run_id"]
        completed = await wait_for_agent_run(client, run_id)
        artifacts = await client.get(f"/api/agent-runs/{run_id}/artifacts")

    async with module.engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT event_type FROM agent_run_events "
                "WHERE run_id = :run_id ORDER BY event_id"
            ),
            {"run_id": run_id},
        )
    event_types = [str(row["event_type"]) for row in result.mappings().all()]

    assert created.status_code == 200
    assert created.json()["status"] == "queued"
    assert completed["status"] == "completed"
    assert completed["agent_mode"] == "fallback"
    assert artifacts.status_code == 200
    assert artifacts.json() == []
    assert "run_completed" in event_types
    assert "report_failed" in event_types
