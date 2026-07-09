from typing import Final
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from schemas import AgentRunArtifact

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


async def ensure_agent_run_artifact_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_RUN_ARTIFACTS_DDL))


async def list_agent_run_artifacts(
    engine: AsyncEngine,
    run_id: str,
) -> list[AgentRunArtifact]:
    await ensure_agent_run_artifact_table(engine)
    query = text(
        "SELECT artifact_id, run_id, kind, name, uri "
        "FROM agent_run_artifacts "
        "WHERE run_id = :run_id "
        "ORDER BY created_at, artifact_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    return [_artifact_from_row(row) for row in result.mappings().all()]


async def insert_agent_run_artifact(
    engine: AsyncEngine,
    *,
    run_id: str,
    kind: str,
    name: str,
    uri: str,
    artifact_id: str | None = None,
) -> AgentRunArtifact:
    await ensure_agent_run_artifact_table(engine)
    artifact_id = artifact_id or str(uuid4())
    query = text(
        "INSERT INTO agent_run_artifacts (artifact_id, run_id, kind, name, uri) "
        "VALUES (:artifact_id, :run_id, :kind, :name, :uri) "
        "RETURNING artifact_id, run_id, kind, name, uri"
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {
                "artifact_id": artifact_id,
                "run_id": run_id,
                "kind": kind,
                "name": name,
                "uri": uri,
            },
        )
    return _artifact_from_row(result.mappings().one())


def _artifact_from_row(row: RowMapping) -> AgentRunArtifact:
    return AgentRunArtifact(
        artifact_id=str(row["artifact_id"]),
        run_id=str(row["run_id"]),
        kind=str(row["kind"]),
        name=str(row["name"]),
        uri=str(row["uri"]),
    )
