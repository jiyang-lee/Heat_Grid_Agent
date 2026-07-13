from __future__ import annotations

from pathlib import Path
from typing import Final

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool


ROOT: Final = Path(__file__).resolve().parents[4]
MIGRATION_PATH: Final = ROOT / "docker" / "postgres" / "init" / "004_agent_execution.sql"
MIGRATION_LOCK_KEY: Final = "heatgrid:004-agent-execution"


async def apply_agent_execution_migration(
    pool: AsyncConnectionPool[AsyncConnection[DictRow]],
) -> None:
    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
    async with pool.connection() as connection:
        await connection.execute(
            "SELECT pg_advisory_lock(hashtext(%s))",
            (MIGRATION_LOCK_KEY,),
        )
        try:
            await connection.execute(
                migration_sql.encode("utf-8"),
                prepare=False,
            )
        finally:
            await connection.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))",
                (MIGRATION_LOCK_KEY,),
            )
