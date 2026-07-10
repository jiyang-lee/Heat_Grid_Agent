from __future__ import annotations

import orjson
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


async def fetch_model_feature_snapshot(
    engine: AsyncEngine,
    card_id: str,
) -> dict[str, float]:
    query = text(
        "SELECT CAST(mfs.features AS text) AS features "
        "FROM priority_cards pc "
        "JOIN priority_decisions pd ON pd.priority_decision_id = pc.priority_decision_id "
        "JOIN model_feature_snapshots mfs ON mfs.window_id = pd.window_id "
        "WHERE pc.card_id = :card_id"
    )
    try:
        async with engine.connect() as connection:
            result = await connection.execute(query, {"card_id": card_id})
    except (SQLAlchemyError, OSError, RuntimeError):
        return {}
    row = result.mappings().one_or_none()
    if row is None:
        return {}
    payload = orjson.loads(row["features"])
    if not isinstance(payload, dict):
        return {}
    values: dict[str, float] = {}
    for name, value in payload.items():
        try:
            values[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    return values
