from __future__ import annotations

from typing import Final

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from schemas import (
    AgentRunArtifact,
    AgentRunResponse,
    OpsAgentOutput,
    SimulationResponse,
    TokenUsage,
)

AGENT_RUNS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id uuid PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES ops_alert_queue(alert_id) ON DELETE CASCADE,
    card_id uuid NOT NULL REFERENCES priority_cards(card_id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('completed', 'failed')),
    agent_mode text CHECK (agent_mode IN ('llm', 'fallback')),
    ops_output jsonb,
    token_usage jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
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

AGENT_RUN_SELECT: Final = (
    "SELECT run_id, alert_id, card_id, status, agent_mode, "
    "CAST(ops_output AS text) AS ops_output, "
    "CAST(token_usage AS text) AS token_usage, error "
    "FROM agent_runs "
)


async def ensure_agent_run_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_RUNS_DDL))
        await connection.execute(text(AGENT_RUN_ARTIFACTS_DDL))


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
