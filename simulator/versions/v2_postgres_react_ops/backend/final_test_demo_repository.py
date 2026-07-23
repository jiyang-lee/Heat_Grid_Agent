from __future__ import annotations

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from final_test_demo_models import (
    FinalTestDemoPackage,
    FinalTestDemoPackageSummary,
)


class FinalTestDemoRepository(Protocol):
    async def list_packages(self) -> list[FinalTestDemoPackageSummary]: ...

    async def get_package(self, demo_id: str) -> FinalTestDemoPackage | None: ...


class PostgresFinalTestDemoRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_packages(self) -> list[FinalTestDemoPackageSummary]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT demo_id, alert_id, substation_id, facility_name, fault_label "
                    "FROM public.final_test_demo_packages "
                    "WHERE scenario_id = 'final_test' ORDER BY substation_id"
                )
            )
        return [FinalTestDemoPackageSummary.model_validate(row) for row in rows.mappings()]

    async def get_package(self, demo_id: str) -> FinalTestDemoPackage | None:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT demo_id, scenario_id, alert_id, substation_id, facility_name, "
                    "fault_label, normal_payload, fault_payload, work_order_document, "
                    "report_document, work_order_versions, report_versions, chat_script "
                    "FROM public.final_test_demo_packages WHERE demo_id = :demo_id"
                ),
                {"demo_id": demo_id},
            )
            row = result.mappings().one_or_none()
        return FinalTestDemoPackage.model_validate(row) if row is not None else None
