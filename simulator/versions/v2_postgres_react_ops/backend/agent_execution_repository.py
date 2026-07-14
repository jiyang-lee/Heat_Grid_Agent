from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_budget_repository import reserve_parent_budget, settle_parent_budget
from heatgrid_ops.agent.models import JsonObject


AGENT_GRAPH_TASK_KEY_V1: Final = "agent_graph:v1"
AGENT_GRAPH_TASK_KEY_V2: Final = "agent_graph:v2"
AGENT_GRAPH_TASK_KEY: Final = AGENT_GRAPH_TASK_KEY_V1
AGENT_GRAPH_TASK_KEYS: Final = (AGENT_GRAPH_TASK_KEY_V1, AGENT_GRAPH_TASK_KEY_V2)
TASK_LEASE_SECONDS: Final = 120


@dataclass(frozen=True, slots=True)
class AgentTaskClaim:
    claimed: bool
    resume_from_checkpoint: bool = False
    attempt_count: int = 0
    lease_owner: str | None = None


@dataclass(frozen=True, slots=True)
class ReclaimableAgentRun:
    run_id: str
    alert_id: str
    card_id: str
    task_key: str


async def claim_agent_graph_task(
    engine: AsyncEngine,
    *,
    run_id: str,
    input_snapshot: JsonObject,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
    input_schema_version: str | None = None,
    input_hash: str | None = None,
    input_snapshot_origin: str = "native_v2",
    input_snapshot_status: str = "unavailable",
) -> AgentTaskClaim:
    lease_owner = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:operation_key))"),
            {"operation_key": _task_operation_key(run_id)},
        )
        task_id = await _ensure_task(
            connection,
            run_id,
            input_snapshot,
            task_key=task_key,
            input_schema_version=input_schema_version,
            input_hash=input_hash,
            input_snapshot_origin=input_snapshot_origin,
            input_snapshot_status=input_snapshot_status,
        )
        await reserve_parent_budget(connection, run_id=run_id, task_id=task_id)
        result = await connection.execute(
            text(
                "UPDATE agent_run_tasks SET "
                "status = 'running', lease_owner = :lease_owner, "
                "lease_expires_at = now() + (:lease_seconds * interval '1 second'), "
                "attempt_count = attempt_count + 1, error = NULL, "
                "checkpoint_id = COALESCE(("
                "SELECT checkpoint_id FROM checkpoints "
                "WHERE thread_id = :checkpoint_thread_id "
                "ORDER BY checkpoint_id DESC LIMIT 1"
                "), checkpoint_id), updated_at = now() "
                "WHERE run_id = :run_id AND task_key = :task_key "
                "AND status <> 'completed' AND attempt_count < max_attempts "
                "AND (status IN ('queued', 'failed') "
                "OR lease_expires_at IS NULL OR lease_expires_at <= now()) "
                "RETURNING checkpoint_id, attempt_count"
            ),
            {
                "run_id": run_id,
                "checkpoint_thread_id": run_id,
                "task_key": task_key,
                "lease_owner": lease_owner,
                "lease_seconds": TASK_LEASE_SECONDS,
            },
        )
        row = result.mappings().one_or_none()
    if row is None:
        return AgentTaskClaim(claimed=False)
    return AgentTaskClaim(
        claimed=True,
        resume_from_checkpoint=row["checkpoint_id"] is not None,
        attempt_count=int(row["attempt_count"]),
        lease_owner=lease_owner,
    )


async def complete_agent_graph_task(
    engine: AsyncEngine,
    *,
    run_id: str,
    lease_owner: str,
    output_snapshot: JsonObject,
    tokens_used: int,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
) -> None:
    async with engine.begin() as connection:
        task_result = await connection.execute(
            text(
                "UPDATE agent_run_tasks SET status = 'completed', "
                "checkpoint_id = COALESCE(("
                "SELECT checkpoint_id FROM checkpoints "
                "WHERE thread_id = :checkpoint_thread_id "
                "ORDER BY checkpoint_id DESC LIMIT 1"
                "), checkpoint_id), output_snapshot = CAST(:output_snapshot AS jsonb), "
                "lease_owner = NULL, lease_expires_at = NULL, error = NULL, "
                "updated_at = now() WHERE run_id = :run_id AND task_key = :task_key "
                "AND lease_owner = :lease_owner"
                " RETURNING task_id"
            ),
            {
                "run_id": run_id,
                "checkpoint_thread_id": run_id,
                "task_key": task_key,
                "lease_owner": lease_owner,
                "output_snapshot": _json(output_snapshot),
            },
        )
        if task_result.mappings().one_or_none() is None:
            raise RuntimeError("agent task lease was lost before completion")
        await settle_parent_budget(
            connection,
            run_id=run_id,
            tokens_used=tokens_used,
        )


async def release_agent_graph_task(
    engine: AsyncEngine,
    *,
    run_id: str,
    lease_owner: str,
    error: str,
    task_key: str = AGENT_GRAPH_TASK_KEY_V1,
) -> bool:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "UPDATE agent_run_tasks SET "
                "status = CASE WHEN attempt_count < max_attempts "
                "THEN 'queued' ELSE 'failed' END, "
                "checkpoint_id = COALESCE(("
                "SELECT checkpoint_id FROM checkpoints "
                "WHERE thread_id = :checkpoint_thread_id "
                "ORDER BY checkpoint_id DESC LIMIT 1"
                "), checkpoint_id), lease_owner = NULL, lease_expires_at = NULL, "
                "error = :error, updated_at = now() "
                "WHERE run_id = :run_id AND task_key = :task_key "
                "AND lease_owner = :lease_owner "
                "RETURNING status"
            ),
            {
                "run_id": run_id,
                "checkpoint_thread_id": run_id,
                "task_key": task_key,
                "lease_owner": lease_owner,
                "error": error[:2000],
            },
        )
        row = result.mappings().one_or_none()
    return row is not None and str(row["status"]) == "queued"


async def list_reclaimable_agent_runs(
    engine: AsyncEngine,
) -> list[ReclaimableAgentRun]:
    query = text(
        "SELECT runs.run_id, runs.alert_id, runs.card_id, tasks.task_key "
        "FROM agent_run_tasks tasks "
        "JOIN agent_runs runs ON runs.run_id = tasks.run_id "
        "WHERE tasks.task_key = ANY(:task_keys) AND tasks.attempt_count < tasks.max_attempts "
        "AND (tasks.status = 'queued' OR (tasks.status = 'running' "
        "AND tasks.lease_expires_at <= now())) "
        "AND runs.status IN ('queued', 'running') ORDER BY tasks.created_at"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"task_keys": list(AGENT_GRAPH_TASK_KEYS)})
    return [
        ReclaimableAgentRun(
            run_id=str(row["run_id"]),
            alert_id=str(row["alert_id"]),
            card_id=str(row["card_id"]),
            task_key=str(row["task_key"]),
        )
        for row in result.mappings().all()
    ]


async def _ensure_task(
    connection: AsyncConnection,
    run_id: str,
    input_snapshot: JsonObject,
    *,
    task_key: str,
    input_schema_version: str | None,
    input_hash: str | None,
    input_snapshot_origin: str,
    input_snapshot_status: str,
) -> str:
    task_id = str(uuid4())
    result = await connection.execute(
        text(
            "INSERT INTO agent_run_tasks ("
            "task_id, run_id, task_key, operation_key, checkpoint_thread_id, input_snapshot, "
            "input_schema_version, input_hash, input_snapshot_origin, input_snapshot_status"
            ") VALUES ("
            ":task_id, :run_id, :task_key, :operation_key, :checkpoint_thread_id, "
            "CAST(:input_snapshot AS jsonb), :input_schema_version, :input_hash, "
            ":input_snapshot_origin, :input_snapshot_status) "
            "ON CONFLICT (run_id, task_key) DO UPDATE SET "
            "input_snapshot = COALESCE(agent_run_tasks.input_snapshot, EXCLUDED.input_snapshot), "
            "input_schema_version = COALESCE(agent_run_tasks.input_schema_version, "
            "EXCLUDED.input_schema_version), input_hash = COALESCE(agent_run_tasks.input_hash, "
            "EXCLUDED.input_hash), input_snapshot_origin = EXCLUDED.input_snapshot_origin, "
            "input_snapshot_status = EXCLUDED.input_snapshot_status "
            "RETURNING task_id"
        ),
        {
            "task_id": task_id,
            "run_id": run_id,
            "task_key": task_key,
            "operation_key": _task_operation_key(run_id),
            "checkpoint_thread_id": run_id,
            "input_snapshot": _json(input_snapshot),
            "input_schema_version": input_schema_version,
            "input_hash": input_hash,
            "input_snapshot_origin": input_snapshot_origin,
            "input_snapshot_status": input_snapshot_status,
        },
    )
    return str(result.scalar_one())


def _task_operation_key(run_id: str) -> str:
    return f"agent-graph:{run_id}"


def _json(value: JsonObject) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
