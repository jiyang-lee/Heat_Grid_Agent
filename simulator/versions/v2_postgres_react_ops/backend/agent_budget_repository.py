from __future__ import annotations

from typing import Final
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


PARENT_TOKEN_LIMIT: Final = 20_000
PARENT_RETRY_LIMIT: Final = 3
EXTERNAL_SEARCH_LIMIT: Final = 0


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


def _budget_operation_key(run_id: str) -> str:
    return f"agent-budget:{run_id}"
