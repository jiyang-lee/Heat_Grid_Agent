from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from schemas import (
    AgentRunArtifact,
    AgentRunEvent,
    AgentRunResponse,
    JsonValue,
    OpsAgentOutput,
    SimulationResponse,
    TokenUsage,
)

AGENT_RUNS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id uuid PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES ops_alert_queue(alert_id) ON DELETE CASCADE,
    card_id uuid NOT NULL REFERENCES priority_cards(card_id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    agent_mode text CHECK (agent_mode IN ('llm', 'fallback')),
    ops_output jsonb,
    token_usage jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""

DROP_AGENT_RUN_STATUS_CONSTRAINT_DDL: Final = """
ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check
"""

ADD_AGENT_RUN_STATUS_CONSTRAINT_DDL: Final = """
ALTER TABLE agent_runs
ADD CONSTRAINT agent_runs_status_check
CHECK (status IN ('queued', 'running', 'completed', 'failed'))
"""

AGENT_RUN_ARTIFACTS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_run_artifacts (
    artifact_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    kind text NOT NULL,
    name text NOT NULL,
    uri text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

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

AGENT_RUN_SELECT: Final = (
    "SELECT run_id, alert_id, card_id, status, agent_mode, "
    "CAST(ops_output AS text) AS ops_output, "
    "CAST(token_usage AS text) AS token_usage, error "
    "FROM agent_runs "
)


@dataclass(frozen=True, slots=True)
class AgentRunEventRecord:
    run_id: str
    event_type: str
    message: str
    payload: dict[str, JsonValue]


async def ensure_agent_run_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_RUNS_DDL))
        await connection.execute(text(DROP_AGENT_RUN_STATUS_CONSTRAINT_DDL))
        await connection.execute(text(ADD_AGENT_RUN_STATUS_CONSTRAINT_DDL))
        await connection.execute(text(AGENT_RUN_ARTIFACTS_DDL))
        await connection.execute(text(AGENT_RUN_EVENTS_DDL))


async def save_completed_agent_run(
    engine: AsyncEngine,
    run_id: str,
    alert_id: str,
    simulation: SimulationResponse,
) -> AgentRunResponse:
    await ensure_agent_run_tables(engine)
    query = text(
        "INSERT INTO agent_runs ("
        "run_id, alert_id, card_id, status, agent_mode, ops_output, token_usage"
        ") VALUES ("
        ":run_id, :alert_id, :card_id, 'completed', :agent_mode, "
        "CAST(:ops_output AS jsonb), CAST(:token_usage AS jsonb)"
        ") "
        "RETURNING run_id, alert_id, card_id, status, agent_mode, "
        "CAST(ops_output AS text) AS ops_output, "
        "CAST(token_usage AS text) AS token_usage, error"
    )
    params = {
        "run_id": run_id,
        "alert_id": alert_id,
        "card_id": simulation.card_id,
        "agent_mode": simulation.agent_mode,
        "ops_output": orjson.dumps(
            simulation.ops_output.model_dump(mode="json")
        ).decode("utf-8"),
        "token_usage": orjson.dumps(
            simulation.token_usage.model_dump(mode="json")
        ).decode("utf-8"),
    }
    async with engine.begin() as connection:
        result = await connection.execute(query, params)
        await _insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="run_started",
                message="agent run started",
                payload={"run_id": run_id, "alert_id": alert_id},
            ),
        )
        await _insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="status_changed",
                message="agent run completed",
                payload={"status": "completed"},
            ),
        )
        await _insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="run_completed",
                message="agent run completed",
                payload={
                    "run_id": run_id,
                    "status": "completed",
                    "card_id": simulation.card_id,
                    "agent_mode": simulation.agent_mode,
                },
            ),
        )
    return _run_from_row(result.mappings().one())


async def get_agent_run(engine: AsyncEngine, run_id: str) -> AgentRunResponse | None:
    await ensure_agent_run_tables(engine)
    query = text(f"{AGENT_RUN_SELECT}WHERE run_id = :run_id")
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    row = result.mappings().one_or_none()
    return None if row is None else _run_from_row(row)


async def list_agent_run_artifacts(
    engine: AsyncEngine,
    run_id: str,
) -> list[AgentRunArtifact] | None:
    await ensure_agent_run_tables(engine)
    run = await get_agent_run(engine, run_id)
    if run is None:
        return None
    query = text(
        "SELECT artifact_id, run_id, kind, name, uri "
        "FROM agent_run_artifacts "
        "WHERE run_id = :run_id "
        "ORDER BY created_at, artifact_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    return [_artifact_from_row(row) for row in result.mappings().all()]


async def list_agent_run_events(
    engine: AsyncEngine,
    run_id: str,
) -> list[AgentRunEvent] | None:
    await ensure_agent_run_tables(engine)
    run = await get_agent_run(engine, run_id)
    if run is None:
        return None
    query = text(
        "SELECT event_id, run_id, event_type, message, CAST(payload AS text) AS payload "
        "FROM agent_run_events "
        "WHERE run_id = :run_id "
        "ORDER BY event_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    return [_event_from_row(row) for row in result.mappings().all()]


async def _insert_agent_run_event(
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


def _run_from_row(row: RowMapping) -> AgentRunResponse:
    ops_output = row["ops_output"]
    token_usage = row["token_usage"]
    return AgentRunResponse(
        run_id=str(row["run_id"]),
        status=row["status"],
        input_source="alert",
        alert_id=str(row["alert_id"]),
        card_id=str(row["card_id"]),
        agent_mode=row["agent_mode"],
        ops_output=None
        if ops_output is None
        else OpsAgentOutput.model_validate(orjson.loads(ops_output)),
        token_usage=None
        if token_usage is None
        else TokenUsage.model_validate(orjson.loads(token_usage)),
        error=row["error"],
    )


def _artifact_from_row(row: RowMapping) -> AgentRunArtifact:
    return AgentRunArtifact(
        artifact_id=str(row["artifact_id"]),
        run_id=str(row["run_id"]),
        kind=str(row["kind"]),
        name=str(row["name"]),
        uri=str(row["uri"]),
    )


def _event_from_row(row: RowMapping) -> AgentRunEvent:
    payload = row["payload"]
    return AgentRunEvent(
        event_id=int(row["event_id"]),
        run_id=str(row["run_id"]),
        event_type=str(row["event_type"]),
        message=str(row["message"]),
        payload=None if payload is None else orjson.loads(payload),
    )
