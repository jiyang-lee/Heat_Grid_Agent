from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from heatgrid_ops.priority.evaluation import (
    AmbiguousSubstationError,
    _resolve_substation_result,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "007_database_normalization.sql"
DATABASE_URL = os.getenv("HEATGRID_V3_REVIEW_TEST_DATABASE_URL")


def test_database_normalization_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "substation_uid uuid" in sql
    assert "primary key (substation_uid)" in sql
    assert "unique (manufacturer_id, substation_id)" in sql
    assert "subject_type" in sql
    assert "subject_key" in sql
    assert "review_contract_version" in sql
    assert "training_feedback_source_review_id_fkey" in sql
    assert "drop column if exists approved_action_task_id" in sql
    assert "drop table if exists public.window_features" in sql
    assert "drop table if exists public.feature_meta_map" in sql
    assert "drop table if exists public.llm_ops_notes" in sql
    assert "validate constraint" in sql


def test_natural_key_resolution_rejects_ambiguous_ids() -> None:
    rows = [
        {"substation_uid": "uid-a", "manufacturer_id": "a", "substation_id": 31},
        {"substation_uid": "uid-b", "manufacturer_id": "b", "substation_id": 31},
    ]

    with pytest.raises(AmbiguousSubstationError):
        _resolve_substation_result(
            rows,
            substation_id=31,
            manufacturer_id=None,
        )
    assert _resolve_substation_result(
        rows,
        substation_id=31,
        manufacturer_id="b",
    ) == rows[1]


@pytest.mark.anyio
@pytest.mark.skipif(
    DATABASE_URL is None,
    reason="HEATGRID_V3_REVIEW_TEST_DATABASE_URL is required",
)
async def test_v007_database_has_validated_references_and_id_allowlist() -> None:
    allowlist = set(
        json.loads(
            (ROOT / "migrations" / "id_reference_allowlist.json").read_text(
                encoding="utf-8"
            )
        )
    )
    engine = create_async_engine(str(DATABASE_URL))
    try:
        async with engine.connect() as connection:
            invalid_fks = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint constraint_row "
                    "JOIN pg_class relation ON relation.oid = constraint_row.conrelid "
                    "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'public' AND constraint_row.contype = 'f' "
                    "AND NOT constraint_row.convalidated"
                )
            )
            loose_result = await connection.execute(
                text(
                    "SELECT columns.table_name || '.' || columns.column_name AS reference "
                    "FROM information_schema.columns columns "
                    "JOIN pg_class relation ON relation.relname = columns.table_name "
                    "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                    "AND namespace.nspname = columns.table_schema "
                    "JOIN pg_attribute attribute ON attribute.attrelid = relation.oid "
                    "AND attribute.attname = columns.column_name "
                    "WHERE columns.table_schema = 'public' "
                    "AND columns.column_name LIKE '%\\_id' ESCAPE '\\' "
                    "AND columns.data_type <> 'ARRAY' "
                    "AND NOT EXISTS ("
                    "SELECT 1 FROM pg_constraint constraint_row "
                    "WHERE constraint_row.conrelid = relation.oid "
                    "AND attribute.attnum = ANY(constraint_row.conkey)) "
                    "ORDER BY reference"
                )
            )
            loose_ids = {str(row["reference"]) for row in loose_result.mappings()}
            legacy_result = await connection.execute(
                text(
                    "SELECT to_regclass('public.feature_meta_map') AS feature_meta_map, "
                    "to_regclass('public.window_features') AS window_features, "
                    "to_regclass('public.llm_ops_notes') AS llm_ops_notes, "
                    "to_regclass('public.ops_agent_runs') AS ops_agent_runs"
                )
            )
            legacy = legacy_result.mappings().one()
    finally:
        await engine.dispose()

    assert invalid_fks == 0
    assert loose_ids == allowlist
    assert all(value is None for value in legacy.values())
