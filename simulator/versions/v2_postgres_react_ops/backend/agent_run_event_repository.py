from dataclasses import dataclass
from typing import Final

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from schemas import AgentRunEvent, JsonObject

AGENT_RUN_EVENTS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_run_events (
    event_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    event_type text NOT NULL,
    message text NOT NULL,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True, slots=True)
class AgentRunEventRecord:
    run_id: str
    event_type: str
    message: str
    payload: JsonObject


async def ensure_agent_run_event_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_RUN_EVENTS_DDL))


async def record_agent_run_event(
    engine: AsyncEngine,
    event: AgentRunEventRecord,
) -> None:
    await ensure_agent_run_event_table(engine)
    async with engine.begin() as connection:
        await insert_agent_run_event(connection, event)


async def insert_agent_run_event(
    connection: AsyncConnection,
    event: AgentRunEventRecord,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO agent_run_events (run_id, event_type, message, payload) "
            "VALUES (:run_id, :event_type, :message, CAST(:payload AS jsonb))"
        ),
        {
            "run_id": event.run_id,
            "event_type": event.event_type,
            "message": event.message,
            "payload": orjson.dumps(event.payload).decode("utf-8"),
        },
    )


async def list_agent_run_events(
    engine: AsyncEngine,
    run_id: str,
) -> list[AgentRunEvent]:
    await ensure_agent_run_event_table(engine)
    query = text(
        "SELECT event_id, run_id, event_type, message, CAST(payload AS text) AS payload "
        "FROM agent_run_events "
        "WHERE run_id = :run_id "
        "ORDER BY event_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    return [_event_from_row(row) for row in result.mappings().all()]


def _event_from_row(row: RowMapping) -> AgentRunEvent:
    payload = row["payload"]
    return AgentRunEvent(
        event_id=int(row["event_id"]),
        run_id=str(row["run_id"]),
        event_type=str(row["event_type"]),
        message=str(row["message"]),
        payload=None if payload is None else orjson.loads(payload),
    )
