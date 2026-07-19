from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from operations_policy_api_models import (
    OperationsPolicyResponse,
    OperationsPolicyUpdateRequest,
    ShiftScheduleResponse,
)


@dataclass(frozen=True, slots=True)
class StaleOperationsPolicyVersionError(RuntimeError):
    expected_version: int
    current_version: int

    def __str__(self) -> str:
        return (
            "operations policy version conflict: "
            f"expected={self.expected_version}, current={self.current_version}"
        )


class OperationsPolicyRepository(Protocol):
    async def get_policy(self) -> OperationsPolicyResponse: ...

    async def update_policy(
        self,
        request: OperationsPolicyUpdateRequest,
        *,
        updated_by: str,
    ) -> OperationsPolicyResponse: ...


@dataclass(frozen=True, slots=True)
class PostgresOperationsPolicyRepository:
    engine: AsyncEngine

    async def get_policy(self) -> OperationsPolicyResponse:
        async with self.engine.connect() as connection:
            return await _get_policy(connection)

    async def update_policy(
        self,
        request: OperationsPolicyUpdateRequest,
        *,
        updated_by: str,
    ) -> OperationsPolicyResponse:
        async with self.engine.begin() as connection:
            updated = await connection.execute(
                text(
                    "UPDATE operations_policy SET version = version + 1, timezone = :timezone, "
                    "freshness_threshold_minutes = :freshness_threshold_minutes, "
                    "anomaly_confirmations = :anomaly_confirmations, "
                    "recovery_confirmations = :recovery_confirmations, updated_at = now(), "
                    "updated_by = :updated_by WHERE policy_key = 'default' "
                    "AND version = :expected_version RETURNING version"
                ),
                {
                    "timezone": request.timezone,
                    "freshness_threshold_minutes": request.freshness_threshold_minutes,
                    "anomaly_confirmations": request.anomaly_confirmations,
                    "recovery_confirmations": request.recovery_confirmations,
                    "updated_by": updated_by,
                    "expected_version": request.expected_version,
                },
            )
            if updated.scalar_one_or_none() is None:
                current_version = await connection.scalar(
                    text(
                        "SELECT version FROM operations_policy WHERE policy_key = 'default'"
                    )
                )
                raise StaleOperationsPolicyVersionError(
                    expected_version=request.expected_version,
                    current_version=0 if current_version is None else int(current_version),
                )
            await connection.execute(
                text("DELETE FROM operations_shift_schedule WHERE policy_key = 'default'")
            )
            for position, shift in enumerate(request.shifts, start=1):
                await connection.execute(
                    text(
                        "INSERT INTO operations_shift_schedule "
                        "(policy_key, shift_id, label, start_time, end_time, position) "
                        "VALUES ('default', :shift_id, :label, "
                        "CAST(CAST(:start_time AS text) AS time), "
                        "CAST(CAST(:end_time AS text) AS time), :position)"
                    ),
                    {
                        "shift_id": shift.shift_id,
                        "label": shift.label,
                        "start_time": shift.start_time,
                        "end_time": shift.end_time,
                        "position": position,
                    },
                )
            return await _get_policy(connection)


async def verify_operations_policy(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await _get_policy(connection)


async def _get_policy(connection: AsyncConnection) -> OperationsPolicyResponse:
    policy_result = await connection.execute(
        text(
            "SELECT version, timezone, freshness_threshold_minutes, anomaly_confirmations, "
            "recovery_confirmations, updated_at, updated_by FROM operations_policy "
            "WHERE policy_key = 'default'"
        )
    )
    policy = policy_result.mappings().one()
    shift_result = await connection.execute(
        text(
            "SELECT shift_id, label, to_char(start_time, 'HH24:MI') AS start_time, "
            "to_char(end_time, 'HH24:MI') AS end_time FROM operations_shift_schedule "
            "WHERE policy_key = 'default' ORDER BY position"
        )
    )
    shifts = tuple(
        ShiftScheduleResponse.model_validate(dict(row))
        for row in shift_result.mappings().all()
    )
    if len(shifts) != 2:
        raise RuntimeError("canonical operations policy must contain exactly two shifts")
    return _policy_response(policy, shifts)


def _policy_response(
    policy: RowMapping,
    shifts: tuple[ShiftScheduleResponse, ShiftScheduleResponse],
) -> OperationsPolicyResponse:
    return OperationsPolicyResponse(
        version=policy["version"],
        timezone=policy["timezone"],
        freshness_threshold_minutes=policy["freshness_threshold_minutes"],
        anomaly_confirmations=policy["anomaly_confirmations"],
        recovery_confirmations=policy["recovery_confirmations"],
        shifts=shifts,
        updated_at=policy["updated_at"],
        updated_by=policy["updated_by"],
    )
