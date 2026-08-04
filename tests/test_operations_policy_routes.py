from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

from operations_policy_api_models import (  # noqa: E402
    CurrentUserResponse,
    OperationsPolicyResponse,
    OperationsPolicyUpdateRequest,
    ShiftScheduleResponse,
)
from operations_policy_repository import StaleOperationsPolicyVersionError  # noqa: E402
from operations_policy_routes import (  # noqa: E402
    current_user,
    make_operations_policy_router,
)


VALID_UPDATE: Final = {
    "expected_version": 1,
    "timezone": "Asia/Seoul",
    "freshness_threshold_minutes": 30,
    "anomaly_confirmations": 2,
    "recovery_confirmations": 3,
    "shifts": [
        {
            "shift_id": "day",
            "label": "주간",
            "start_time": "08:00",
            "end_time": "20:00",
        },
        {
            "shift_id": "night",
            "label": "야간",
            "start_time": "20:00",
            "end_time": "08:00",
        },
    ],
}


def _default_policy(version: int = 1) -> OperationsPolicyResponse:
    return OperationsPolicyResponse(
        version=version,
        timezone="Asia/Seoul",
        freshness_threshold_minutes=30,
        anomaly_confirmations=2,
        recovery_confirmations=3,
        shifts=(
            ShiftScheduleResponse(
                shift_id="day",
                label="주간",
                start_time="08:00",
                end_time="20:00",
            ),
            ShiftScheduleResponse(
                shift_id="night",
                label="야간",
                start_time="20:00",
                end_time="08:00",
            ),
        ),
        updated_at=datetime(2026, 7, 19, tzinfo=UTC),
        updated_by="operator",
    )


@dataclass(slots=True)
class FakeOperationsPolicyRepository:
    policy: OperationsPolicyResponse
    update_calls: int = 0

    async def get_policy(self) -> OperationsPolicyResponse:
        return self.policy

    async def update_policy(
        self,
        request: OperationsPolicyUpdateRequest,
        *,
        updated_by: str,
    ) -> OperationsPolicyResponse:
        self.update_calls += 1
        if request.expected_version != self.policy.version:
            raise StaleOperationsPolicyVersionError(
                expected_version=request.expected_version,
                current_version=self.policy.version,
            )
        self.policy = OperationsPolicyResponse(
            version=self.policy.version + 1,
            timezone=request.timezone,
            freshness_threshold_minutes=request.freshness_threshold_minutes,
            anomaly_confirmations=request.anomaly_confirmations,
            recovery_confirmations=request.recovery_confirmations,
            shifts=(
                ShiftScheduleResponse.model_validate(request.shifts[0].model_dump()),
                ShiftScheduleResponse.model_validate(request.shifts[1].model_dump()),
            ),
            updated_at=datetime(2026, 7, 19, 1, tzinfo=UTC),
            updated_by=updated_by,
        )
        return self.policy


def _client(
    repository: FakeOperationsPolicyRepository,
    *,
    user: CurrentUserResponse | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(make_operations_policy_router(repository))
    if user is not None:
        app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def test_existing_settings_keep_replay_disabled_by_default() -> None:
    # Given: the current backend settings contract.
    from settings import Settings

    # When: settings are created without replay environment overrides.
    settings = Settings()

    # Then: replay remains an explicit opt-in capability.
    assert settings.replay_enabled is False


def test_current_user_returns_fixed_operator_admin_identity() -> None:
    # Given: the operations API with its fixed development identity.
    client = _client(FakeOperationsPolicyRepository(_default_policy()))

    # When: the current-user seam is requested.
    response = client.get("/api/me")

    # Then: it identifies the operator and exposes the admin capability.
    assert response.status_code == 200
    assert response.json() == {
        "user_id": "operator",
        "display_name": "운영자",
        "capabilities": ["admin"],
        "auth_mode": "fixed",
    }


def test_get_operations_policy_returns_seeded_defaults() -> None:
    # Given: the canonical seeded operations policy.
    client = _client(FakeOperationsPolicyRepository(_default_policy()))

    # When: the policy is read.
    response = client.get("/api/operations-policy")

    # Then: KST, two shifts, freshness, and lifecycle defaults are returned.
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["timezone"] == "Asia/Seoul"
    assert body["freshness_threshold_minutes"] == 30
    assert body["anomaly_confirmations"] == 2
    assert body["recovery_confirmations"] == 3
    assert [(shift["start_time"], shift["end_time"]) for shift in body["shifts"]] == [
        ("08:00", "20:00"),
        ("20:00", "08:00"),
    ]


def test_admin_can_update_operations_policy_with_expected_version() -> None:
    # Given: version one of the canonical policy.
    repository = FakeOperationsPolicyRepository(_default_policy())
    client = _client(repository)

    # When: the fixed admin updates it with the current version.
    response = client.put("/api/operations-policy", json=VALID_UPDATE)

    # Then: the policy advances exactly one version.
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["shifts"][0]["label"] == "주간"
    assert repository.update_calls == 1


def test_stale_policy_update_returns_conflict() -> None:
    # Given: policy version two and a client still holding version one.
    repository = FakeOperationsPolicyRepository(_default_policy(version=2))
    client = _client(repository)

    # When: the stale client attempts an update.
    response = client.put("/api/operations-policy", json=VALID_UPDATE)

    # Then: the API exposes an optimistic concurrency conflict.
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "operations_policy_version_conflict",
        "expected_version": 1,
        "current_version": 2,
    }


def test_overlapping_shift_schedule_is_rejected() -> None:
    # Given: a two-shift schedule whose second shift starts before the first ends.
    repository = FakeOperationsPolicyRepository(_default_policy())
    client = _client(repository)
    malformed = {
        **VALID_UPDATE,
        "shifts": [
            {**VALID_UPDATE["shifts"][0]},
            {**VALID_UPDATE["shifts"][1], "start_time": "19:30"},
        ],
    }

    # When: the malformed boundary payload is submitted.
    response = client.put("/api/operations-policy", json=malformed)

    # Then: validation fails before the repository is mutated.
    assert response.status_code == 422
    assert repository.update_calls == 0


def test_whitespace_only_shift_label_is_rejected_before_mutation() -> None:
    # Given: a shift label containing no visible characters.
    repository = FakeOperationsPolicyRepository(_default_policy())
    client = _client(repository)
    malformed = {
        **VALID_UPDATE,
        "shifts": [
            {**VALID_UPDATE["shifts"][0], "label": "  \t  "},
            {**VALID_UPDATE["shifts"][1]},
        ],
    }

    # When: the boundary payload is submitted.
    response = client.put("/api/operations-policy", json=malformed)

    # Then: validation rejects it before canonical state is mutated.
    assert response.status_code == 422
    assert repository.update_calls == 0


def test_non_admin_cannot_mutate_operations_policy() -> None:
    # Given: a dependency-injected operator without the admin capability.
    repository = FakeOperationsPolicyRepository(_default_policy())
    client = _client(
        repository,
        user=CurrentUserResponse(
            user_id="viewer",
            display_name="조회자",
            capabilities=(),
            auth_mode="fixed",
        ),
    )

    # When: the non-admin attempts an Admin mutation.
    response = client.put("/api/operations-policy", json=VALID_UPDATE)

    # Then: the server rejects it without touching canonical state.
    assert response.status_code == 403
    assert response.json()["detail"] == "admin capability required"
    assert repository.update_calls == 0
