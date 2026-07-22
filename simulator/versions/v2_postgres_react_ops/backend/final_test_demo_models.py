from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FinalTestDemoPackageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    demo_id: str
    alert_id: str
    substation_id: int
    facility_name: str
    fault_label: str


class FinalTestDemoPackage(BaseModel):
    model_config = ConfigDict(frozen=True)

    demo_id: str
    scenario_id: str
    alert_id: str
    substation_id: int
    facility_name: str
    fault_label: str
    normal_payload: dict[str, Any]
    fault_payload: dict[str, Any]
    work_order_document: dict[str, Any]
    report_document: dict[str, Any]
    chat_script: dict[str, Any]


class FinalTestDemoPackagePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[FinalTestDemoPackageSummary] = Field(default_factory=list)
