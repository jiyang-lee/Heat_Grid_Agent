from __future__ import annotations

from typing import Any, Literal

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
    work_order_versions: list[dict[str, Any]] = Field(default_factory=list)
    report_versions: list[dict[str, Any]] = Field(default_factory=list)
    chat_script: dict[str, Any]


class FinalTestDemoPackagePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[FinalTestDemoPackageSummary] = Field(default_factory=list)


class FinalTestChatHistoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal['operator', 'assistant']
    content: str = Field(min_length=1, max_length=8_000)


class FinalTestChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str = Field(min_length=1, max_length=4_000)
    document_type: Literal['work_order', 'report']
    current_version: int = Field(ge=1, le=3)
    history: tuple[FinalTestChatHistoryItem, ...] = Field(default=(), max_length=20)


class FinalTestChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
