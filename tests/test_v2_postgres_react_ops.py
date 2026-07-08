import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from httpx import ASGITransport, AsyncClient
import orjson
import pytest

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "05_시뮬레이션" / "versions" / "v2_postgres_react_ops" / "backend"
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
