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

AGENT_RUN_ACTIONS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_run_actions (
    run_id uuid NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    action_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    requested_by text,
    artifact_id uuid REFERENCES agent_run_artifacts(artifact_id) ON DELETE SET NULL,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, action_name)
)
"""


async def ensure_agent_run_artifact_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_RUN_ARTIFACTS_DDL))
        await connection.execute(
            text(
                "DELETE FROM agent_run_artifacts duplicate USING agent_run_artifacts kept "
                "WHERE duplicate.run_id = kept.run_id AND duplicate.name = kept.name "
                "AND (duplicate.created_at, duplicate.artifact_id) > "
                "(kept.created_at, kept.artifact_id)"
            )
        )
        await connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS agent_run_artifact_run_name_idx "
                "ON agent_run_artifacts(run_id, name)"
            )
        )
        await connection.execute(text(AGENT_RUN_ACTIONS_DDL))


async def list_agent_run_artifacts(
    engine: AsyncEngine,
    run_id: str,
) -> list[AgentRunArtifact]:
    query = text(
        "SELECT artifact_id, run_id, kind, name, uri, created_at "
        "FROM agent_run_artifacts "
        "WHERE run_id = :run_id "
        "ORDER BY created_at, artifact_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    return [_artifact_from_row(row) for row in result.mappings().all()]


async def get_agent_run_artifact(
    engine: AsyncEngine,
    *,
    run_id: str,
    name: str,
) -> AgentRunArtifact | None:
    query = text(
        "SELECT artifact_id, run_id, kind, name, uri "
        "FROM agent_run_artifacts WHERE run_id = :run_id AND name = :name "
        "ORDER BY created_at LIMIT 1"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id, "name": name})
    row = result.mappings().one_or_none()
    return None if row is None else _artifact_from_row(row)


async def get_agent_run_artifact_by_id(
    engine: AsyncEngine,
    *,
    run_id: str,
    artifact_id: str,
) -> AgentRunArtifact | None:
    query = text(
        "SELECT artifact_id, run_id, kind, name, uri "
        "FROM agent_run_artifacts "
        "WHERE run_id = :run_id AND artifact_id = :artifact_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(
            query,
            {"run_id": run_id, "artifact_id": artifact_id},
        )
    row = result.mappings().one_or_none()
    return None if row is None else _artifact_from_row(row)


async def claim_agent_run_action(
    engine: AsyncEngine,
    *,
    run_id: str,
    action_name: str,
    requested_by: str | None = None,
) -> bool:
    query = text(
        "INSERT INTO agent_run_actions (run_id, action_name, status, requested_by) "
        "VALUES (:run_id, :action_name, 'running', :requested_by) "
        "ON CONFLICT (run_id, action_name) DO UPDATE SET "
        "status = 'running', error = NULL, updated_at = now() "
        "WHERE agent_run_actions.status = 'failed' "
        "OR agent_run_actions.updated_at < now() - interval '10 minutes' "
        "RETURNING run_id"
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {
                "run_id": run_id,
                "action_name": action_name,
                "requested_by": requested_by,
            },
        )
    return result.mappings().one_or_none() is not None


async def complete_agent_run_action(
    engine: AsyncEngine,
    *,
    run_id: str,
    action_name: str,
    artifact_id: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE agent_run_actions SET status = 'completed', "
                "artifact_id = :artifact_id, error = NULL, updated_at = now() "
                "WHERE run_id = :run_id AND action_name = :action_name"
            ),
            {
                "run_id": run_id,
                "action_name": action_name,
                "artifact_id": artifact_id,
            },
        )


async def fail_agent_run_action(
    engine: AsyncEngine,
    *,
    run_id: str,
    action_name: str,
    error: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE agent_run_actions SET status = 'failed', error = :error, "
                "updated_at = now() WHERE run_id = :run_id AND action_name = :action_name"
            ),
            {"run_id": run_id, "action_name": action_name, "error": error[:1000]},
        )


async def insert_agent_run_artifact(
    engine: AsyncEngine,
    *,
    run_id: str,
    kind: str,
    name: str,
    uri: str,
    artifact_id: str | None = None,
    source_output_hash: str | None = None,
    source_review_id: str | None = None,
    contract_version: str | None = None,
) -> AgentRunArtifact:
    artifact_id = artifact_id or str(uuid4())
    query = text(
        "INSERT INTO agent_run_artifacts (artifact_id, run_id, kind, name, uri) "
        "VALUES (:artifact_id, :run_id, :kind, :name, :uri) "
        "ON CONFLICT (run_id, name) DO UPDATE SET "
        "kind = EXCLUDED.kind, uri = EXCLUDED.uri "
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
                "source_output_hash": source_output_hash,
                "source_review_id": source_review_id,
                "contract_version": contract_version
                or (
                    "artifact.legacy-v1"
                    if source_output_hash is None
                    else "artifact.output-v2"
                ),
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
        created_at=row.get("created_at"),
    )
