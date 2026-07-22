from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final
from uuid import uuid4

import anyio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND: Final = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
DATABASE_URL: Final = os.getenv(
    "HEATGRID_OPERATIONS_REPORTS_TEST_DATABASE_URL",
    os.getenv(
        "HEATGRID_DATABASE_URL",
        "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops",
    ),
)
sys.path.insert(0, str(BACKEND))

from simulator.versions.v2_postgres_react_ops.backend.operations_report_repository import (  # noqa: E402
    PostgresOperationsReportRepository,
)
from simulator.versions.v2_postgres_react_ops.backend.operations_report_scheduler import (  # noqa: E402
    OperationsReportScheduler,
)
from simulator.versions.v2_postgres_react_ops.backend.operations_report_writer import (  # noqa: E402
    OperationsReportDraft,
)
from simulator.versions.v2_postgres_react_ops.backend.schemas import JsonValue  # noqa: E402


YEAR_OFFSET: Final = int(uuid4().hex[:4], 16) % 1000


@dataclass(frozen=True, slots=True)
class PeriodProbe:
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True, slots=True)
class AlertSeed:
    alert_id: str
    card_id: str
    status: str
    freshness_status: str
    created_at: datetime


@dataclass(slots=True)
class SlowCountingWriter:
    target: PeriodProbe
    started_count: int = 0
    first_started: anyio.Event = field(default_factory=anyio.Event)
    release: anyio.Event = field(default_factory=anyio.Event)

    async def write_report(self, draft: OperationsReportDraft) -> dict[str, JsonValue]:
        if draft.period_start != self.target.start_utc or draft.period_end != self.target.end_utc:
            return draft.content
        self.started_count += 1
        self.first_started.set()
        await self.release.wait()
        return draft.content


@pytest.mark.anyio
async def test_concurrent_scheduler_run_writes_same_due_period_once() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    year = 7100 + YEAR_OFFSET
    now = datetime(year, 6, 9, 23, 0, tzinfo=UTC)
    probe = _night_shift_probe(year, 6, 10)
    writer = SlowCountingWriter(target=probe)
    scheduler = OperationsReportScheduler(repo, writer=writer, lookback_hours=12)
    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(_run_due_reports, scheduler, now)
            await writer.first_started.wait()
            task_group.start_soon(_run_due_reports, scheduler, now)
            await anyio.sleep(0.2)
            writer.release.set()

        report = await repo.get_period_by_range("shift", probe.start_utc, probe.end_utc)

        assert writer.started_count == 1
        assert report is not None
        assert len(report.versions) == 1
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_alert_snapshot_counts_only_alerts_created_inside_period() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    scheduler = OperationsReportScheduler(repo, lookback_hours=12)
    year = 7200 + YEAR_OFFSET
    probe = _night_shift_probe(year, 7, 11)
    try:
        async with engine.begin() as connection:
            await _insert_alert(
                connection,
                AlertSeed(
                    alert_id=str(uuid4()),
                    card_id=str(uuid4()),
                    status="resolved",
                    freshness_status="stale",
                    created_at=probe.start_utc - timedelta(hours=1),
                ),
            )
            await _insert_alert(
                connection,
                AlertSeed(
                    alert_id=str(uuid4()),
                    card_id=str(uuid4()),
                    status="open",
                    freshness_status="fresh",
                    created_at=probe.start_utc + timedelta(hours=1),
                ),
            )

        await scheduler.run_due_reports(now=datetime(year, 7, 10, 23, 0, tzinfo=UTC))
        report = await repo.get_period_by_range("shift", probe.start_utc, probe.end_utc)

        assert report is not None
        counts = report.versions[0].content["source_counts"]
        assert counts == {
            "open_incidents": 1,
            "resolved_incidents": 0,
            "data_quality_issues": 0,
            "approved_outcome_unknown_work_orders": 0,
            "agent_report_artifacts": 0,
        }
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_daily_scheduler_catches_up_multiple_missing_days() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    scheduler = OperationsReportScheduler(repo, lookback_hours=96)
    year = 7300 + YEAR_OFFSET
    try:
        summary = await scheduler.run_due_reports(now=datetime(year, 8, 6, 23, 0, tzinfo=UTC))

        first = await repo.get_period_by_range("daily", *_daily_window(year, 8, 3))
        second = await repo.get_period_by_range("daily", *_daily_window(year, 8, 4))
        third = await repo.get_period_by_range("daily", *_daily_window(year, 8, 5))

        assert summary.generated_count >= 3
        assert first is not None
        assert second is not None
        assert third is not None
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_scheduler_marks_old_failed_report_periods_overdue() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    scheduler = OperationsReportScheduler(repo, lookback_hours=12)
    year = 7400 + YEAR_OFFSET
    start, end = _daily_window(year, 9, 3)
    operation_key = f"operations-report:daily:{start.isoformat()}:{end.isoformat()}"
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO operations_report_periods "
                    "(report_type, period_start, period_end, timezone, status, "
                    "operation_key, error, updated_at) "
                    "VALUES ('daily', :start, :end, 'Asia/Seoul', 'failed', "
                    ":operation_key, 'writer unavailable', :updated_at)"
                ),
                {
                    "start": start,
                    "end": end,
                    "operation_key": operation_key,
                    "updated_at": datetime(year, 9, 5, 0, 0, tzinfo=UTC),
                },
            )

        await scheduler.run_due_reports(now=datetime(year, 9, 6, 23, 0, tzinfo=UTC))
        period = await repo.get_period_by_range("daily", start, end)

        assert period is not None
        assert period.status == "overdue"
    finally:
        await engine.dispose()


async def _run_due_reports(
    scheduler: OperationsReportScheduler,
    now: datetime,
) -> None:
    await scheduler.run_due_reports(now=now)


async def _insert_alert(connection: AsyncConnection, seed: AlertSeed) -> None:
    decision_id = str(uuid4())
    window_id = str(uuid4())
    substation_id = seed.created_at.year
    substation_uid = await connection.scalar(
        text(
            "INSERT INTO substations (substation_uid, manufacturer_id, substation_id) "
            "VALUES (:substation_uid, 'pytest', :substation_id) "
            "ON CONFLICT (manufacturer_id, substation_id) DO UPDATE SET "
            "configuration_type = public.substations.configuration_type "
            "RETURNING substation_uid"
        ),
        {"substation_uid": str(uuid4()), "substation_id": substation_id},
    )
    assert substation_uid is not None
    await connection.execute(
        text(
            "INSERT INTO windows "
            "(window_id, substation_uid, manufacturer_id, substation_id, "
            "window_start, window_end) "
            "VALUES (:window_id, :substation_uid, 'pytest', :substation_id, "
            ":created_at, :created_at)"
        ),
        {
            "window_id": window_id,
            "substation_uid": substation_uid,
            "substation_id": substation_id,
            "created_at": seed.created_at,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO priority_decisions (priority_decision_id, window_id, "
            "priority_score, priority_level, priority_source, policy_version, decision_basis) "
            "VALUES (:decision_id, :window_id, 0.8, 'high', 'pytest', 'pytest', 'pytest')"
        ),
        {"decision_id": decision_id, "window_id": window_id},
    )
    await connection.execute(
        text(
            "INSERT INTO priority_cards (card_id, priority_decision_id, review_required) "
            "VALUES (:card_id, :decision_id, true)"
        ),
        {"card_id": seed.card_id, "decision_id": decision_id},
    )
    await connection.execute(
        text(
            "INSERT INTO ops_alert_queue "
            "(alert_id, card_id, substation_uid, manufacturer_id, substation_id, "
            "priority_level, freshness_status, status, enqueue_reason, created_at) "
            "VALUES (:alert_id, :card_id, :substation_uid, 'pytest', :substation_id, "
            "'high', :freshness_status, :status, 'operations report regression', "
            ":created_at)"
        ),
        {
            "alert_id": seed.alert_id,
            "card_id": seed.card_id,
            "substation_uid": substation_uid,
            "substation_id": substation_id,
            "freshness_status": seed.freshness_status,
            "status": seed.status,
            "created_at": seed.created_at,
        },
    )


def _night_shift_probe(year: int, month: int, day: int) -> PeriodProbe:
    return PeriodProbe(
        start_utc=datetime(year, month, day - 1, 11, 0, tzinfo=UTC),
        end_utc=datetime(year, month, day - 1, 23, 0, tzinfo=UTC),
    )


def _daily_window(year: int, month: int, day: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, day - 1, 15, 0, tzinfo=UTC)
    return start, start + timedelta(days=1)
