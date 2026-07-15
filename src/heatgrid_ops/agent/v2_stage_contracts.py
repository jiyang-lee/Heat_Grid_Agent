from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.v2_models import (
    ReasonCategory,
    StageName,
    StageSnapshotEnvelope,
)
from heatgrid_ops.agent.v2_state import AgentV2State


@dataclass(frozen=True, slots=True)
class StageSnapshotWrite:
    run_id: str
    stage_name: StageName
    attempt: int
    stage_input_hash: str
    output_hash: str
    envelope: StageSnapshotEnvelope
    execution_status: str
    quality_status: str | None
    score: float | None
    contract_version: str
    component_versions: JsonObject
    reused_from_snapshot_id: str | None = None


class StageSnapshotPort(Protocol):
    async def get_attempt(
        self,
        run_id: str,
        stage_name: StageName,
        attempt: int,
    ) -> StageSnapshotWrite | None: ...

    async def record(self, request: StageSnapshotWrite) -> StageSnapshotWrite: ...


@dataclass(frozen=True, slots=True)
class RagRetrievalQualityRequest:
    query: str
    evidence_ids: tuple[str, ...]
    result_count: int
    top_k: int
    broaden: bool


@dataclass(frozen=True, slots=True)
class RagQualityResult:
    quality_status: str
    score: float | None
    reasons: tuple[str, ...] = ()
    suggested_query: str | None = None


class RagQualityPort(Protocol):
    async def evaluate_retrieval(
        self,
        request: RagRetrievalQualityRequest,
    ) -> RagQualityResult: ...


class StageAdapter(Protocol):
    async def __call__(self, state: AgentV2State) -> StageSnapshotEnvelope: ...


@dataclass(frozen=True, slots=True)
class EscalationRequest:
    state: AgentV2State
    reasons: tuple[str, ...]


class EscalationPort(Protocol):
    async def reassess(self, request: EscalationRequest) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class ReportFidelityResult:
    deterministic_score: float
    judge_score: float | None
    reasons: tuple[str, ...] = ()


class ReportFidelityPort(Protocol):
    async def evaluate(self, report: JsonObject) -> ReportFidelityResult: ...


def stage_contract_version(stage_name: StageName) -> str:
    return f"{stage_name}.v2"


def reason_category_values() -> tuple[ReasonCategory, ...]:
    return (
        "ml_prediction_issue",
        "weather_context_issue",
        "rag_retrieval_issue",
        "rag_interpretation_issue",
        "fault_analysis_issue",
        "escalation_issue",
        "report_draft_issue",
        "insufficient_evidence",
        "operational_policy_issue",
    )
