from __future__ import annotations

from importlib import import_module
import sys
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

models = import_module("final_test_demo_models")
routes = import_module("final_test_demo_routes")


def _package() -> object:
    return models.FinalTestDemoPackage(
        demo_id="final-test-fault-001",
        scenario_id="final_test",
        alert_id="scenario-alert-1",
        substation_id=1,
        facility_name="도램마을10단지호반베르디움아파트",
        fault_label="1번 변전소 복합 고장",
        normal_payload={"state": "normal", "sensors": [], "priority": {}},
        fault_payload={"state": "fault", "sensors": [], "priority": {}},
        work_order_document={"document_id": "final-test-fault-001-work-order"},
        report_document={"document_id": "final-test-fault-001-report"},
        chat_script={"guardrails": [{"category": "jailbreak"}]},
    )


class _Repository:
    def __init__(self) -> None:
        self.package = _package()
        self.requested_ids: list[str] = []

    async def list_packages(self) -> list[object]:
        return [
            models.FinalTestDemoPackageSummary(
                demo_id=self.package.demo_id,
                alert_id=self.package.alert_id,
                substation_id=self.package.substation_id,
                facility_name=self.package.facility_name,
                fault_label=self.package.fault_label,
            )
        ]

    async def get_package(self, demo_id: str) -> object | None:
        self.requested_ids.append(demo_id)
        return self.package if demo_id == self.package.demo_id else None


@pytest.mark.anyio
async def test_final_test_list_and_detail_use_one_demo_id() -> None:
    repository = _Repository()
    app = FastAPI()
    app.include_router(routes.make_final_test_demo_router(repository))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        list_response = await client.get("/api/final-test/packages")
        demo_id = list_response.json()["items"][0]["demo_id"]
        detail_response = await client.get(f"/api/final-test/packages/{demo_id}")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert repository.requested_ids == ["final-test-fault-001"]
    assert detail["demo_id"] == "final-test-fault-001"
    assert detail["work_order_document"]["document_id"].startswith(detail["demo_id"])
    assert detail["report_document"]["document_id"].startswith(detail["demo_id"])


@pytest.mark.anyio
async def test_final_test_detail_returns_404_for_unknown_id() -> None:
    app = FastAPI()
    app.include_router(routes.make_final_test_demo_router(_Repository()))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/final-test/packages/not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": "final_test demo package was not found"}
