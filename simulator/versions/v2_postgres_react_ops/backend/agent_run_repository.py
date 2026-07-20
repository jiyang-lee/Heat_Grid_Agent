from __future__ import annotations

from typing import Final

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_run_artifact_repository import ensure_agent_run_artifact_table
from agent_run_event_repository import (
    AgentRunEventRecord,
    ensure_agent_run_event_table,
    insert_agent_run_event,
)
from schemas import (
    AgentLoopSummary,
    AgentRunResponse,
    OpsAgentOutput,
    SimulationResponse,
    TokenUsage,
)

ACTIVE_AGENT_RUN_STALE_AFTER_SECONDS: Final = 600

AGENT_RUNS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id uuid PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES ops_alert_queue(alert_id) ON DELETE CASCADE,
    card_id uuid NOT NULL REFERENCES priority_cards(card_id) ON DELETE CASCADE,
    evaluation_run_id uuid,
    manufacturer_id text,
    substation_id integer,
    parent_run_id uuid REFERENCES agent_runs(run_id),
    trigger_type text NOT NULL DEFAULT 'alert',
    requested_by text,
    trigger_reason text,
    approved_action_task_id uuid,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    agent_mode text CHECK (agent_mode IN ('llm', 'fallback')),
    ops_output jsonb,
    token_usage jsonb,
    loop_summary jsonb,
    review_status text NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'corrected')),
    review_task_id uuid,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""

AGENT_RUNS_COMPATIBILITY_DDL: Final = (
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS loop_summary jsonb",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'pending'",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS review_task_id uuid",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS evaluation_run_id uuid",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS manufacturer_id text",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS substation_id integer",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS parent_run_id uuid REFERENCES agent_runs(run_id)",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS trigger_type text NOT NULL DEFAULT 'alert'",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS requested_by text",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS trigger_reason text",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS approved_action_task_id uuid",
)

DROP_AGENT_RUN_STATUS_CONSTRAINT_DDL: Final = """
ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check
"""

ADD_AGENT_RUN_STATUS_CONSTRAINT_DDL: Final = (
    "ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check "
    "CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled'))"
)

ADD_AGENT_RUN_STATUS_CONSTRAINT_DDL: Final = """
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check
CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled'))
"""

AGENT_RUN_SELECT: Final = (
    "SELECT run_id, alert_id, card_id, evaluation_run_id, manufacturer_id, "
    "substation_id, parent_run_id, trigger_type, requested_by, trigger_reason, "
    "approved_action_task_id, "
    "status, agent_mode, "
    "CAST(ops_output AS text) AS ops_output, "
    "CAST(token_usage AS text) AS token_usage, "
    "CAST(loop_summary AS text) AS loop_summary, "
    "review_status, review_task_id, error "
    "FROM agent_runs "
)


async def ensure_agent_run_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_RUNS_DDL))
        for statement in AGENT_RUNS_COMPATIBILITY_DDL:
            await connection.execute(text(statement))
        await connection.execute(text(DROP_AGENT_RUN_STATUS_CONSTRAINT_DDL))
        await connection.execute(text(ADD_AGENT_RUN_STATUS_CONSTRAINT_DDL))
    await ensure_agent_run_artifact_table(engine)
    await ensure_agent_run_event_table(engine)


async def create_queued_agent_run(
    engine: AsyncEngine,
    run_id: str,
    alert_id: str,
    card_id: str,
) -> AgentRunResponse:
    async with engine.begin() as connection:
        row = await _insert_queued_agent_run(
            connection,
            run_id=run_id,
            alert_id=alert_id,
            card_id=card_id,
        )
    return _run_from_row(row)


async def reserve_agent_run(
    engine: AsyncEngine,
    *,
    run_id: str,
    alert_id: str,
    card_id: str,
    force_new: bool = False,
    requested_by: str | None = None,
    reason: str | None = None,
    trigger_type: str | None = None,
    approved_action_task_id: str | None = None,
) -> tuple[AgentRunResponse, bool]:
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"agent-run:{alert_id}"},
        )
        await _expire_stale_agent_runs(connection, alert_id=alert_id)
        existing = await connection.execute(
            text(
                f"{AGENT_RUN_SELECT}"
                "WHERE alert_id = :alert_id AND status <> 'failed' "
                "ORDER BY created_at DESC, lineage_depth DESC, updated_at DESC LIMIT 1"
            ),
            {"alert_id": alert_id},
        )
        existing_row = existing.mappings().one_or_none()
        existing_status = None if existing_row is None else str(existing_row["status"])
        should_reuse = existing_row is not None and (
            existing_status in {"queued", "running"} or not force_new
        )
        if should_reuse and existing_row is not None:
            await insert_agent_run_event(
                connection,
                AgentRunEventRecord(
                    run_id=str(existing_row["run_id"]),
                    event_type="run_reused",
                    message="existing agent run reused",
                    payload={"requested_run_id": run_id, "alert_id": alert_id},
                ),
            )
            return _run_from_row(existing_row), False
        parent_run_id = None if existing_row is None else str(existing_row["run_id"])
        lineage_rollover = False
        if force_new and parent_run_id is not None:
            lineage_depth = await connection.scalar(
                text("SELECT lineage_depth FROM agent_runs WHERE run_id = :run_id"),
                {"run_id": parent_run_id},
            )
            if lineage_depth is not None and int(lineage_depth) >= 2:
                parent_run_id = None
                lineage_rollover = True
        run_row = await _insert_queued_agent_run(
            connection,
            run_id=run_id,
            alert_id=alert_id,
            card_id=card_id,
            parent_run_id=parent_run_id,
            trigger_type=trigger_type
            or (
                "manual_rerun_rollover"
                if lineage_rollover
                else "manual_rerun"
                if force_new
                else "alert"
            ),
            requested_by=requested_by,
            trigger_reason=reason,
            approved_action_task_id=approved_action_task_id,
        )
    return _run_from_row(run_row), True


async def _insert_queued_agent_run(
    connection: AsyncConnection,
    *,
    run_id: str,
    alert_id: str,
    card_id: str,
    parent_run_id: str | None = None,
    trigger_type: str = "alert",
    requested_by: str | None = None,
    trigger_reason: str | None = None,
    approved_action_task_id: str | None = None,
) -> RowMapping:
    query = text(
        "INSERT INTO agent_runs ("
        "run_id, alert_id, card_id, evaluation_run_id, substation_uid, manufacturer_id, "
        "substation_id, parent_run_id, root_run_id, lineage_depth, "
        "trigger_type, requested_by, trigger_reason, "
        "approved_action_task_id, status"
        ") VALUES ("
        ":run_id, :alert_id, :card_id, "
        "(SELECT evaluation_run_id FROM ops_alert_queue WHERE alert_id = :alert_id), "
        "(SELECT substation_uid FROM ops_alert_queue WHERE alert_id = :alert_id), "
        "(SELECT manufacturer_id FROM ops_alert_queue WHERE alert_id = :alert_id), "
        "(SELECT substation_id FROM ops_alert_queue WHERE alert_id = :alert_id), "
        ":parent_run_id, "
        "COALESCE((SELECT root_run_id FROM agent_runs WHERE run_id = :parent_run_id), :run_id), "
        "COALESCE((SELECT lineage_depth + 1 FROM agent_runs WHERE run_id = :parent_run_id), 0), "
        ":trigger_type, :requested_by, :trigger_reason, "
        ":approved_action_task_id, 'queued'"
        ") "
        "RETURNING run_id, alert_id, card_id, evaluation_run_id, manufacturer_id, "
        "substation_id, parent_run_id, trigger_type, requested_by, trigger_reason, "
        "approved_action_task_id, "
        "status, agent_mode, "
        "CAST(ops_output AS text) AS ops_output, "
        "CAST(token_usage AS text) AS token_usage, "
        "CAST(loop_summary AS text) AS loop_summary, "
        "review_status, review_task_id, error"
    )
    result = await connection.execute(
        query,
        {
            "run_id": run_id,
            "alert_id": alert_id,
            "card_id": card_id,
            "parent_run_id": parent_run_id,
            "trigger_type": trigger_type,
            "requested_by": requested_by,
            "trigger_reason": trigger_reason,
            "approved_action_task_id": approved_action_task_id,
        },
    )
    run_row = result.mappings().one()
    await insert_agent_run_event(
        connection,
        AgentRunEventRecord(
            run_id=run_id,
            event_type="run_queued",
            message="agent run queued",
            payload={
                "run_id": run_id,
                "alert_id": alert_id,
                "evaluation_run_id": None
                if run_row["evaluation_run_id"] is None
                else str(run_row["evaluation_run_id"]),
                "parent_run_id": parent_run_id,
                "trigger_type": trigger_type,
                "requested_by": requested_by,
                "reason": trigger_reason,
                "approved_action_task_id": approved_action_task_id,
            },
        ),
    )
    await insert_agent_run_event(
        connection,
        AgentRunEventRecord(
            run_id=run_id,
            event_type="status_changed",
            message="agent run queued",
            payload={"status": "queued"},
        ),
    )
    return run_row


async def _expire_stale_agent_runs(
    connection: AsyncConnection,
    *,
    run_id: str | None = None,
    alert_id: str | None = None,
) -> None:
    if run_id is None and alert_id is None:
        raise ValueError("run_id 또는 alert_id가 필요합니다.")
    identity_sql = "run_id = :run_id" if run_id is not None else "alert_id = :alert_id"
    params = {
        "run_id": run_id,
        "alert_id": alert_id,
        "stale_after_seconds": ACTIVE_AGENT_RUN_STALE_AFTER_SECONDS,
    }
    result = await connection.execute(
        text(
            "UPDATE agent_runs SET status = 'failed', "
            "error = 'agent run lease expired', updated_at = now() "
            f"WHERE {identity_sql} AND status IN ('queued', 'running') "
            "AND updated_at < now() - "
            "(:stale_after_seconds * interval '1 second') "
            "RETURNING run_id"
        ),
        params,
    )
    for row in result.mappings().all():
        expired_run_id = str(row["run_id"])
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=expired_run_id,
                event_type="status_changed",
                message="agent run lease expired",
                payload={"status": "failed"},
            ),
        )
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=expired_run_id,
                event_type="run_failed",
                message="agent run lease expired",
                payload={"error": "agent run lease expired"},
            ),
        )


async def mark_agent_run_running(engine: AsyncEngine, run_id: str) -> AgentRunResponse:
    run = await _set_agent_run_status(
        engine,
        AgentRunEventRecord(
            run_id=run_id,
            event_type="status_changed",
            message="agent run running",
            payload={"status": "running"},
        ),
    )
    await record_agent_run_event(
        engine,
        AgentRunEventRecord(
            run_id=run_id,
            event_type="run_started",
            message="agent graph execution started",
            payload={"status": "running"},
        ),
    )
    return run


async def complete_agent_run(
    engine: AsyncEngine,
    run_id: str,
    simulation: SimulationResponse,
    *,
    loop_summary: AgentLoopSummary | None = None,
    review_task_id: str | None = None,
) -> AgentRunResponse:
    query = text(
        "UPDATE agent_runs SET "
        "status = 'completed', agent_mode = :agent_mode, "
        "ops_output = CAST(:ops_output AS jsonb), "
        "token_usage = CAST(:token_usage AS jsonb), "
        "loop_summary = CAST(:loop_summary AS jsonb), "
        "review_status = 'pending', review_task_id = :review_task_id, "
        "error = NULL, updated_at = now() "
        "WHERE run_id = :run_id AND status IN ('queued', 'running') "
        "RETURNING run_id, alert_id, card_id, evaluation_run_id, manufacturer_id, "
        "substation_id, parent_run_id, trigger_type, requested_by, trigger_reason, "
        "approved_action_task_id, "
        "status, agent_mode, "
        "CAST(ops_output AS text) AS ops_output, "
        "CAST(token_usage AS text) AS token_usage, "
        "CAST(loop_summary AS text) AS loop_summary, "
        "review_status, review_task_id, error"
    )
    params = {
        "run_id": run_id,
        "agent_mode": simulation.agent_mode,
        "ops_output": orjson.dumps(
            simulation.ops_output.model_dump(mode="json")
        ).decode("utf-8"),
        "token_usage": orjson.dumps(
            simulation.token_usage.model_dump(mode="json")
        ).decode("utf-8"),
        "loop_summary": orjson.dumps(
            (loop_summary or AgentLoopSummary()).model_dump(mode="json")
        ).decode("utf-8"),
        "review_task_id": review_task_id,
    }
    async with engine.begin() as connection:
        result = await connection.execute(query, params)
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="status_changed",
                message="agent run completed",
                payload={"status": "completed"},
            ),
        )
        await insert_agent_run_event(
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


async def fail_agent_run(
    engine: AsyncEngine,
    run_id: str,
    error: str,
) -> AgentRunResponse:
    query = text(
        "UPDATE agent_runs SET "
        "status = 'failed', error = :error, updated_at = now() "
        "WHERE run_id = :run_id "
        "RETURNING run_id, alert_id, card_id, evaluation_run_id, manufacturer_id, "
        "substation_id, parent_run_id, trigger_type, requested_by, trigger_reason, "
        "approved_action_task_id, "
        "status, agent_mode, "
        "CAST(ops_output AS text) AS ops_output, "
        "CAST(token_usage AS text) AS token_usage, "
        "CAST(loop_summary AS text) AS loop_summary, "
        "review_status, review_task_id, error"
    )
    async with engine.begin() as connection:
        result = await connection.execute(query, {"run_id": run_id, "error": error})
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="status_changed",
                message="agent run failed",
                payload={"status": "failed"},
            ),
        )
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="run_failed",
                message="agent run failed",
                payload={"error": error},
            ),
        )
    return _run_from_row(result.mappings().one())


async def record_agent_run_event(
    engine: AsyncEngine,
    event: AgentRunEventRecord,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE agent_runs SET updated_at = now() WHERE run_id = :run_id"),
            {"run_id": event.run_id},
        )
        await insert_agent_run_event(connection, event)


async def get_agent_run(engine: AsyncEngine, run_id: str) -> AgentRunResponse | None:
    query = text(f"{AGENT_RUN_SELECT}WHERE run_id = :run_id")
    async with engine.begin() as connection:
        await _expire_stale_agent_runs(connection, run_id=run_id)
        result = await connection.execute(query, {"run_id": run_id})
    row = result.mappings().one_or_none()
    return None if row is None else _run_from_row(row)


async def cancel_queued_agent_run(
    engine: AsyncEngine,
    run_id: str,
) -> AgentRunResponse | None:
    query = text(
        "UPDATE agent_runs SET status = 'cancelled', error = NULL, updated_at = now() "
        "WHERE run_id = :run_id AND status = 'queued' "
        "RETURNING run_id, alert_id, card_id, evaluation_run_id, manufacturer_id, "
        "substation_id, parent_run_id, trigger_type, requested_by, trigger_reason, "
        "approved_action_task_id, status, agent_mode, "
        "CAST(ops_output AS text) AS ops_output, "
        "CAST(token_usage AS text) AS token_usage, "
        "CAST(loop_summary AS text) AS loop_summary, "
        "review_status, review_task_id, error"
    )
    async with engine.begin() as connection:
        result = await connection.execute(query, {"run_id": run_id})
        row = result.mappings().one_or_none()
        if row is None:
            return None
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="status_changed",
                message="agent run cancelled before execution",
                payload={"status": "cancelled"},
            ),
        )
    return _run_from_row(row)


async def _set_agent_run_status(
    engine: AsyncEngine,
    event: AgentRunEventRecord,
) -> AgentRunResponse:
    query = text(
        "UPDATE agent_runs SET status = :status, updated_at = now() "
        "WHERE run_id = :run_id "
        "RETURNING run_id, alert_id, card_id, evaluation_run_id, manufacturer_id, "
        "substation_id, parent_run_id, trigger_type, requested_by, trigger_reason, "
        "approved_action_task_id, "
        "status, agent_mode, "
        "CAST(ops_output AS text) AS ops_output, "
        "CAST(token_usage AS text) AS token_usage, "
        "CAST(loop_summary AS text) AS loop_summary, "
        "review_status, review_task_id, error"
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {"run_id": event.run_id, "status": event.payload["status"]},
        )
        await insert_agent_run_event(connection, event)
    return _run_from_row(result.mappings().one())


def _run_from_row(row: RowMapping) -> AgentRunResponse:
    ops_output = row["ops_output"]
    token_usage = row["token_usage"]
    loop_summary = row["loop_summary"]
    return AgentRunResponse(
        run_id=str(row["run_id"]),
        status=row["status"],
        input_source="alert",
        alert_id=str(row["alert_id"]),
        card_id=str(row["card_id"]),
        evaluation_run_id=None
        if row["evaluation_run_id"] is None
        else str(row["evaluation_run_id"]),
        manufacturer_id=row["manufacturer_id"],
        substation_id=row["substation_id"],
        parent_run_id=None
        if row["parent_run_id"] is None
        else str(row["parent_run_id"]),
        trigger_type=str(row["trigger_type"] or "alert"),
        requested_by=row["requested_by"],
        trigger_reason=row["trigger_reason"],
        approved_action_task_id=None
        if row["approved_action_task_id"] is None
        else str(row["approved_action_task_id"]),
        agent_mode=row["agent_mode"],
        ops_output=None
        if ops_output is None
        else OpsAgentOutput.model_validate(orjson.loads(ops_output)),
        token_usage=None
        if token_usage is None
        else TokenUsage.model_validate(orjson.loads(token_usage)),
        loop_summary=None
        if loop_summary is None
        else AgentLoopSummary.model_validate(orjson.loads(loop_summary)),
        review_status=str(row["review_status"] or "pending"),
        review_task_id=None
        if row["review_task_id"] is None
        else str(row["review_task_id"]),
        error=row["error"],
        # 일부 RETURNING 경로에는 created_at이 없어 .get으로 안전 처리(additive).
        created_at=row.get("created_at"),
    )
