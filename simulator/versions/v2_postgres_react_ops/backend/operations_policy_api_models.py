from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


Capability = Literal["admin"]


@dataclass(frozen=True, slots=True)
class InvalidShiftScheduleError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    display_name: str
    capabilities: tuple[Capability, ...]
    auth_mode: Literal["fixed"]


class ShiftScheduleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    shift_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    label: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ]
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or any(not part.isdigit() for part in parts):
            raise InvalidShiftScheduleError("shift times must use HH:MM")
        hour, minute = (int(part) for part in parts)
        if hour > 23 or minute > 59:
            raise InvalidShiftScheduleError("shift times must use a valid 24-hour time")
        return f"{hour:02d}:{minute:02d}"


class OperationsPolicyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = Field(ge=1)
    timezone: Literal["Asia/Seoul"]
    freshness_threshold_minutes: int = Field(ge=1, le=1440)
    anomaly_confirmations: int = Field(ge=1, le=100)
    recovery_confirmations: int = Field(ge=1, le=100)
    shifts: tuple[ShiftScheduleResponse, ShiftScheduleResponse]
    updated_at: datetime
    updated_by: str


class OperationsPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(ge=1)
    timezone: Literal["Asia/Seoul"]
    freshness_threshold_minutes: int = Field(ge=1, le=1440)
    anomaly_confirmations: int = Field(ge=1, le=100)
    recovery_confirmations: int = Field(ge=1, le=100)
    shifts: tuple[ShiftScheduleResponse, ShiftScheduleResponse]

    @model_validator(mode="after")
    def validate_shift_coverage(self) -> Self:
        first, second = self.shifts
        if first.shift_id == second.shift_id:
            raise InvalidShiftScheduleError("shift identifiers must be unique")
        if first.start_time == first.end_time or second.start_time == second.end_time:
            raise InvalidShiftScheduleError("each shift must have a positive duration")
        if first.end_time != second.start_time or second.end_time != first.start_time:
            raise InvalidShiftScheduleError(
                "two shifts must cover a full day without gaps or overlaps"
            )
        return self
