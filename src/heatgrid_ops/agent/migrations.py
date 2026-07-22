from __future__ import annotations

from pathlib import Path
from typing import Final

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool


MIGRATION_LOCK_KEY: Final = "heatgrid:agent-migrations"


async def apply_migrations(
    pool: AsyncConnectionPool[AsyncConnection[DictRow]],
    migration_paths: tuple[Path, ...],
) -> None:
    async with pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (MIGRATION_LOCK_KEY,),
            )
            for migration_path in migration_paths:
                migration_sql = migration_path.read_text(encoding="utf-8")
                await connection.execute(
                    migration_sql.encode("utf-8"),
                    prepare=False,
                )
