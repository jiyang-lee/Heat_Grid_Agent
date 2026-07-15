import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
SERVER_PATH: Final = BACKEND_DIR / "server.py"
VALID_SOURCES: Final = {"postgres", "pgvector", "jsonl", "kma", "fallback", "manual"}


def load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("v4_agent_result_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("v2 서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def reset_contract_tables(module: ModuleType) -> None:
    async with module.engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE TABLE agent_runs, ops_alert_queue CASCADE")
        )


async def wait_for_agent_run(client: AsyncClient, run_id: str) -> None:
    for _ in range(200):
        response = await client.get(f"/api/agent-runs/{run_id}")
        if response.json().get("status") in {"completed", "failed"}:
            return
        await asyncio.sleep(0.025)
    raise AssertionError(f"agent run {run_id} did not finish")


@pytest.mark.anyio
async def test_agent_result_v4_returns_completed_run_contract(
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
        await wait_for_agent_run(client, run_id)
        result = await client.get(f"/api/agent-runs/{run_id}/result")

    payload = result.json()

    assert result.status_code == 200
    assert payload["schema_version"] == "ops_agent_result.v4"
    assert payload["run_id"] == run_id
    assert payload["card_id"] == alert["card_id"]
    assert payload["headline"]
    assert payload["situation"]
    assert payload["evidence"]
    assert {item["source"] for item in payload["evidence"]} <= VALID_SOURCES
    assert payload["actions"][0]["priority"] == 1
    assert payload["actions"][0]["detail"]
    assert payload["cautions"]
    assert payload["report"]["format"] == "markdown"
    assert "작업 지시 보고서" in payload["report"]["content"]


@pytest.mark.anyio
async def test_agent_result_v4_returns_404_for_unknown_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/agent-runs/{uuid4()}/result")

    assert response.status_code == 404
    assert response.json()["detail"] == "run_id를 찾을 수 없습니다."


@pytest.mark.anyio
async def test_agent_result_v4_returns_409_for_run_without_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)
    from agent_run_repository import create_queued_agent_run

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        await client.post("/api/alerts/enqueue")
        alerts = await client.get("/api/alerts", params={"status": "open"})
        alert = alerts.json()[0]
    queued_run = await create_queued_agent_run(
        module.engine,
        str(uuid4()),
        alert["alert_id"],
        alert["card_id"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/agent-runs/{queued_run.run_id}/result")

    assert response.status_code == 409
    assert response.json()["detail"] == "agent run result is not ready."
