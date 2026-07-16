from __future__ import annotations

from dataclasses import dataclass
import os
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Final, Literal

import orjson
from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from heatgrid_ops.db.migration_hook_registry import get_data_hook


MIGRATION_LOCK_KEY: Final = "heatgrid:database-migrations"
CHECKPOINT_PACKAGE: Final = "langgraph-checkpoint-postgres"
CHECKPOINT_PACKAGE_VERSION: Final = "3.1.0"
POSTGRESQL_MAJOR: Final = 16
CHECKPOINT_TABLES: Final = frozenset(
    {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}
)
CHECKPOINT_INDEXES: Final = frozenset(
    {
        "checkpoints_thread_id_idx",
        "checkpoint_blobs_thread_id_idx",
        "checkpoint_writes_thread_id_idx",
    }
)
APPLICATION_TABLES_V011: Final = frozenset(
    {
        "agent_budget_ledger",
        "agent_loop_iterations",
        "agent_model_calls",
        "agent_policy_candidates",
        "agent_rerun_requests",
        "agent_run_actions",
        "agent_run_artifacts",
        "agent_run_events",
        "agent_run_review_snapshots",
        "agent_run_reviews",
        "agent_run_tasks",
        "agent_runs",
        "agent_stage_snapshots",
        "agent_tool_calls",
        "automation_policy",
        "evidence_candidates",
        "fault_events",
        "human_review_tasks",
        "model_candidates",
        "model_deployments",
        "model_feature_snapshots",
        "model_outputs",
        "model_runs",
        "ops_alert_queue",
        "priority_card_review_reasons",
        "review_chat_action_proposals",
        "review_chat_events",
        "review_chat_messages",
        "review_chat_threads",
        "priority_cards",
        "priority_decisions",
        "priority_evaluation_results",
        "priority_evaluation_runs",
        "replay_dataset_files",
        "replay_datasets",
        "replay_latest_readings",
        "replay_run_commands",
        "replay_runs",
        "replay_stream_events",
        "replay_tick_batches",
        "replay_window_evaluations",
        "rag_chunks",
        "rag_documents",
        "retrain_jobs",
        "schema_migrations",
        "sensor_readings",
        "sensor_summaries",
        "substation_building_context",
        "substations",
        "training_feedback",
        "windows",
    }
)

class MigrationContractError(RuntimeError):
    pass


def _find_migrations_dir() -> Path:
    explicit = os.getenv("HEATGRID_MIGRATIONS_DIR")
    if explicit:
        candidate = Path(explicit).resolve()
        if candidate.is_dir() and list(candidate.glob("[0-9][0-9][0-9]_*.sql")):
            return candidate
    base_dir = Path(__file__).resolve().parent
    for ancestor in base_dir.parents:
        candidate = ancestor / "migrations"
        if candidate.is_dir() and list(candidate.glob("[0-9][0-9][0-9]_*.sql")):
            return candidate
    fallback = Path("/app") / "migrations"
    if fallback.is_dir() and list(fallback.glob("[0-9][0-9][0-9]_*.sql")):
        return fallback
    raise MigrationContractError("migration directory not found")


MIGRATIONS_DIR: Final = _find_migrations_dir()


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    hook_path: Path | None = None


@dataclass(frozen=True, slots=True)
class SchemaSignatures:
    application: str
    checkpoint: str


def load_migrations(directory: Path = MIGRATIONS_DIR) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        version_text, _, name = path.stem.partition("_")
        if not name:
            raise MigrationContractError(f"invalid migration filename: {path.name}")
        version = int(version_text)
        hook = directory / "hooks" / f"{version_text}.py"
        digest = sha256(path.read_bytes())
        if hook.exists():
            digest.update(b"\x00data-hook\x00")
            digest.update(hook.read_bytes())
        migrations.append(
            Migration(
                version=version,
                name=name,
                path=path,
                checksum=digest.hexdigest(),
                hook_path=hook if hook.exists() else None,
            )
        )
    expected = list(range(len(migrations)))
    if not migrations:
        raise MigrationContractError(f"no migration files found in {directory}")
    actual = [migration.version for migration in migrations]
    if actual != expected:
        raise MigrationContractError(
            f"migration versions must be contiguous from 000: expected={expected}, actual={actual}"
        )
    return tuple(migrations)


def migration_manifest_hash(migrations: tuple[Migration, ...]) -> str:
    payload = [
        {"version": item.version, "name": item.name, "checksum": item.checksum}
        for item in migrations
    ]
    return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


async def migrate_database(
    database_url: str,
    *,
    allow_baseline: bool = True,
) -> None:
    migrations = load_migrations()
    manifest_hash = migration_manifest_hash(migrations)
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        conninfo=_psycopg_url(database_url),
        min_size=1,
        max_size=1,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    await pool.open()
    try:
        async with pool.connection() as connection:
            await _assert_runtime_versions(connection)
            await connection.execute(
                "SELECT pg_advisory_lock(hashtext(%s))",
                (MIGRATION_LOCK_KEY,),
            )
            try:
                existing_schema = await _has_existing_application_schema(connection)
                await _apply_migration(
                    connection,
                    migrations[0],
                    manifest_hash=manifest_hash,
                    apply_mode="executed",
                )
                await _assert_applied_checksums(connection, migrations)
                if existing_schema and allow_baseline:
                    await _baseline_legacy_schema(connection, migrations, manifest_hash)
                for migration in migrations[1:]:
                    if await _is_applied(connection, migration.version):
                        continue
                    if migration.version == 4:
                        await _apply_checkpoint_migration(
                            connection,
                            migration,
                            manifest_hash=manifest_hash,
                        )
                    else:
                        await _apply_migration(
                            connection,
                            migration,
                            manifest_hash=manifest_hash,
                            apply_mode="executed",
                        )
                await _assert_applied_checksums(connection, migrations)
                await _verify_application_catalog(connection, migrations[-1].version)
                await _refresh_latest_contract(connection, migrations, manifest_hash)
            finally:
                await connection.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    (MIGRATION_LOCK_KEY,),
                )
    finally:
        await pool.close()


async def verify_database_contract(database_url: str) -> None:
    migrations = load_migrations()
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        conninfo=_psycopg_url(database_url),
        min_size=1,
        max_size=1,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    try:
        async with pool.connection() as connection:
            await _assert_runtime_versions(connection)
            await _assert_applied_checksums(connection, migrations)
            latest = await connection.execute(
                "SELECT version, manifest_hash, application_schema_signature, "
                "checkpoint_schema_signature FROM public.schema_migrations "
                "ORDER BY version DESC LIMIT 1"
            )
            row = await latest.fetchone()
            if row is None or int(row["version"]) != migrations[-1].version:
                raise MigrationContractError(
                    f"database must be at schema version {migrations[-1].version:03d}"
                )
            expected_manifest = migration_manifest_hash(migrations)
            if row["manifest_hash"] != expected_manifest:
                raise MigrationContractError("migration manifest hash mismatch")
            signatures = await calculate_schema_signatures(connection)
            if row["application_schema_signature"] != signatures.application:
                raise MigrationContractError("application schema signature mismatch")
            if row["checkpoint_schema_signature"] != signatures.checkpoint:
                raise MigrationContractError("checkpoint schema signature mismatch")
            await _verify_checkpoint_catalog(connection)
            await _verify_application_catalog(connection, migrations[-1].version)
    finally:
        await pool.close()


async def provision_application_role(
    database_url: str,
    *,
    app_role: str,
    app_password: str,
) -> None:
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        conninfo=_psycopg_url(database_url),
        min_size=1,
        max_size=1,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    try:
        async with pool.connection() as connection:
            role_result = await connection.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s) AS role_exists",
                (app_role,),
            )
            role_row = await role_result.fetchone()
            if role_row is None:
                raise MigrationContractError("failed to inspect PostgreSQL roles")
            if bool(role_row["role_exists"]):
                await connection.execute(
                    sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(app_role),
                        sql.Literal(app_password),
                    )
                )
            else:
                await connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(app_role),
                        sql.Literal(app_password),
                    )
                )
            await grant_application_role(connection, app_role=app_role)
    finally:
        await pool.close()


async def grant_application_role(
    connection: AsyncConnection[DictRow],
    *,
    app_role: str,
) -> None:
    role = sql.Identifier(app_role)
    await connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    await connection.execute(
        sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(role)
    )
    await connection.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(role)
    )
    await connection.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {}").format(role)
    )
    await connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role)
    )
    await connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE ON TABLES TO {}"
        ).format(role)
    )
    await connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(role)
    )


async def calculate_schema_signatures(
    connection: AsyncConnection[DictRow],
) -> SchemaSignatures:
    application = await _catalog_payload(connection, checkpoint=False)
    checkpoint = await _catalog_payload(connection, checkpoint=True)
    return SchemaSignatures(
        application=sha256(
            orjson.dumps(application, option=orjson.OPT_SORT_KEYS)
        ).hexdigest(),
        checkpoint=sha256(
            orjson.dumps(checkpoint, option=orjson.OPT_SORT_KEYS)
        ).hexdigest(),
    )


async def _apply_migration(
    connection: AsyncConnection[DictRow],
    migration: Migration,
    *,
    manifest_hash: str,
    apply_mode: Literal["executed", "baselined"],
) -> None:
    if await _is_applied(connection, migration.version):
        return
    async with connection.transaction():
        await connection.execute(migration.path.read_bytes(), prepare=False)
        await _run_data_hook(connection, migration)
        await _verify_application_catalog(connection, migration.version)
        signatures = await calculate_schema_signatures(connection)
        await _insert_ledger(
            connection,
            migration,
            apply_mode=apply_mode,
            manifest_hash=manifest_hash,
            application_signature=signatures.application,
            checkpoint_signature=signatures.checkpoint,
        )


async def _run_data_hook(
    connection: AsyncConnection[DictRow],
    migration: Migration,
) -> None:
    if migration.hook_path is None:
        return
    module_name = f"heatgrid_migration_hook_{migration.version:03d}"
    spec = spec_from_file_location(module_name, migration.hook_path)
    if spec is None or spec.loader is None:
        raise MigrationContractError(
            f"cannot load data hook for migration {migration.version:03d}"
        )
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    hook = get_data_hook(migration.version)
    if hook is None:
        raise MigrationContractError(
            f"data hook did not register migration {migration.version:03d}"
        )
    await hook(connection)


async def _apply_checkpoint_migration(
    connection: AsyncConnection[DictRow],
    migration: Migration,
    *,
    manifest_hash: str,
) -> None:
    async with connection.transaction():
        await connection.execute(migration.path.read_bytes(), prepare=False)
    checkpointer = _checkpoint_saver()(connection)
    await checkpointer.setup()
    await _verify_checkpoint_catalog(connection)
    signatures = await calculate_schema_signatures(connection)
    async with connection.transaction():
        await _insert_ledger(
            connection,
            migration,
            apply_mode="executed",
            manifest_hash=manifest_hash,
            application_signature=signatures.application,
            checkpoint_signature=signatures.checkpoint,
        )


async def _baseline_legacy_schema(
    connection: AsyncConnection[DictRow],
    migrations: tuple[Migration, ...],
    manifest_hash: str,
) -> None:
    required_by_version: dict[int, tuple[str, ...]] = {
        1: (
            "substations", "windows", "model_runs", "model_outputs",
            "priority_decisions", "priority_cards", "sensor_summaries",
            "rag_documents", "rag_chunks", "substation_building_context",
        ),
        2: (
            "ops_alert_queue", "agent_runs", "agent_run_events",
            "agent_run_artifacts", "agent_loop_iterations", "human_review_tasks",
            "training_feedback", "retrain_jobs", "model_candidates",
        ),
        3: ("priority_evaluation_runs", "priority_evaluation_results"),
        4: ("agent_run_tasks", "agent_budget_ledger"),
        5: ("agent_run_reviews", "agent_run_review_snapshots", "agent_policy_candidates"),
    }
    for migration in migrations[1:6]:
        if await _is_applied(connection, migration.version):
            continue
        missing = [
            name
            for name in required_by_version[migration.version]
            if not await _table_exists(connection, name)
        ]
        if missing:
            raise MigrationContractError(
                f"baseline preflight failed for {migration.version:03d}: missing {missing}"
            )
        if migration.version == 4:
            checkpointer = _checkpoint_saver()(connection)
            await checkpointer.setup()
            await _verify_checkpoint_catalog(connection)
        async with connection.transaction():
            await _insert_ledger(
                connection,
                migration,
                apply_mode="baselined",
                manifest_hash=manifest_hash,
                application_signature=None,
                checkpoint_signature=None,
            )


async def _insert_ledger(
    connection: AsyncConnection[DictRow],
    migration: Migration,
    *,
    apply_mode: Literal["executed", "baselined"],
    manifest_hash: str,
    application_signature: str | None,
    checkpoint_signature: str | None,
) -> None:
    components = {
        "langgraph_checkpoint_postgres": CHECKPOINT_PACKAGE_VERSION,
        "postgresql_major": POSTGRESQL_MAJOR,
    }
    await connection.execute(
        "INSERT INTO public.schema_migrations ("
        "version, name, checksum, apply_mode, component_versions, manifest_hash, "
        "application_schema_signature, checkpoint_schema_signature"
        ") VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)",
        (
            migration.version,
            migration.name,
            migration.checksum,
            apply_mode,
            orjson.dumps(components).decode(),
            manifest_hash,
            application_signature,
            checkpoint_signature,
        ),
    )


async def _refresh_latest_contract(
    connection: AsyncConnection[DictRow],
    migrations: tuple[Migration, ...],
    manifest_hash: str,
) -> None:
    signatures = await calculate_schema_signatures(connection)
    await connection.execute(
        "UPDATE public.schema_migrations SET manifest_hash = %s, "
        "application_schema_signature = %s, checkpoint_schema_signature = %s "
        "WHERE version = %s",
        (manifest_hash, signatures.application, signatures.checkpoint, migrations[-1].version),
    )


async def _assert_applied_checksums(
    connection: AsyncConnection[DictRow],
    migrations: tuple[Migration, ...],
) -> None:
    if not await _table_exists(connection, "schema_migrations"):
        return
    result = await connection.execute(
        "SELECT version, name, checksum FROM public.schema_migrations ORDER BY version"
    )
    rows = await result.fetchall()
    by_version = {migration.version: migration for migration in migrations}
    for row in rows:
        version = int(row["version"])
        migration = by_version.get(version)
        if migration is None:
            raise MigrationContractError(f"unknown applied migration version: {version:03d}")
        if row["name"] != migration.name or row["checksum"] != migration.checksum:
            raise MigrationContractError(f"migration checksum mismatch: {version:03d}")


async def _assert_runtime_versions(connection: AsyncConnection[DictRow]) -> None:
    result = await connection.execute("SHOW server_version_num")
    row = await result.fetchone()
    if row is None:
        raise MigrationContractError("PostgreSQL did not report server_version_num")
    major = int(str(row["server_version_num"])) // 10000
    if major != POSTGRESQL_MAJOR:
        raise MigrationContractError(
            f"PostgreSQL {POSTGRESQL_MAJOR} required; connected to {major}"
        )
    try:
        installed = package_version(CHECKPOINT_PACKAGE)
    except PackageNotFoundError as exc:
        raise MigrationContractError(
            f"{CHECKPOINT_PACKAGE} package is not installed"
        ) from exc
    if installed != CHECKPOINT_PACKAGE_VERSION:
        raise MigrationContractError(
            f"{CHECKPOINT_PACKAGE} {CHECKPOINT_PACKAGE_VERSION} required; installed {installed}"
        )


async def _verify_checkpoint_catalog(connection: AsyncConnection[DictRow]) -> None:
    table_result = await connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename = ANY(%s) ORDER BY tablename",
        (list(CHECKPOINT_TABLES),),
    )
    tables = {str(row["tablename"]) for row in await table_result.fetchall()}
    if tables != CHECKPOINT_TABLES:
        raise MigrationContractError(
            f"checkpoint tables mismatch: expected={sorted(CHECKPOINT_TABLES)}, actual={sorted(tables)}"
        )
    index_result = await connection.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
        "AND indexname = ANY(%s) ORDER BY indexname",
        (list(CHECKPOINT_INDEXES),),
    )
    indexes = {str(row["indexname"]) for row in await index_result.fetchall()}
    if indexes != CHECKPOINT_INDEXES:
        raise MigrationContractError(
            f"checkpoint indexes mismatch: expected={sorted(CHECKPOINT_INDEXES)}, actual={sorted(indexes)}"
        )
    version_result = await connection.execute(
        "SELECT array_agg(v ORDER BY v) AS versions FROM public.checkpoint_migrations"
    )
    version_row = await version_result.fetchone()
    if version_row is None:
        raise MigrationContractError("checkpoint migration catalog is unavailable")
    versions = list(version_row["versions"] or [])
    if versions != list(range(10)):
        raise MigrationContractError(f"checkpoint migration versions mismatch: {versions}")


async def _verify_application_catalog(
    connection: AsyncConnection[DictRow],
    version: int,
) -> None:
    # APPLICATION_TABLES_V011 includes replay_* tables created by migration 011,
    # so enforce from 011 onward; checking at 010 breaks fresh-database bootstrap.
    if version < 11:
        return
    result = await connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND NOT (tablename = ANY(%s)) ORDER BY tablename",
        (list(CHECKPOINT_TABLES),),
    )
    actual = {str(row["tablename"]) for row in await result.fetchall()}
    if actual != APPLICATION_TABLES_V011:
        raise MigrationContractError(
            "application tables mismatch: "
            f"expected={sorted(APPLICATION_TABLES_V011)}, actual={sorted(actual)}"
        )


async def _catalog_payload(
    connection: AsyncConnection[DictRow],
    *,
    checkpoint: bool,
) -> dict[str, object]:
    table_filter = "c.relname = ANY(%s)" if checkpoint else "NOT (c.relname = ANY(%s))"
    names = list(CHECKPOINT_TABLES)
    columns_result = await connection.execute(
        "SELECT c.relname AS table_name, a.attnum AS ordinal, a.attname AS column_name, "
        "pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type, "
        "a.attnotnull AS not_null, pg_get_expr(d.adbin, d.adrelid) AS column_default "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
        "LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND " + table_filter + " "
        "ORDER BY c.relname, a.attnum",
        (names,),
    )
    constraints_result = await connection.execute(
        "SELECT c.relname AS table_name, pc.conname, pc.contype, pc.convalidated, "
        "pg_get_constraintdef(pc.oid, true) AS definition "
        "FROM pg_constraint pc JOIN pg_class c ON c.oid = pc.conrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND " + table_filter + " "
        "ORDER BY c.relname, pc.conname",
        (names,),
    )
    indexes_result = await connection.execute(
        "SELECT tablename AS table_name, indexname, indexdef AS definition "
        "FROM pg_indexes WHERE schemaname = 'public' AND "
        + ("tablename = ANY(%s)" if checkpoint else "NOT (tablename = ANY(%s))")
        + " ORDER BY tablename, indexname",
        (names,),
    )
    payload: dict[str, object] = {
        "schema": "public",
        "columns": [dict(row) for row in await columns_result.fetchall()],
        "constraints": [dict(row) for row in await constraints_result.fetchall()],
        "indexes": [dict(row) for row in await indexes_result.fetchall()],
    }
    if checkpoint:
        if await _table_exists(connection, "checkpoint_migrations"):
            versions = await connection.execute(
                "SELECT v FROM public.checkpoint_migrations ORDER BY v"
            )
            payload["migration_versions"] = [
                int(row["v"]) for row in await versions.fetchall()
            ]
        else:
            payload["migration_versions"] = []
    else:
        extensions = await connection.execute(
            "SELECT extname, extversion FROM pg_extension ORDER BY extname"
        )
        payload["extensions"] = [dict(row) for row in await extensions.fetchall()]
    return payload


async def _has_existing_application_schema(connection: AsyncConnection[DictRow]) -> bool:
    return await _table_exists(connection, "substations") or await _table_exists(
        connection, "agent_runs"
    )


async def _table_exists(connection: AsyncConnection[DictRow], table_name: str) -> bool:
    result = await connection.execute(
        "SELECT to_regclass(%s) IS NOT NULL AS table_exists",
        (f"public.{table_name}",),
    )
    row = await result.fetchone()
    return False if row is None else bool(row["table_exists"])


async def _is_applied(connection: AsyncConnection[DictRow], version: int) -> bool:
    if not await _table_exists(connection, "schema_migrations"):
        return False
    result = await connection.execute(
        "SELECT EXISTS (SELECT 1 FROM public.schema_migrations WHERE version = %s) "
        "AS migration_exists",
        (version,),
    )
    row = await result.fetchone()
    return False if row is None else bool(row["migration_exists"])


def _psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _checkpoint_saver():
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except (ImportError, ModuleNotFoundError) as exc:
        raise MigrationContractError(
            f"{CHECKPOINT_PACKAGE} package is not installed"
        ) from exc
    return AsyncPostgresSaver
