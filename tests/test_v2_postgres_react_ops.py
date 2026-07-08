import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from httpx import ASGITransport, AsyncClient
import orjson
import pytest
from sqlalchemy import text

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
SERVER_PATH: Final = BACKEND_DIR / "server.py"


def load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("v2_postgres_react_ops_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("v2 서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.anyio
async def test_v2_postgres_tools_return_ops_evidence_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    card_ids = await module.list_card_ids(module.engine)
    source_input = await module.input_for_card(card_ids[0])
    tools = {item.name: item for item in module.tools_for(source_input)}

    evidence = orjson.loads(tools["get_ops_evidence"].invoke({"card_id": card_ids[0]}))

    assert set(tools) == {"get_ops_evidence"}
    assert evidence["priority_context"]["card"]["card_id"] == card_ids[0]
    assert "model_outputs" in evidence["priority_context"]
    assert isinstance(evidence["priority_context"]["model_outputs"], list)
    assert "raw_context" in evidence


@pytest.mark.anyio
async def test_v2_postgres_api_returns_fallback_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        health = await client.get("/health")
        cards = await client.get("/cards")
        card_id = cards.json()[0]["card_id"]
        response = await client.post(f"/simulate/{card_id}")
        stream = await client.get(f"/simulate-stream/{card_id}")

    assert health.status_code == 200
    assert health.json()["input"] == "postgresql"
    assert cards.status_code == 200
    assert response.status_code == 200
    assert response.json()["input_source"] == "postgresql"
    assert stream.status_code == 200
    assert "PostgreSQL priority_card 조회 완료" in stream.text
    assert "get_external_context" not in stream.text


@pytest.mark.anyio
async def test_v2_postgres_alert_api_enqueues_lists_and_acks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    async with module.engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS ops_alert_queue"))

    async with AsyncClient(
        transport=ASGITransport(app=module.app),
        base_url="http://test",
    ) as client:
        enqueue = await client.post("/alerts/enqueue")
        duplicate_enqueue = await client.post("/alerts/enqueue")
        open_alerts = await client.get("/alerts", params={"status": "open"})
        first_alert = open_alerts.json()[0]
        ack = await client.post(
            f"/alerts/{first_alert['alert_id']}/ack",
            json={"acked_by": "pytest"},
        )
        acked_alerts = await client.get("/alerts", params={"status": "acked"})

    assert enqueue.status_code == 200
    assert enqueue.json()["queued_count"] > 0
    assert enqueue.json()["existing_count"] == 0
    assert duplicate_enqueue.status_code == 200
    assert duplicate_enqueue.json()["queued_count"] == 0
    assert duplicate_enqueue.json()["existing_count"] == enqueue.json()["queued_count"]
    assert open_alerts.status_code == 200
    assert first_alert["card_id"]
    assert first_alert["priority_level"] in {"urgent", "high"}
    assert ack.status_code == 200
    assert ack.json()["status"] == "acked"
    assert ack.json()["acked_by"] == "pytest"
    assert acked_alerts.status_code == 200
    assert any(item["alert_id"] == first_alert["alert_id"] for item in acked_alerts.json())
