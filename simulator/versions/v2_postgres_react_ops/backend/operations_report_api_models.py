from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from schemas import JsonValue


ReportType = Literal["shift", "daily"]
ReportStatus = Literal["pending", "generating", "official", "failed", "overdue"]


class FrozenApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CurrentShiftMemoRequest(FrozenApiModel):
    memo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


class CurrentShiftMemoResponse(FrozenApiModel):
    period_start: datetime
    period_end: datetime
    timezone: Literal["Asia/Seoul"]
    memo: str
    updated_by: str | None = None
    updated_at: datetime | None = None


class OperationsReportVersionResponse(FrozenApiModel):
    report_version_id: str
    version: int = Field(ge=1)
    source_report_version_id: str | None = None
    official: bool
    content: dict[str, JsonValue]
    content_hash: str
    data_quality_caveats: tuple[str, ...]
    generated_by: str
    generated_at: datetime
    correction_reason: str | None = None


class OperationsReportPeriodResponse(FrozenApiModel):
    report_period_id: str
    report_type: ReportType
    period_start: datetime
    period_end: datetime
    timezone: Literal["Asia/Seoul"]
    status: ReportStatus
    operation_key: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    versions: tuple[OperationsReportVersionResponse, ...] = ()


class OperationsReportPage(FrozenApiModel):
    items: tuple[OperationsReportPeriodResponse, ...]


class OperationsReportCorrectionRequest(FrozenApiModel):
    expected_latest_version: int = Field(ge=1)
    content: dict[str, JsonValue]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class OperationsReportRunSummary(FrozenApiModel):
    checked_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
