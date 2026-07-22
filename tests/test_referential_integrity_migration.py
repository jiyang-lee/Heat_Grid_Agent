from __future__ import annotations

from pathlib import Path
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]
MIGRATION: Final = (
    ROOT / "migrations" / "006_referential_integrity.sql"
)


def test_referential_integrity_migration_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "ops_alert_queue_evaluation_run_id_fkey" in sql
    assert "agent_runs_evaluation_run_id_fkey" in sql
    assert "ops_alert_queue_substation_fkey" in sql
    assert "agent_runs_substation_fkey" in sql
    assert sql.count("not valid") >= 7
    assert "confdeltype = 'c'" in sql
    assert "validate constraint" in sql
    assert "drop table if exists public.ops_retrieval_hits" in sql
    assert "drop table if exists public.ops_tool_calls" in sql
    assert "drop table if exists public.ops_agent_runs" in sql
    assert "drop table if exists public.ops_retrieval_hits cascade" not in sql
    assert "drop table if exists public.ops_tool_calls cascade" not in sql
    assert "drop table if exists public.ops_agent_runs cascade" not in sql
