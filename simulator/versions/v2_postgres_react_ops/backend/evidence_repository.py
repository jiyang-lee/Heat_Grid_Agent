from collections.abc import Sequence
from decimal import Decimal
from typing import Final, TypeAlias

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
OpsInput: TypeAlias = dict[str, JsonValue]
SUPPORTED_EVIDENCE_SECTIONS: Final = frozenset(
    {
        "priority",
        "window",
        "substation",
        "sensor_summaries",
        "model_outputs",
        "review_reasons",
        "evaluation",
    }
)


async def fetch_ops_evidence(engine: AsyncEngine, card_id: str) -> OpsInput | None:
    try:
        async with engine.connect() as connection:
            context_result = await connection.execute(
                evidence_context_query(), {"card_id": card_id}
            )
            context_row = context_result.mappings().one_or_none()
            if context_row is None:
                return None
            sensor_result = await connection.execute(
                evidence_sensor_summary_query(), {"card_id": card_id}
            )
            model_result = await connection.execute(
                evidence_model_output_query(), {"card_id": card_id}
            )
            review_result = await connection.execute(
                evidence_review_reason_query(), {"card_id": card_id}
            )
    except (SQLAlchemyError, OSError):
        return None
    return _ops_input_from_schema_rows(
        context_row,
        sensor_result.mappings().all(),
        model_result.mappings().all(),
        review_result.mappings().all(),
    )


def filter_ops_evidence(
    source_input: OpsInput,
    card_id: str,
    requested_sections: Sequence[str] | None,
) -> OpsInput:
    if card_id != str(source_input["card_id"]):
        return {"error": "card_id를 찾을 수 없습니다."}
    if requested_sections is None:
        return source_input

    sections = _dict_value(source_input["sections"])
    supported = [name for name in requested_sections if name in SUPPORTED_EVIDENCE_SECTIONS]
    unsupported = [
        name for name in requested_sections if name not in SUPPORTED_EVIDENCE_SECTIONS
    ]
    return {
        "card_id": card_id,
        "sections": {name: sections[name] for name in supported},
        "unsupported_sections": unsupported,
    }


def evidence_context_query():
    return text(
        "select "
        "cast(to_jsonb(pc) as text) as priority_card, "
        "cast(to_jsonb(pd) as text) as priority_decision, "
        "cast(to_jsonb(w) as text) as window, "
        "cast(to_jsonb(s) as text) as substation "
        "from priority_cards pc "
        "join priority_decisions pd on pd.priority_decision_id = pc.priority_decision_id "
        "join windows w on w.window_id = pd.window_id "
        "left join substations s "
        "on s.manufacturer_id = w.manufacturer_id "
        "and s.substation_id = w.substation_id "
        "where pc.card_id = :card_id"
    )


def evidence_sensor_summary_query():
    return text(
        "select cast(to_jsonb(ss) as text) as section_row "
        "from sensor_summaries ss "
        "where ss.card_id = :card_id "
        "order by ss.display_rank, ss.feature_name"
    )


def evidence_model_output_query():
    return text(
        "select cast(to_jsonb(mo) as text) as section_row "
        "from model_outputs mo "
        "join priority_decisions pd on pd.window_id = mo.window_id "
        "join priority_cards pc on pc.priority_decision_id = pd.priority_decision_id "
        "where pc.card_id = :card_id "
        "order by mo.display_rank, mo.score_name, mo.label_name"
    )


def evidence_review_reason_query():
    return text(
        "select cast(to_jsonb(prr) as text) as section_row "
        "from priority_card_review_reasons prr "
        "where prr.card_id = :card_id "
        "order by prr.display_rank, prr.reason_code"
    )


def _ops_input_from_schema_rows(
    context_row: RowMapping,
    sensor_rows: Sequence[RowMapping],
    model_output_rows: Sequence[RowMapping],
    review_reason_rows: Sequence[RowMapping],
) -> OpsInput:
    priority_card = _dict_value(_json_from_text(context_row["priority_card"]))
    priority_decision = _dict_value(_json_from_text(context_row["priority_decision"]))
    window = _dict_value(_json_from_text(context_row["window"]))
    sections: dict[str, JsonValue] = {
        "priority": {
            "priority_card": priority_card,
            "priority_decision": priority_decision,
        },
        "window": window,
        "substation": _json_from_text(context_row["substation"]),
        "sensor_summaries": _json_rows(sensor_rows),
        "model_outputs": _json_rows(model_output_rows),
        "review_reasons": _json_rows(review_reason_rows),
    }
    payload: OpsInput = {
        "card_id": str(priority_card["card_id"]),
        "sections": sections,
        "unsupported_sections": [],
    }
    payload.update(_legacy_evidence_aliases(sections))
    return payload


def _legacy_evidence_aliases(sections: dict[str, JsonValue]) -> OpsInput:
    priority = _dict_value(sections["priority"])
    priority_card = _dict_value(priority["priority_card"])
    priority_decision = _dict_value(priority["priority_decision"])
    review_reasons = _list_value(sections["review_reasons"])
    return {
        "raw_context": {
            "window": sections["window"],
            "substation": sections["substation"],
            "sensor_summaries": sections["sensor_summaries"],
        },
        "priority_context": {
            "card": priority_card,
            "priority": priority_decision,
            "model_signals": priority_decision,
            "explanation": {
                **priority_card,
                "review_reasons": [
                    _dict_value(row)["reason_code"] for row in review_reasons
                ],
            },
            "model_outputs": sections["model_outputs"],
        },
    }


def _json_rows(rows: Sequence[RowMapping]) -> list[JsonValue]:
    return [_json_from_text(row["section_row"]) for row in rows]


def _json_from_text(value: JsonValue) -> JsonValue:
    if not isinstance(value, str):
        return _json_scalar(value)
    return orjson.loads(value)


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value


def _dict_value(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError("JSON object expected")
    return value


def _list_value(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError("JSON array expected")
    return value
