from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from heatgrid_ops.db.migrations import (
    APPLICATION_TABLES_V011,
    CHECKPOINT_PACKAGE_VERSION,
    MigrationContractError,
    POSTGRESQL_MAJOR,
    _legacy_work_order_versions,
    _verify_application_catalog,
    load_migrations,
    migration_manifest_hash,
)


ROOT = Path(__file__).resolve().parents[1]


def _catalog_connection(tables: set[str] | frozenset[str]) -> AsyncMock:
    result = AsyncMock()
    result.fetchall.return_value = [
        {"tablename": table} for table in sorted(tables)
    ]
    connection = AsyncMock()
    connection.execute.return_value = result
    return connection


def test_migration_manifest_is_contiguous_and_stable() -> None:
    migrations = load_migrations()

    assert [migration.version for migration in migrations] == list(range(24))
    assert migrations[0].path.name == "000_schema_migrations.sql"
    assert migrations[-1].path.name == "023_final_test_demo_packages.sql"
    assert migrations[-1].hook_path is None
    assert len(migration_manifest_hash(migrations)) == 64


def test_final_test_demo_packages_are_seeded_and_read_only() -> None:
    sql = (
        ROOT / "migrations" / "023_final_test_demo_packages.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create table if not exists public.final_test_demo_packages" in sql
    assert "primary key" in sql
    assert "normal_payload jsonb" in sql
    assert "fault_payload jsonb" in sql
    assert "work_order_document jsonb" in sql
    assert "report_document jsonb" in sql
    assert "chat_script jsonb" in sql
    assert sql.count("final-test-fault-") >= 3
    assert "grant select on table public.final_test_demo_packages to heatgrid_app" in sql
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql


def test_legacy_work_order_migration_lineage_is_recognized() -> None:
    rows = [
        {"version": 19, "name": "work_order_structure", "checksum": "b41f709eb13e73679750c8cadc665ecf8763d427cfde2fe8a42ac24dcc366b44"},
        {"version": 20, "name": "work_order_equipment_catalog", "checksum": "9264acaaed5b488df3ff569114d5cfd3d7862002199219bb165b205ed882fa9c"},
        {"version": 21, "name": "demo_building_context", "checksum": "ee5de82fb1372579a45cf76679d95cc196910bfd8b2a31d76a10fa93c719e31c"},
    ]

    assert _legacy_work_order_versions(rows) == (19, 20, 21)


def test_unknown_legacy_work_order_checksum_is_rejected() -> None:
    rows = [{"version": 19, "name": "work_order_structure", "checksum": "0" * 64}]

    with pytest.raises(
        MigrationContractError,
        match="unsupported legacy work-order migration",
    ):
        _legacy_work_order_versions(rows)


def test_review_chat_scope_notice_migration_updates_only_message_kind_constraint() -> None:
    sql = (
        ROOT / "migrations" / "019_review_chat_scope_notice.sql"
    ).read_text(encoding="utf-8").lower()

    assert "alter table public.review_chat_messages" in sql
    assert "drop constraint if exists review_chat_messages_message_kind_check" in sql
    assert "'scope_notice'" in sql
    assert "drop table" not in sql
    assert "review_chat_action_proposals" not in sql


def test_production_operations_console_migration_is_repeat_safe_and_append_only() -> None:
    # Given: the forward-only operations console migration.
    sql = (
        ROOT / "migrations" / "016_production_operations_console.sql"
    ).read_text(encoding="utf-8").lower()

    # When: its schema contract is inspected.
    required_repeat_safe_tables = (
        "anomaly_episode_consumptions",
        "anomaly_episode_events",
        "anomaly_episodes",
        "preventive_projections",
        "operations_policy",
        "operations_shift_handover_memos",
        "operations_shift_schedule",
        "incident_document_versions",
        "incident_document_reviews",
        "operations_report_periods",
        "operations_report_versions",
        "operations_report_corrections",
        "operation_idempotency_keys",
    )

    # Then: all additions are repeat-safe and preserve the append-only lineages.
    for table in required_repeat_safe_tables:
        assert f"create table if not exists public.{table}" in sql
    assert "alter table public.ops_alert_queue add column if not exists read_at" in sql
    assert "alter table public.ops_alert_queue add column if not exists read_by" in sql
    assert "anomaly_episodes_one_active_per_asset_uidx" in sql
    assert "operations_report_versions_one_official_uidx" in sql
    assert "unique (report_period_id, version)" in sql
    assert "parent_document_version_id" in sql
    assert "prevent_append_only_mutation" in sql
    assert "drop table" not in sql
    assert "alter table public.ops_alert_queue drop" not in sql


def test_production_operations_console_migration_seeds_canonical_policy() -> None:
    # Given: the operations policy seed in migration 016.
    sql = (
        ROOT / "migrations" / "016_production_operations_console.sql"
    ).read_text(encoding="utf-8").lower()

    # When and Then: the approved KST, shift, freshness, and lifecycle defaults exist.
    assert "'asia/seoul'" in sql
    assert "'08:00'::time" in sql
    assert "'20:00'::time" in sql
    assert "freshness_threshold_minutes" in sql
    assert "30" in sql
    assert "anomaly_confirmations" in sql
    assert "recovery_confirmations" in sql
    assert "on conflict" in sql


def test_demo_ai_history_reset_uses_a_restricted_security_definer() -> None:
    sql = (
        ROOT / "migrations" / "017_demo_ai_history_reset.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create schema if not exists heatgrid_admin authorization current_user" in sql
    assert "security definer" in sql
    assert "set search_path = pg_catalog, pg_temp" in sql
    assert "truncate table public.agent_runs cascade" in sql
    assert "revoke all on schema heatgrid_admin from public" in sql
    assert "revoke create on schema heatgrid_admin from heatgrid_app" in sql
    assert "revoke all on function heatgrid_admin.reset_demo_ai_history() from public" in sql
    assert "grant execute on function heatgrid_admin.reset_demo_ai_history() to heatgrid_app" in sql
    assert "grant truncate" not in sql


def test_demo_ai_history_reset_scope_clears_ai_outputs_and_preserves_operations() -> None:
    sql = (
        ROOT / "migrations" / "018_demo_ai_history_reset_scope.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create or replace function heatgrid_admin.reset_demo_ai_history()" in sql
    assert "security definer" in sql
    assert "set search_path = pg_catalog, pg_temp" in sql
    assert "public.agent_runs," in sql
    assert "public.incident_document_versions," in sql
    assert "public.operation_idempotency_keys" in sql
    assert "cascade" in sql
    assert "revoke all on function heatgrid_admin.reset_demo_ai_history() from public" in sql
    assert "grant execute on function heatgrid_admin.reset_demo_ai_history() to heatgrid_app" in sql

    preserved_operational_roots = (
        "anomaly_episodes",
        "ops_alert_queue",
        "priority_cards",
        "operations_report_periods",
        "operations_report_versions",
        "operations_report_corrections",
    )
    for table in preserved_operational_roots:
        assert f"public.{table}" not in sql


@pytest.mark.anyio
async def test_runtime_catalog_accepts_production_operations_tables_at_v016() -> None:
    # Given: the database contains the v011 catalog plus migration 016's tables.
    operations_tables = {
        "anomaly_episode_consumptions",
        "anomaly_episode_events",
        "anomaly_episodes",
        "preventive_projections",
        "operations_policy",
        "operations_shift_handover_memos",
        "operations_shift_schedule",
        "incident_document_versions",
        "incident_document_reviews",
        "operations_report_periods",
        "operations_report_versions",
        "operations_report_corrections",
        "operation_idempotency_keys",
    }
    connection = _catalog_connection(APPLICATION_TABLES_V011 | operations_tables)

    # When and Then: the runtime contract accepts the final v016 catalog.
    await _verify_application_catalog(connection, 16)


@pytest.mark.anyio
async def test_runtime_catalog_preserves_v011_contract_before_v016() -> None:
    # Given: migration 015 still has the established v011 table catalog.
    connection = _catalog_connection(APPLICATION_TABLES_V011)

    # When and Then: runtime verification does not require v016 tables early.
    await _verify_application_catalog(connection, 15)


def test_agent_run_support_table_recovery_restores_final_contract() -> None:
    sql = (
        ROOT / "migrations" / "015_agent_run_support_table_recovery.sql"
    ).read_text().lower()

    assert "create table if not exists public.agent_run_events" in sql
    assert "create table if not exists public.agent_run_artifacts" in sql
    assert "create table if not exists public.agent_run_actions" in sql
    assert "agent_run_events_v3_snapshot_idx" in sql
    assert "agent_run_artifacts_output_lineage_uidx" in sql
    assert "on delete restrict" in sql


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


def test_normalized_runtime_writes_include_substation_uid() -> None:
    evaluation_source = (
        ROOT / "src" / "heatgrid_ops" / "priority" / "evaluation.py"
    ).read_text(encoding="utf-8")
    alert_queue_source = (ROOT / "scripts" / "ops_alert_queue.py").read_text(
        encoding="utf-8"
    )
    alert_repository_source = (
        ROOT
        / "simulator"
        / "versions"
        / "v2_postgres_react_ops"
        / "backend"
        / "alert_repository.py"
    ).read_text(encoding="utf-8")
    agent_run_repository_source = (
        ROOT
        / "simulator"
        / "versions"
        / "v2_postgres_react_ops"
        / "backend"
        / "agent_run_repository.py"
    ).read_text(encoding="utf-8")

    assert "s.substation_uid" in evaluation_source
    assert ":substation_uid" in evaluation_source
    assert "result.substation_uid" in alert_queue_source
    assert "q.substation_uid = c.substation_uid" in alert_queue_source
    assert "card.substation_uid" in alert_repository_source
    assert "ON CONFLICT (evaluation_run_id, substation_uid)" in alert_repository_source
    assert "SELECT substation_uid FROM ops_alert_queue" in agent_run_repository_source
    assert "SELECT root_run_id FROM agent_runs" in agent_run_repository_source


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
