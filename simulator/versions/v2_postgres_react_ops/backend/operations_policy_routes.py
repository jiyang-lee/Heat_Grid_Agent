from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, status

from operations_policy_api_models import (
    CurrentUserResponse,
    OperationsPolicyResponse,
    OperationsPolicyUpdateRequest,
)
from operations_policy_repository import (
    OperationsPolicyRepository,
    StaleOperationsPolicyVersionError,
)


FIXED_OPERATOR: Final = CurrentUserResponse(
    user_id="operator",
    display_name="운영자",
    capabilities=("admin",),
    auth_mode="fixed",
)


async def current_user() -> CurrentUserResponse:
    return FIXED_OPERATOR


async def require_admin(
    user: Annotated[CurrentUserResponse, Depends(current_user)],
) -> CurrentUserResponse:
    if "admin" not in user.capabilities:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin capability required",
        )
    return user


def make_operations_policy_router(
    repository: OperationsPolicyRepository,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["operations-policy"])

    @router.get("/me", response_model=CurrentUserResponse)
    async def me(
        user: Annotated[CurrentUserResponse, Depends(current_user)],
    ) -> CurrentUserResponse:
        return user

    @router.get("/operations-policy", response_model=OperationsPolicyResponse)
    async def get_operations_policy() -> OperationsPolicyResponse:
        return await repository.get_policy()

    @router.put("/operations-policy", response_model=OperationsPolicyResponse)
    async def update_operations_policy(
        request: OperationsPolicyUpdateRequest,
        admin: Annotated[CurrentUserResponse, Depends(require_admin)],
    ) -> OperationsPolicyResponse:
        try:
            return await repository.update_policy(request, updated_by=admin.user_id)
        except StaleOperationsPolicyVersionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "operations_policy_version_conflict",
                    "expected_version": error.expected_version,
                    "current_version": error.current_version,
                },
            ) from error

    return router
