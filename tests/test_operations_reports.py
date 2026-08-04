from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine


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

from simulator.versions.v2_postgres_react_ops.backend.schemas import JsonValue  # noqa: E402
from simulator.versions.v2_postgres_react_ops.backend.operations_report_repository import (  # noqa: E402
    PostgresOperationsReportRepository,
)
from simulator.versions.v2_postgres_react_ops.backend.operations_report_routes import (  # noqa: E402
    make_operations_report_router,
)
from simulator.versions.v2_postgres_react_ops.backend.operations_report_scheduler import (  # noqa: E402
    OperationsReportScheduler,
)
from simulator.versions.v2_postgres_react_ops.backend.operations_report_writer import (  # noqa: E402
    OperationsReportDraft,
)


YEAR_OFFSET: Final = int(uuid4().hex[:4], 16) % 1000


@dataclass(frozen=True, slots=True)
class PeriodProbe:
    start_utc: datetime
    end_utc: datetime


class FailingWriter:
    async def write_report(self, draft: OperationsReportDraft) -> dict[str, JsonValue]:
        raise RuntimeError("writer unavailable")


@pytest.mark.anyio
async def test_scheduler_finalizes_shift_only_at_kst_boundary_and_is_idempotent() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    scheduler = OperationsReportScheduler(repo)
    year = 3000 + YEAR_OFFSET
    probe = _night_shift_probe(year, 1, 3)
    try:
        await repo.ensure_runtime_tables()

        await scheduler.run_due_reports(now=datetime(year, 1, 2, 22, 59, tzinfo=UTC))
        missing = await repo.get_period_by_range("shift", probe.start_utc, probe.end_utc)
        assert missing is None

        first = await scheduler.run_due_reports(now=datetime(year, 1, 2, 23, 0, tzinfo=UTC))
        second = await scheduler.run_due_reports(now=datetime(year, 1, 2, 23, 0, tzinfo=UTC))
        report = await repo.get_period_by_range("shift", probe.start_utc, probe.end_utc)

        assert first.generated_count >= 1
        assert second.generated_count == 0
        assert report is not None
        assert report.status == "official"
        assert len(report.versions) == 1
        assert report.versions[0].content["handover_memo"] == "no memo recorded"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_scheduler_finalizes_daily_report_after_following_0800_kst() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    scheduler = OperationsReportScheduler(repo)
    year = 4000 + YEAR_OFFSET
    daily = _daily_probe(year, 2, 4)
    try:
        await repo.ensure_runtime_tables()

        await scheduler.run_due_reports(now=datetime(year, 2, 4, 22, 59, tzinfo=UTC))
        missing = await repo.get_period_by_range("daily", daily.start_utc, daily.end_utc)
        assert missing is None

        await scheduler.run_due_reports(now=datetime(year, 2, 4, 23, 0, tzinfo=UTC))
        report = await repo.get_period_by_range("daily", daily.start_utc, daily.end_utc)

        assert report is not None
        assert report.status == "official"
        assert len(report.versions) == 1
        assert report.versions[0].content["report_type"] == "daily"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_failed_generation_is_visible_and_retried_idempotently() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    failing_scheduler = OperationsReportScheduler(repo, writer=FailingWriter())
    scheduler = OperationsReportScheduler(repo)
    year = 5000 + YEAR_OFFSET
    probe = _night_shift_probe(year, 3, 5)
    try:
        await repo.ensure_runtime_tables()

        failed = await failing_scheduler.run_due_reports(
            now=datetime(year, 3, 4, 23, 0, tzinfo=UTC)
        )
        failed_report = await repo.get_period_by_range(
            "shift", probe.start_utc, probe.end_utc
        )
        retried = await scheduler.run_due_reports(now=datetime(year, 3, 4, 23, 0, tzinfo=UTC))
        report = await repo.get_period_by_range("shift", probe.start_utc, probe.end_utc)

        assert failed.failed_count >= 1
        assert failed_report is not None
        assert failed_report.status == "failed"
        assert retried.generated_count >= 1
        assert report is not None
        assert report.status == "official"
        assert len(report.versions) == 1
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_current_shift_memo_and_reasoned_correction_are_append_only() -> None:
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    scheduler = OperationsReportScheduler(repo)
    year = 6000 + YEAR_OFFSET
    probe = _day_shift_probe(year, 4, 6)
    try:
        await repo.ensure_runtime_tables()
        await repo.save_current_shift_memo(
            probe.start_utc,
            probe.end_utc,
            memo="pump vibration follow-up",
            updated_by="operator",
        )

        await scheduler.run_due_reports(now=datetime(year, 4, 6, 11, 0, tzinfo=UTC))
        report = await repo.get_period_by_range("shift", probe.start_utc, probe.end_utc)
        assert report is not None
        assert report.versions[0].content["handover_memo"] == "pump vibration follow-up"

        corrected = await repo.create_correction(
            report.report_period_id,
            expected_latest_version=1,
            content={
                **report.versions[0].content,
                "operator_correction": "add pump inspection assignee",
            },
            reason="handover omission repair",
            created_by="operator",
        )
        reread = await repo.get_period(report.report_period_id)

        assert corrected.version == 2
        assert reread is not None
        assert [version.version for version in reread.versions] == [1, 2]
        assert reread.versions[0].content["handover_memo"] == "pump vibration follow-up"
        assert reread.versions[1].correction_reason == "handover omission repair"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_operations_report_routes_expose_memo_run_due_and_correction() -> None:
    fixed_now = datetime(7000 + YEAR_OFFSET, 5, 8, 23, 0, tzinfo=UTC)
    engine = create_async_engine(DATABASE_URL)
    repo = PostgresOperationsReportRepository(engine)
    app = FastAPI()
    app.include_router(
        make_operations_report_router(
            repo,
            OperationsReportScheduler(repo),
            clock=lambda: fixed_now,
        )
    )
    try:
        await repo.ensure_runtime_tables()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            memo = await client.put(
                "/api/operations-reports/current-shift/memo",
                json={"memo": "night shift leak patrol clear"},
            )
            run = await client.post("/api/operations-reports/run-due")
            page = await client.get("/api/operations-reports", params={"report_type": "shift"})

            assert memo.status_code == 200
            assert run.status_code == 200
            assert page.status_code == 200
            item = page.json()["items"][0]
            conflict = await client.post(
                f"/api/operations-reports/{item['report_period_id']}/corrections",
                json={
                    "expected_latest_version": 999,
                    "content": {"summary": "stale"},
                    "reason": "stale version probe",
                },
            )

        assert conflict.status_code == 409
    finally:
        await engine.dispose()


def _night_shift_probe(year: int, month: int, day: int) -> PeriodProbe:
    return PeriodProbe(
        start_utc=datetime(year, month, day - 1, 11, 0, tzinfo=UTC),
        end_utc=datetime(year, month, day - 1, 23, 0, tzinfo=UTC),
    )


def _day_shift_probe(year: int, month: int, day: int) -> PeriodProbe:
    return PeriodProbe(
        start_utc=datetime(year, month, day - 1, 23, 0, tzinfo=UTC),
        end_utc=datetime(year, month, day, 11, 0, tzinfo=UTC),
    )


def _daily_probe(year: int, month: int, day: int) -> PeriodProbe:
    return PeriodProbe(
        start_utc=datetime(year, month, day - 1, 15, 0, tzinfo=UTC),
        end_utc=datetime(year, month, day, 15, 0, tzinfo=UTC),
    )
