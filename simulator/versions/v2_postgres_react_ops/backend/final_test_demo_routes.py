from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from final_test_demo_models import (
    FinalTestDemoPackage,
    FinalTestDemoPackagePage,
)
from final_test_demo_repository import FinalTestDemoRepository


def make_final_test_demo_router(repository: FinalTestDemoRepository) -> APIRouter:
    router = APIRouter(prefix="/api/final-test/packages", tags=["final-test-demo"])

    @router.get("", response_model=FinalTestDemoPackagePage)
    async def list_packages() -> FinalTestDemoPackagePage:
        return FinalTestDemoPackagePage(items=await repository.list_packages())

    @router.get("/{demo_id}", response_model=FinalTestDemoPackage)
    async def get_package(demo_id: str) -> FinalTestDemoPackage:
        package = await repository.get_package(demo_id)
        if package is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="final_test demo package was not found",
            )
        return package

    return router
