from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from operations_report_api_models import ReportType
from schemas import JsonValue


@dataclass(frozen=True, slots=True)
class OperationsReportDraft:
    report_type: ReportType
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    content: dict[str, JsonValue]


class OperationsReportWriter(Protocol):
    async def write_report(self, draft: OperationsReportDraft) -> dict[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class DeterministicOperationsReportWriter:
    async def write_report(self, draft: OperationsReportDraft) -> dict[str, JsonValue]:
        return draft.content
