from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ExecutionStatus = Literal["passed", "failed", "unavailable", "skipped", "reused"]
QualityStatus = Literal[
    "passed",
    "partial",
    "retry",
    "insufficient",
    "unavailable",
    "skipped",
]


@dataclass(frozen=True, slots=True)
class StageQualityResult:
    execution_status: ExecutionStatus
    quality_status: QualityStatus | None
    score: float | None


def ml_quality_result(*, status: str, agreement: bool | None) -> StageQualityResult:
    if status == "unavailable":
        return StageQualityResult("unavailable", "unavailable", None)
    if status == "error":
        return StageQualityResult("failed", "insufficient", 0.0)
    if status == "verified":
        if agreement is True:
            return StageQualityResult("passed", "passed", 100.0)
        if agreement is False:
            return StageQualityResult("passed", "insufficient", 25.0)
        return StageQualityResult("passed", "partial", 50.0)
    if status == "partial":
        if agreement is True:
            return StageQualityResult("passed", "partial", 60.0)
        if agreement is False:
            return StageQualityResult("passed", "insufficient", 25.0)
        return StageQualityResult("passed", "partial", 40.0)
    return StageQualityResult("failed", "insufficient", 0.0)


def rag_quality_result(
    *,
    result_count: int,
    quality_enabled: bool,
) -> StageQualityResult:
    if not quality_enabled:
        return StageQualityResult("passed", "skipped", None)
    if result_count <= 0:
        return StageQualityResult("passed", "insufficient", 0.0)
    if result_count < 3:
        return StageQualityResult("passed", "partial", 70.0)
    return StageQualityResult("passed", "passed", 100.0)
