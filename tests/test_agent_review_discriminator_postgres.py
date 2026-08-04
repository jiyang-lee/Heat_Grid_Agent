from __future__ import annotations

from asyncio import SelectorEventLoop
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest
from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from heatgrid_ops.agent.migrations import apply_migrations


ROOT: Final = Path(__file__).resolve().parents[1]
MIGRATION: Final = ROOT / "migrations" / "005_agent_review.sql"
DEFAULT_DATABASE_URL: Final = (
    "postgresql://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
)


@pytest.fixture
def anyio_backend():
    return ("asyncio", {"loop_factory": SelectorEventLoop})


@pytest.mark.anyio
async def test_clean_review_migration_defers_future_run_default() -> None:
    async with _isolated_database() as pool:
        await apply_migrations(pool, (MIGRATION,))
        async with pool.connection() as connection:
            await connection.execute(
                "CREATE TABLE agent_runs ("
                "run_id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now()"
                ")"
            )

        await apply_migrations(pool, (MIGRATION,))
        run_id = str(uuid4())
        async with pool.connection() as connection:
            await connection.execute(
                "INSERT INTO agent_runs (run_id) VALUES (%s)",
                (run_id,),
            )
            cursor = await connection.execute(
                "SELECT review_snapshot_expected FROM agent_runs WHERE run_id = %s",
                (run_id,),
            )
            row = await cursor.fetchone()

        assert row is not None
        assert row["review_snapshot_expected"] is True


@pytest.mark.anyio
async def test_existing_review_migration_preserves_legacy_null_on_repeat() -> None:
    async with _isolated_database() as pool:
        legacy_run_id = str(uuid4())
        new_run_id = str(uuid4())
        async with pool.connection() as connection:
            await connection.execute(
                "CREATE TABLE agent_runs ("
                "run_id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now()"
                ")"
            )
            await connection.execute(
                "INSERT INTO agent_runs (run_id) VALUES (%s)",
                (legacy_run_id,),
            )

        await apply_migrations(pool, (MIGRATION,))
        async with pool.connection() as connection:
            await connection.execute(
                "INSERT INTO agent_runs (run_id) VALUES (%s)",
                (new_run_id,),
            )
        await apply_migrations(pool, (MIGRATION,))

        async with pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT run_id, review_snapshot_expected FROM agent_runs "
                "ORDER BY run_id"
            )
            rows = {str(row["run_id"]): row["review_snapshot_expected"] for row in await cursor.fetchall()}

        assert rows[legacy_run_id] is None
        assert rows[new_run_id] is True


@asynccontextmanager
async def _isolated_database() -> AsyncIterator[
    AsyncConnectionPool[AsyncConnection[DictRow]]
]:
    source_url = os.getenv("HEATGRID_TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    database_name = f"heatgrid_v3_review_{uuid4().hex}"
    admin_pool = _pool(_database_url(source_url, "postgres"))
    database_pool = _pool(_database_url(source_url, database_name))
    await admin_pool.open()
    try:
        async with admin_pool.connection() as connection:
            await connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
            )
        await database_pool.open()
        try:
            yield database_pool
        finally:
            await database_pool.close()
    finally:
        async with admin_pool.connection() as connection:
            await connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
        await admin_pool.close()


def _database_url(source_url: str, database: str) -> str:
    url = make_url(source_url).set(drivername="postgresql", database=database)
    return url.render_as_string(hide_password=False)


def _pool(
    database_url: str,
) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
    return AsyncConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=1,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
