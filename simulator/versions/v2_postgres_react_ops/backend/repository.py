from decimal import Decimal
from typing import TypeAlias

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from evidence_repository import fetch_ops_evidence

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
    return await fetch_ops_evidence(engine, card_id)


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value
