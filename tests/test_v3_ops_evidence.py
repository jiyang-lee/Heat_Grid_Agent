import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from sqlalchemy import text
import orjson
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
    spec = importlib.util.spec_from_file_location("v3_ops_evidence_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("v2 서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tools_for_input(
    module: ModuleType,
    card_id: str,
    source_input: dict[str, object],
) -> dict[str, object]:
    external_context = module.external_context_for(card_id, source_input)
    return {item.name: item for item in module.tools_for(source_input, external_context)}


@pytest.mark.anyio
async def test_ops_evidence_tool_returns_selected_schema_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    card_ids = await module.list_card_ids(module.engine)
    source_input = await module.input_for_card(card_ids[0])
    tools = tools_for_input(module, card_ids[0], source_input)

    evidence = orjson.loads(
        tools["get_ops_evidence"].invoke(
            {"card_id": card_ids[0], "sections": ["priority", "window"]}
        )
    )

    assert evidence["card_id"] == card_ids[0]
    assert set(evidence["sections"]) == {"priority", "window"}
    assert "priority_card" in evidence["sections"]["priority"]
    assert "priority_decision" in evidence["sections"]["priority"]
    assert "window_id" in evidence["sections"]["window"]
    assert evidence["unsupported_sections"] == []
    assert "raw_context" not in evidence
    assert "priority_context" not in evidence


@pytest.mark.anyio
async def test_ops_evidence_tool_keeps_database_section_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    card_ids = await module.list_card_ids(module.engine)
    source_input = await module.input_for_card(card_ids[0])
    tools = tools_for_input(module, card_ids[0], source_input)

    evidence = orjson.loads(
        tools["get_ops_evidence"].invoke(
            {"card_id": card_ids[0], "sections": ["priority", "window"]}
        )
    )
    async with module.engine.connect() as connection:
        result = await connection.execute(
            text(
                "select table_name, column_name "
                "from information_schema.columns "
                "where table_schema = 'public' "
                "and table_name in "
                "('priority_cards', 'priority_decisions', 'windows')"
            )
        )
    columns_by_table: dict[str, set[str]] = {}
    for row in result.mappings().all():
        columns_by_table.setdefault(str(row["table_name"]), set()).add(
            str(row["column_name"])
        )

    assert columns_by_table["priority_cards"] <= set(
        evidence["sections"]["priority"]["priority_card"]
    )
    assert columns_by_table["priority_decisions"] <= set(
        evidence["sections"]["priority"]["priority_decision"]
    )
    assert columns_by_table["windows"] <= set(evidence["sections"]["window"])


@pytest.mark.anyio
async def test_ops_evidence_tool_reports_unsupported_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    card_ids = await module.list_card_ids(module.engine)
    source_input = await module.input_for_card(card_ids[0])
    tools = tools_for_input(module, card_ids[0], source_input)

    evidence = orjson.loads(
        tools["get_ops_evidence"].invoke(
            {"card_id": card_ids[0], "sections": ["priority", "sensor_readings"]}
        )
    )

    assert set(evidence["sections"]) == {"priority"}
    assert evidence["unsupported_sections"] == ["sensor_readings"]
