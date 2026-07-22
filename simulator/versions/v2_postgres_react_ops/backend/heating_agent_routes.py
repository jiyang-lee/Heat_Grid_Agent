from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeAlias

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from alert_repository import ensure_alert_queue

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parents[3]
HEATING_AGENT_HTML = REPO_ROOT / "frontend" / "heating_agent.html"
BRIDGE_SCRIPT = BACKEND_DIR / "heating_agent_bridge.js"
BRIDGE_TAG = '<script src="/heating-agent-bridge.js"></script>'

HEATING_AGENT_ALERTS_SQL = (
    "SELECT "
    "q.alert_id, q.card_id, q.priority_level, q.priority_score, q.status, "
    "q.enqueue_reason, q.created_at, q.acked_at, q.acked_by, "
    "s.manufacturer_id, s.substation_id, w.window_start, w.window_end, "
    "pc.why_reason, pc.recommended_action "
    "FROM ops_alert_queue q "
    "JOIN priority_cards pc ON pc.card_id = q.card_id "
    "JOIN priority_decisions pd ON pd.priority_decision_id = pc.priority_decision_id "
    "JOIN windows w ON w.window_id = pd.window_id "
    "JOIN substations s ON s.substation_uid = w.substation_uid "
    "{where_sql} "
    "ORDER BY "
    "CASE q.priority_level WHEN 'urgent' THEN 0 ELSE 1 END, "
    "q.priority_score DESC NULLS LAST, q.created_at DESC, q.alert_id"
)


class HeatingAgentAlert(BaseModel):
    alert_id: str
    card_id: str
    priority_level: Literal["urgent", "high"]
    priority_score: float | None
    status: Literal["open", "acked"]
    enqueue_reason: str
    created_at: str
    acked_at: str | None
    acked_by: str | None
    manufacturer_id: str
    substation_id: int | str | None
    window_start: str
    window_end: str
    why_reason: str | None
    recommended_action: str | None


def register_heating_agent_routes(router: APIRouter, engine: AsyncEngine) -> None:
    @router.get("/heating-agent", include_in_schema=False)
    async def heating_agent() -> HTMLResponse:
        html = HEATING_AGENT_HTML.read_text(encoding="utf-8")
        return HTMLResponse(inject_bridge(html))

    @router.get("/heating-agent-bridge.js", include_in_schema=False)
    async def heating_agent_bridge() -> FileResponse:
        return FileResponse(BRIDGE_SCRIPT, media_type="application/javascript")

    @router.get(
        "/heating-agent/api/alerts",
        response_model=list[HeatingAgentAlert],
    )
    async def heating_agent_alerts(
        status: Literal["open", "acked", "all"] = "open",
        priority_level: Literal["urgent", "high"] | None = None,
    ) -> list[HeatingAgentAlert]:
        rows = await list_heating_agent_alerts(
            engine,
            status=status,
            priority_level=priority_level,
        )
        return [HeatingAgentAlert.model_validate(row) for row in rows]


def inject_bridge(html: str) -> str:
    if BRIDGE_TAG in html:
        return html
    if "</body>" in html:
        return html.replace("</body>", f"{BRIDGE_TAG}\n</body>", 1)
    return f"{html}\n{BRIDGE_TAG}\n"


async def list_heating_agent_alerts(
    engine: AsyncEngine,
    status: str,
    priority_level: str | None,
) -> list[dict[str, JsonValue]]:
    await ensure_alert_queue(engine)
    filters: list[str] = []
    params: dict[str, JsonValue] = {}
    if status != "all":
        filters.append("q.status = :status")
        params["status"] = status
    if priority_level is not None:
        filters.append("q.priority_level = :priority_level")
        params["priority_level"] = priority_level
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(HEATING_AGENT_ALERTS_SQL.format(where_sql=where_sql))
    async with engine.connect() as connection:
        result = await connection.execute(query, params)
    return [_alert_from_row(row) for row in result.mappings().all()]


def _alert_from_row(row: RowMapping) -> dict[str, JsonValue]:
    acked_at = row["acked_at"]
    return {
        "alert_id": str(row["alert_id"]),
        "card_id": str(row["card_id"]),
        "priority_level": row["priority_level"],
        "priority_score": _json_scalar(row["priority_score"]),
        "status": row["status"],
        "enqueue_reason": row["enqueue_reason"],
        "created_at": row["created_at"].isoformat(),
        "acked_at": None if acked_at is None else acked_at.isoformat(),
        "acked_by": row["acked_by"],
        "manufacturer_id": str(row["manufacturer_id"]),
        "substation_id": _json_scalar(row["substation_id"]),
        "window_start": row["window_start"].isoformat(),
        "window_end": row["window_end"].isoformat(),
        "why_reason": row["why_reason"],
        "recommended_action": row["recommended_action"],
    }


def _json_scalar(value: JsonValue | Decimal) -> JsonValue:
    return float(value) if isinstance(value, Decimal) else value
