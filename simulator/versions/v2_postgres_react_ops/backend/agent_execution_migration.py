from __future__ import annotations

from typing import cast

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool

from heatgrid_ops.db.migrations import migrate_database


async def apply_agent_execution_migration(
    pool: AsyncConnectionPool[AsyncConnection[DictRow]],
) -> None:
    await migrate_database(cast(str, pool.conninfo))
