from __future__ import annotations

from typing import Final
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from heatgrid_ops.agent.diagnostics import DiagnosticBudgetReservation


PARENT_TOKEN_LIMIT: Final = 60_000
PARENT_RETRY_LIMIT: Final = 3
EXTERNAL_SEARCH_LIMIT: Final = 0
DIAGNOSTIC_TASK_KEY: Final = "fault_diagnosis:v1"


async def reserve_parent_budget(
    connection: AsyncConnection,
    *,
    run_id: str,
    task_id: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO agent_budget_ledger ("
            "ledger_id, run_id, task_id, operation_key, token_limit, retry_limit, "
            "external_search_limit"
            ") VALUES ("
            ":ledger_id, :run_id, :task_id, :operation_key, :token_limit, "
            ":retry_limit, :external_search_limit"
            ") ON CONFLICT (operation_key) DO NOTHING"
        ),
        {
            "ledger_id": str(uuid4()),
            "run_id": run_id,
            "task_id": task_id,
            "operation_key": _budget_operation_key(run_id),
            "token_limit": PARENT_TOKEN_LIMIT,
            "retry_limit": PARENT_RETRY_LIMIT,
            "external_search_limit": EXTERNAL_SEARCH_LIMIT,
        },
    )


async def settle_parent_budget(
    connection: AsyncConnection,
    *,
    run_id: str,
    tokens_used: int,
) -> None:
    result = await connection.execute(
        text(
            "UPDATE agent_budget_ledger SET status = 'settled', "
            "tokens_used = :tokens_used, settled_at = now(), updated_at = now() "
            "WHERE operation_key = :operation_key AND status = 'reserved' "
            "AND :tokens_used <= token_limit RETURNING ledger_id"
        ),
        {
            "operation_key": _budget_operation_key(run_id),
            "tokens_used": tokens_used,
        },
    )
    if result.mappings().one_or_none() is None:
        raise RuntimeError("agent run token budget could not be settled")


async def reserve_diagnostic_budget(
    engine: AsyncEngine,
    *,
    run_id: str,
    token_limit: int,
) -> DiagnosticBudgetReservation:
    operation_key = _diagnostic_operation_key(run_id)
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:operation_key))"),
            {"operation_key": operation_key},
        )
        existing = await _existing_reservation(connection, operation_key)
        if existing is not None:
            return existing
        parent_result = await connection.execute(
            text(
                "SELECT parent.ledger_id, parent.task_id, parent.token_limit, "
                "COALESCE((SELECT SUM(child.token_limit) FROM agent_budget_ledger child "
                "WHERE child.parent_ledger_id = parent.ledger_id "
                "AND child.status IN ('reserved', 'settled')), 0) AS child_tokens "
                "FROM agent_budget_ledger parent "
                "WHERE parent.operation_key = :parent_key AND parent.status = 'reserved'"
            ),
            {"parent_key": _budget_operation_key(run_id)},
        )
        parent = parent_result.mappings().one_or_none()
        if parent is None or int(parent["child_tokens"]) + token_limit > int(
            parent["token_limit"]
        ):
            return DiagnosticBudgetReservation(
                granted=False,
                reason="parent_token_budget_unavailable",
            )
        reservation_id = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO agent_budget_ledger ("
                "ledger_id, run_id, task_id, parent_ledger_id, operation_key, "
                "token_limit, retry_limit, external_search_limit"
                ") VALUES ("
                ":ledger_id, :run_id, :task_id, :parent_ledger_id, :operation_key, "
                ":token_limit, 1, 0)"
            ),
            {
                "ledger_id": reservation_id,
                "run_id": run_id,
                "task_id": str(parent["task_id"]),
                "parent_ledger_id": str(parent["ledger_id"]),
                "operation_key": operation_key,
                "token_limit": token_limit,
            },
        )
    return DiagnosticBudgetReservation(
        reservation_id=reservation_id,
        granted=True,
    )


async def finish_diagnostic_budget(
    engine: AsyncEngine,
    *,
    reservation_id: str,
    tokens_used: int,
    model_called: bool,
) -> None:
    status = "settled" if model_called else "released"
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "UPDATE agent_budget_ledger SET status = :status, "
                "tokens_used = :tokens_used, settled_at = now(), updated_at = now() "
                "WHERE ledger_id = :ledger_id AND status = 'reserved' "
                "AND :tokens_used <= token_limit RETURNING ledger_id"
            ),
            {
                "ledger_id": reservation_id,
                "status": status,
                "tokens_used": tokens_used if model_called else 0,
            },
        )
        if result.mappings().one_or_none() is None:
            raise RuntimeError("diagnostic token budget could not be settled")


async def _existing_reservation(
    connection: AsyncConnection,
    operation_key: str,
) -> DiagnosticBudgetReservation | None:
    result = await connection.execute(
        text(
            "SELECT ledger_id, status FROM agent_budget_ledger "
            "WHERE operation_key = :operation_key"
        ),
        {"operation_key": operation_key},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    if str(row["status"]) == "reserved":
        return DiagnosticBudgetReservation(
            reservation_id=str(row["ledger_id"]),
            granted=True,
        )
    return DiagnosticBudgetReservation(
        granted=False,
        reason="diagnostic_budget_already_consumed",
    )


def _budget_operation_key(run_id: str) -> str:
    return f"agent-budget:{run_id}"


def _diagnostic_operation_key(run_id: str) -> str:
    return f"diagnostic-budget:{run_id}:{DIAGNOSTIC_TASK_KEY}"
