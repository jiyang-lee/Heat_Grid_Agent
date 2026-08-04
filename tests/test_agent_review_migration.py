from __future__ import annotations

from pathlib import Path
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]
MIGRATION: Final = ROOT / "migrations" / "005_agent_review.sql"
RUNNER: Final = (
    ROOT
    / "simulator"
    / "versions"
    / "v2_postgres_react_ops"
    / "backend"
    / "agent_execution_migration.py"
)
LOCK_EXECUTOR: Final = ROOT / "src" / "heatgrid_ops" / "agent" / "migrations.py"


def test_agent_review_migration_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists agent_run_review_snapshots" in sql
    assert "primary key (run_id)" in sql
    assert "create table if not exists agent_run_reviews" in sql
    assert "unique (run_id, review_version)" in sql
    assert "unique (run_id, idempotency_key)" in sql
    assert "request_hash" in sql
    assert "create table if not exists agent_policy_candidates" in sql
    assert "source_review_id uuid not null unique" in sql
    assert "version integer not null default 1" in sql
    assert "agent_run_review_snapshots_run_id_fkey" in sql
    assert "agent_run_reviews_run_id_fkey" in sql
    assert "add column if not exists review_snapshot_expected boolean" in sql
    assert "alter column review_snapshot_expected set default true" in sql
    assert "review_snapshot_expected boolean default true" not in sql


def test_agent_review_migration_defers_agent_run_foreign_keys() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "to_regclass('public.agent_runs') is not null" in sql
    assert "to_regclass('public.agent_run_review_snapshots') is not null" in sql
    assert "to_regclass('public.agent_run_reviews') is not null" in sql


def test_migration_manifest_applies_004_then_005_under_one_lock() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    executor_source = LOCK_EXECUTOR.read_text(encoding="utf-8")

    assert "migrate_database" in source
    assert "pool.conninfo" in source
    assert "apply_migrations" in executor_source

def test_agent_review_constraints_default_to_restrict() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert sql.count("on delete restrict") == 3
    assert "on delete cascade" not in sql
