from __future__ import annotations

from pathlib import Path
from typing import Final

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool

from heatgrid_ops.agent.migrations import apply_migrations


ROOT: Final = Path(__file__).resolve().parents[4]
MIGRATION_PATHS: Final = (
    ROOT / "docker" / "postgres" / "init" / "004_agent_execution.sql",
    ROOT / "docker" / "postgres" / "init" / "005_agent_review.sql",
)
async def apply_agent_execution_migration(
    pool: AsyncConnectionPool[AsyncConnection[DictRow]],
) -> None:
    await apply_migrations(pool, MIGRATION_PATHS)
