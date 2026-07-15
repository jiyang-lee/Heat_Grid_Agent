from __future__ import annotations

from pathlib import Path

from heatgrid_ops.db.migrations import (
    CHECKPOINT_PACKAGE_VERSION,
    POSTGRESQL_MAJOR,
    load_migrations,
    migration_manifest_hash,
)


ROOT = Path(__file__).resolve().parents[1]


def test_migration_manifest_is_contiguous_and_stable() -> None:
    migrations = load_migrations()

    assert [migration.version for migration in migrations] == list(range(15))
    assert migrations[0].path.name == "000_schema_migrations.sql"
    assert migrations[-1].path.name == "014_replay_legacy_priority_index_cleanup.sql"
    assert migrations[-1].hook_path is None
    assert len(migration_manifest_hash(migrations)) == 64


def test_migration_ledger_records_baseline_and_contract_metadata() -> None:
    sql = (ROOT / "migrations" / "000_schema_migrations.sql").read_text()

    assert "apply_mode" in sql
    assert "component_versions" in sql
    assert "manifest_hash" in sql
    assert "application_schema_signature" in sql
    assert "checkpoint_schema_signature" in sql


def test_checkpoint_setup_is_outside_application_ddl_transaction() -> None:
    source = (ROOT / "src" / "heatgrid_ops" / "db" / "migrations.py").read_text()
    function = source[source.index("async def _apply_checkpoint_migration") :]

    transaction_end = function.index("checkpointer = _checkpoint_saver()(connection)")
    assert "async with connection.transaction()" in function[:transaction_end]
    assert "await checkpointer.setup()" in function[transaction_end:]
    assert function.index("await checkpointer.setup()") < function.index(
        "await _insert_ledger", transaction_end
    )


def test_runtime_python_has_no_schema_ddl() -> None:
    paths = (
        ROOT / "src" / "heatgrid_ops" / "priority" / "evaluation.py",
        ROOT / "scripts" / "predictor_db_schema.py",
        ROOT / "scripts" / "ops_alert_queue.py",
        ROOT
        / "simulator"
        / "versions"
        / "v2_postgres_react_ops"
        / "backend"
        / "server.py",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8").upper()
        assert "CREATE TABLE" not in source, path
        assert "ALTER TABLE" not in source, path


def test_runtime_versions_are_pinned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()

    assert CHECKPOINT_PACKAGE_VERSION == "3.1.0"
    assert 'langgraph-checkpoint-postgres==3.1.0' in pyproject
    assert POSTGRESQL_MAJOR == 16
    assert "pgvector/pgvector:pg16" in compose
    assert 'LANGGRAPH_STRICT_MSGPACK: "true"' in compose
    assert "condition: service_completed_successfully" in compose


def test_agent_stage_trace_migration_preserves_append_only_audit_contract() -> None:
    sql = (ROOT / "migrations" / "009_agent_stage_trace.sql").read_text().lower()

    assert "create table public.agent_model_calls" in sql
    assert "create table public.agent_tool_calls" in sql
    assert "operation_key text not null unique" in sql
    assert "foreign key (stage_snapshot_id)" in sql
    assert "unique (model_call_id, call_sequence)" in sql


def test_review_chat_migration_requires_proposal_confirmation_contract() -> None:
    sql = (ROOT / "migrations" / "010_review_chat.sql").read_text().lower()

    assert "create table public.review_chat_threads" in sql
    assert "create table public.review_chat_action_proposals" in sql
    assert "review_chat_threads_one_open_per_run" in sql
    assert "executed_review_id" in sql
    assert "decision <> 'reject' or reason_category is not null" in sql
