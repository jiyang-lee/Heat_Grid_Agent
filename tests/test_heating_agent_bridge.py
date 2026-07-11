import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
SERVER_PATH: Final = BACKEND_DIR / "server.py"


def load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location(
        "v2_postgres_react_ops_server", SERVER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("v2 서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def reset_contract_tables(module: ModuleType) -> None:
    async with module.engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_actions"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_artifacts"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_events"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_runs"))
        await connection.execute(text("DROP TABLE IF EXISTS ops_alert_queue"))


@pytest.mark.anyio
async def test_heating_agent_bridge_serves_frontend_without_modifying_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    source_html = (ROOT / "frontend" / "heating_agent.html").read_text(encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        page = await client.get("/heating-agent")
        script = await client.get("/heating-agent-bridge.js")

    assert page.status_code == 200
    assert "지역난방 보조운영 에이전트" in page.text
    assert '<script src="/heating-agent-bridge.js"></script>' in page.text
    assert '<script src="/heating-agent-bridge.js"></script>' not in source_html
    assert script.status_code == 200
    assert 'POST"' in script.text
    assert "/alerts/enqueue" in script.text
    assert "/heating-agent/api/alerts?status=open" in script.text
    assert '"/api/agent-runs"' in script.text


@pytest.mark.anyio
async def test_heating_agent_alert_api_returns_alerts_with_building_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    await reset_contract_tables(module)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        enqueue = await client.post("/alerts/enqueue")
        alerts = await client.get("/heating-agent/api/alerts", params={"status": "open"})
        urgent_alerts = await client.get(
            "/heating-agent/api/alerts",
            params={"status": "open", "priority_level": "urgent"},
        )

    first_alert = alerts.json()[0]
    assert enqueue.status_code == 200
    assert enqueue.json()["queued_count"] > 0
    assert alerts.status_code == 200
    assert first_alert["alert_id"]
    assert first_alert["card_id"]
    assert first_alert["priority_level"] in {"urgent", "high"}
    assert 1 <= int(first_alert["substation_id"]) <= 31
    assert first_alert["manufacturer_id"]
    assert first_alert["window_start"]
    assert first_alert["window_end"]
    assert urgent_alerts.status_code == 200
    assert all(item["priority_level"] == "urgent" for item in urgent_alerts.json())
