from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final
from uuid import uuid4

import anyio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
APP_DATABASE_URL = os.getenv("HEATGRID_OPERATIONS_POLICY_TEST_DATABASE_URL")
ADMIN_DATABASE_URL = os.getenv("HEATGRID_OPERATIONS_POLICY_ADMIN_TEST_DATABASE_URL")
APP_PASSWORD = os.getenv("HEATGRID_OPERATIONS_POLICY_TEST_APP_PASSWORD", "heatgrid_app")
MIGRATION_CLI = Path(sys.executable).with_name("heatgrid-db-migrate.exe")
APPEND_ONLY_TABLES: Final = (
    "incident_document_versions",
    "incident_document_reviews",
    "operations_report_versions",
    "operations_report_corrections",
)
sys.path.insert(0, str(BACKEND))

from operations_policy_api_models import (  # noqa: E402
    OperationsPolicyResponse,
    OperationsPolicyUpdateRequest,
)
from operations_policy_repository import (  # noqa: E402
    PostgresOperationsPolicyRepository,
)


pytestmark = pytest.mark.skipif(
    APP_DATABASE_URL is None or ADMIN_DATABASE_URL is None,
    reason=(
        "HEATGRID_OPERATIONS_POLICY_TEST_DATABASE_URL and "
        "HEATGRID_OPERATIONS_POLICY_ADMIN_TEST_DATABASE_URL are required"
    ),
)


def _same_policy_update(policy: OperationsPolicyResponse) -> OperationsPolicyUpdateRequest:
    return OperationsPolicyUpdateRequest(
        expected_version=policy.version,
        timezone=policy.timezone,
        freshness_threshold_minutes=policy.freshness_threshold_minutes,
        anomaly_confirmations=policy.anomaly_confirmations,
        recovery_confirmations=policy.recovery_confirmations,
        shifts=policy.shifts,
    )


async def _replace_schedule(database_url: str) -> tuple[int, int]:
    engine = create_async_engine(database_url)
    repository = PostgresOperationsPolicyRepository(engine)
    try:
        policy = await repository.get_policy()
        updated = await repository.update_policy(
            _same_policy_update(policy),
            updated_by="operator",
        )
        return policy.version, updated.version
    finally:
        await engine.dispose()


async def _revoke_schedule_delete(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "REVOKE DELETE ON TABLE public.operations_shift_schedule "
                    "FROM heatgrid_app"
                )
            )
    finally:
        await engine.dispose()


async def _assert_append_only_privileges(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            for table_name in APPEND_ONLY_TABLES:
                can_select = await connection.scalar(
                    text(
                        "SELECT has_table_privilege(current_user, "
                        "CAST(:table_name AS text), 'SELECT')"
                    ),
                    {"table_name": f"public.{table_name}"},
                )
                can_insert = await connection.scalar(
                    text(
                        "SELECT has_table_privilege(current_user, "
                        "CAST(:table_name AS text), 'INSERT')"
                    ),
                    {"table_name": f"public.{table_name}"},
                )
                can_update = await connection.scalar(
                    text(
                        "SELECT has_table_privilege(current_user, "
                        "CAST(:table_name AS text), 'UPDATE')"
                    ),
                    {"table_name": f"public.{table_name}"},
                )
                assert can_select is True
                assert can_insert is True
                assert can_update is False
    finally:
        await engine.dispose()


async def _insert_append_only_lineage(database_url: str) -> None:
    engine = create_async_engine(database_url)
    lineage_id = uuid4()
    manufacturer_id = f"qa-{lineage_id.hex[:12]}"
    period_start = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO substations "
                    "(manufacturer_id, substation_id, configuration_type, substation_uid) "
                    "VALUES (:manufacturer_id, 9901, 'qa', :substation_uid)"
                ),
                {"manufacturer_id": manufacturer_id, "substation_uid": lineage_id},
            )
            episode_id = await connection.scalar(
                text(
                    "INSERT INTO anomaly_episodes "
                    "(stream_key, manufacturer_id, substation_id, lifecycle_status) "
                    "VALUES (:stream_key, :manufacturer_id, 9901, 'pending') "
                    "RETURNING episode_id"
                ),
                {"stream_key": f"qa:{lineage_id}", "manufacturer_id": manufacturer_id},
            )
            document_version_id = await connection.scalar(
                text(
                    "INSERT INTO incident_document_versions "
                    "(episode_id, document_type, version, status, content, content_hash, created_by) "
                    "VALUES (:episode_id, 'work_order', 1, 'draft', '{}'::jsonb, "
                    ":content_hash, 'operator') RETURNING document_version_id"
                ),
                {"episode_id": episode_id, "content_hash": "a" * 64},
            )
            await connection.execute(
                text(
                    "INSERT INTO incident_document_reviews "
                    "(document_version_id, review_type, decision, note, actor) "
                    "VALUES (:document_version_id, 'operator_note', 'pending', "
                    "'qa insert', 'operator')"
                ),
                {"document_version_id": document_version_id},
            )
            report_period_id = await connection.scalar(
                text(
                    "INSERT INTO operations_report_periods "
                    "(report_type, period_start, period_end, timezone, status, operation_key) "
                    "VALUES ('shift', :period_start, :period_end, 'Asia/Seoul', 'pending', "
                    ":operation_key) RETURNING report_period_id"
                ),
                {
                    "period_start": period_start,
                    "period_end": period_start + timedelta(hours=1),
                    "operation_key": f"qa:{lineage_id}",
                },
            )
            first_report_version_id = await connection.scalar(
                text(
                    "INSERT INTO operations_report_versions "
                    "(report_period_id, version, content, content_hash, generated_by) "
                    "VALUES (:report_period_id, 1, '{}'::jsonb, :content_hash, 'operator') "
                    "RETURNING report_version_id"
                ),
                {"report_period_id": report_period_id, "content_hash": "b" * 64},
            )
            second_report_version_id = await connection.scalar(
                text(
                    "INSERT INTO operations_report_versions "
                    "(report_period_id, version, source_report_version_id, content, "
                    "content_hash, generated_by) VALUES (:report_period_id, 2, "
                    ":source_report_version_id, '{}'::jsonb, :content_hash, 'operator') "
                    "RETURNING report_version_id"
                ),
                {
                    "report_period_id": report_period_id,
                    "source_report_version_id": first_report_version_id,
                    "content_hash": "c" * 64,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO operations_report_corrections "
                    "(source_report_version_id, corrected_report_version_id, reason, created_by) "
                    "VALUES (:source_report_version_id, :corrected_report_version_id, "
                    "'qa insert', 'operator')"
                ),
                {
                    "source_report_version_id": first_report_version_id,
                    "corrected_report_version_id": second_report_version_id,
                },
            )
    finally:
        await engine.dispose()


def test_app_role_replaces_schedule_for_both_role_provision_orders() -> None:
    # Given: a dedicated database with the application role provisioned before migrations.
    assert APP_DATABASE_URL is not None
    assert ADMIN_DATABASE_URL is not None
    environment = os.environ.copy()
    environment["HEATGRID_MIGRATION_DATABASE_URL"] = ADMIN_DATABASE_URL
    environment["HEATGRID_APP_PASSWORD"] = APP_PASSWORD
    subprocess.run(
        [MIGRATION_CLI, "provision-role"],
        check=True,
        env=environment,
    )
    subprocess.run([MIGRATION_CLI, "migrate"], check=True, env=environment)
    subprocess.run([MIGRATION_CLI, "migrate"], check=True, env=environment)

    # When: the app role replaces the schedule using migration-time grants.
    first_version, first_updated_version = anyio.run(
        _replace_schedule,
        APP_DATABASE_URL,
    )

    # Then: migration-time provisioning permits the committed replacement.
    assert first_updated_version == first_version + 1
    anyio.run(_assert_append_only_privileges, APP_DATABASE_URL)
    anyio.run(_insert_append_only_lineage, APP_DATABASE_URL)

    # Given: schedule DELETE is revoked before post-migration role provisioning.
    anyio.run(_revoke_schedule_delete, ADMIN_DATABASE_URL)
    subprocess.run(
        [MIGRATION_CLI, "provision-role"],
        check=True,
        env=environment,
    )

    # When: the app role replaces the schedule after post-migration provisioning.
    second_version, second_updated_version = anyio.run(
        _replace_schedule,
        APP_DATABASE_URL,
    )

    # Then: the narrow provisioning grant restores the repository contract.
    assert second_updated_version == second_version + 1
    anyio.run(_assert_append_only_privileges, APP_DATABASE_URL)
    anyio.run(_insert_append_only_lineage, APP_DATABASE_URL)
