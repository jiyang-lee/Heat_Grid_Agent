from collections.abc import Sequence
from decimal import Decimal
from typing import TypeAlias

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from queries import (
    CURRENT_BEST_FLOW,
    M1_SPECIALIST_FLOW,
    PRIORITY_CALCULATION_EXPRESSION,
    card_query,
    model_outputs_query,
    sensor_summary_query,
)

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
OpsInput: TypeAlias = dict[str, JsonValue]


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


async def check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except (SQLAlchemyError, OSError):
        return False
    return True


async def list_card_ids(engine: AsyncEngine) -> list[str]:
    cards = await list_cards(engine)
    return [str(item["card_id"]) for item in cards]


async def list_cards(
    engine: AsyncEngine,
    search: str | None = None,
    priority_level: str | None = None,
) -> list[dict[str, JsonValue]]:
    filters: list[str] = []
    params: dict[str, JsonValue] = {}
    if search:
        params["search"] = f"%{search}%"
        filters.append(
            "("
            "pc.card_id::text ilike :search "
            "or w.manufacturer_id ilike :search "
            "or cast(w.substation_id as text) ilike :search "
            "or coalesce(pc.operational_label, '') ilike :search "
            "or coalesce(pc.primary_state, '') ilike :search "
            "or coalesce(pc.why_reason, '') ilike :search"
            ")"
        )
    if priority_level:
        params["priority_level"] = priority_level
        filters.append("pd.priority_level = :priority_level")

    where_sql = f" where {' and '.join(filters)}" if filters else ""
    query = text(
        "select pc.card_id, w.manufacturer_id, w.substation_id, pc.operational_label,\n"
        "pc.primary_state, pc.review_required, pc.trust_level,\n"
        "pd.priority_level, pd.priority_score, pd.current_best_weight, pd.m1_specialist_weight,\n"
        "pd.current_best_priority_score, pd.m1_specialist_priority_score,\n"
        "pc.why_reason, pc.recommended_action, pc.stable_crossing_lead_hours,\n"
        "w.window_start, w.window_end, w.label, w.fault_event_id\n"
        "from priority_cards pc\n"
        "join priority_decisions pd on pd.priority_decision_id = pc.priority_decision_id\n"
        "join windows w on w.window_id = pd.window_id\n"
        f"{where_sql}\n"
        "order by pd.priority_score desc nulls last, pc.created_at desc, pc.card_id"
    )

    async with engine.connect() as connection:
        result = await connection.execute(query, params)
    rows = result.mappings().all()
    return [
        {
            "card_id": str(row["card_id"]),
            "manufacturer_id": str(row["manufacturer_id"]),
            "substation_id": _json_scalar(row["substation_id"]),
            "operational_label": row["operational_label"],
            "primary_state": row["primary_state"],
            "review_required": row["review_required"],
            "trust_level": row["trust_level"],
            "priority_level": row["priority_level"],
            "priority_score": _json_scalar(row["priority_score"]),
            "current_best_weight": _json_scalar(row["current_best_weight"]),
            "m1_specialist_weight": _json_scalar(row["m1_specialist_weight"]),
            "current_best_priority_score": _json_scalar(
                row["current_best_priority_score"]
            ),
            "m1_specialist_priority_score": _json_scalar(
                row["m1_specialist_priority_score"]
            ),
            "why_reason": row["why_reason"],
            "recommended_action": row["recommended_action"],
            "stable_crossing_lead_hours": _json_scalar(row["stable_crossing_lead_hours"]),
            "window_start": row["window_start"].isoformat(),
            "window_end": row["window_end"].isoformat(),
            "window_label": row["label"],
            "fault_event_id": row["fault_event_id"],
        }
        for row in rows
    ]


async def fetch_ops_input(engine: AsyncEngine, card_id: str) -> OpsInput | None:
    try:
        async with engine.connect() as connection:
            card_result = await connection.execute(card_query(), {"card_id": card_id})
            card_row = card_result.mappings().one_or_none()
            if card_row is None:
                return None
            current_best_result = await connection.execute(
                sensor_summary_query(),
                {"card_id": card_id, "flow_source": CURRENT_BEST_FLOW},
            )
            m1_result = await connection.execute(
                sensor_summary_query(),
                {"card_id": card_id, "flow_source": M1_SPECIALIST_FLOW},
            )
            review_reason_result = await connection.execute(
                text(
                    "select reason_code "
                    "from priority_card_review_reasons "
                    "where card_id = :card_id "
                    "order by display_rank, reason_code"
                ),
                {"card_id": card_id},
            )
            model_outputs_result = await connection.execute(
                model_outputs_query(),
                {"window_id": card_row["window_id"]},
            )
    except (SQLAlchemyError, OSError):
        return None
    return _ops_input_from_rows(
        card_row,
        current_best_result.mappings().all(),
        m1_result.mappings().all(),
        review_reason_result.mappings().all(),
        model_outputs_result.mappings().all(),
    )



def _ops_input_from_rows(
    card_row: RowMapping,
    current_best_rows: Sequence[RowMapping],
    m1_rows: Sequence[RowMapping],
    review_reason_rows: Sequence[RowMapping],
    model_output_rows: Sequence[RowMapping],
) -> OpsInput:
    current_best_values = [_sensor_value_from_row(row) for row in current_best_rows]
    m1_values = [_sensor_value_from_row(row) for row in m1_rows]
    return {
        "raw_context": {
            "window": {
                "window_id": str(card_row["window_id"]),
                "manufacturer_id": str(card_row["manufacturer_id"]),
                "substation_id": _json_scalar(card_row["substation_id"]),
                "configuration_type": card_row["configuration_type"],
                "window_start": card_row["window_start"].isoformat(),
                "window_end": card_row["window_end"].isoformat(),
            },
            "current_best_sensor_values": {
                "model_id": _group_text(current_best_rows, "model_id", "current-best"),
                "model_version": _row_optional_text(
                    current_best_rows[0], "model_version"
                )
                if current_best_rows
                else None,
                "source_artifact": _group_text(current_best_rows, "source_artifact", ""),
                "selection_rule": _group_text(current_best_rows, "selection_rule", ""),
                "top_n": len(current_best_values),
                "values": current_best_values,
            },
            "m1_specialist_features": {
                "model_id": _group_text(m1_rows, "model_id", "m1-specialist"),
                "model_version": _row_optional_text(m1_rows[0], "model_version")
                if m1_rows
                else None,
                "source_artifact": _group_text(m1_rows, "source_artifact", ""),
                "feature_count": len(m1_values),
                "features": m1_values,
            },
        },
        "priority_context": {
            "card": {
                "card_id": str(card_row["card_id"]),
                "operational_label": card_row["operational_label"],
                "primary_state": card_row["primary_state"],
                "trust_level": card_row["trust_level"],
                "raw_card": card_row["raw_card"],
            },
            "priority": {
                "priority_decision_id": str(card_row["priority_decision_id"]),
                "priority_score": _json_scalar(card_row["priority_score"]),
                "priority_level": card_row["priority_level"],
                "priority_source": card_row["priority_source"],
                "m1_priority_agreement": card_row["m1_priority_agreement"],
                "calculation": {
                    "current_best_weight": _json_scalar(
                        card_row["current_best_weight"]
                    ),
                    "m1_specialist_weight": _json_scalar(
                        card_row["m1_specialist_weight"]
                    ),
                    "expression": PRIORITY_CALCULATION_EXPRESSION,
                },
            },
            "model_signals": {
                "current_best_priority_score": _json_scalar(
                    card_row["current_best_priority_score"]
                ),
                "current_best_priority_level": card_row["current_best_priority_level"],
                "m1_specialist_priority_score": _json_scalar(
                    card_row["m1_specialist_priority_score"]
                ),
                "m1_specialist_priority_level": card_row["m1_specialist_priority_level"],
                "m1_specialist_primary_state": card_row[
                    "m1_specialist_primary_state"
                ],
                "m1_specialist_fault_group": card_row["m1_specialist_fault_group"],
            },
            "explanation": {
                "why_reason": card_row["why_reason"],
                "recommended_action": card_row["recommended_action"],
                "review_required": card_row["review_required"],
                "review_reasons": [str(row["reason_code"]) for row in review_reason_rows],
            },
            "model_outputs": [
                {
                    "model_family": row["model_family"],
                    "score_name": _row_text(row, "score_name", ""),
                    "score_value": _json_scalar(row["score_value"]),
                    "label_name": _row_optional_text(row, "label_name"),
                    "label_value": _row_optional_text(row, "label_value"),
                    "display_rank": int(row["display_rank"]),
                }
                for row in model_output_rows
            ],
        },
    }


def _sensor_value_from_row(row: RowMapping) -> dict[str, JsonValue]:
    return {
        "rank": int(row["display_rank"]),
        "feature_name": str(row["feature_name"]),
        "source_sensor": str(row["source_sensor"]),
        "source_column": _row_text(row, "source_column", str(row["feature_name"])),
        "feature_value": _json_scalar(row["feature_value"]),
        "unit": _row_optional_text(row, "unit"),
        "calculation": _row_text(row, "calculation", "unknown"),
        "meaning": _row_text(row, "meaning", ""),
        "summary_text": _row_optional_text(row, "summary_text"),
    }


def _group_text(rows: Sequence[RowMapping], key: str, fallback: str) -> str:
    return fallback if len(rows) == 0 else _row_text(rows[0], key, fallback)


def _row_text(row: RowMapping, key: str, fallback: str) -> str:
    value = row[key]
    return fallback if value is None else str(value)


def _row_optional_text(row: RowMapping, key: str) -> str | None:
    value = row[key]
    return None if value is None else str(value)


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value
