from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

import anyio
import pytest
from psycopg import AsyncConnection, errors
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from heatgrid_ops.agent.migrations import (
    MIGRATION_LOCK_KEY,
    apply_migrations,
)
ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.versions.v2_postgres_react_ops.backend.selector_loop import (  # noqa: E402
    selector_event_loop_factory,
)


DEFAULT_DATABASE_URL: Final = (
    "postgresql://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
)


def test_migration_failure_preserves_error_and_releases_lock(tmp_path: Path) -> None:
    anyio.run(
        _assert_failure_path,
        tmp_path,
        backend_options={"loop_factory": selector_event_loop_factory},
    )


async def _assert_failure_path(tmp_path: Path) -> None:
    valid = tmp_path / "004_valid.sql"
    invalid = tmp_path / "005_invalid.sql"
    valid.write_text("SELECT 1;", encoding="utf-8")
    invalid.write_text(
        "SELECT * FROM heatgrid_v3_missing_migration_relation;",
        encoding="utf-8",
    )
    database_url = os.environ.get("HEATGRID_TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    migration_pool = _pool(database_url)
    observer_pool = _pool(database_url)
    await migration_pool.open()
    await observer_pool.open()
    try:
        with pytest.raises(errors.UndefinedTable) as captured:
            await apply_migrations(migration_pool, (valid, invalid))

        assert "heatgrid_v3_missing_migration_relation" in str(captured.value)
        async with observer_pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired",
                (MIGRATION_LOCK_KEY,),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["acquired"] is True
            await connection.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))",
                (MIGRATION_LOCK_KEY,),
            )
    finally:
        await observer_pool.close()
        await migration_pool.close()


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
