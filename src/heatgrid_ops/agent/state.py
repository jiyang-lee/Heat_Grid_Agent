from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.assessment import EvidenceAssessment, OutputValidation
from heatgrid_ops.agent.diagnostics import DiagnosticSummary
from heatgrid_ops.agent.models import (
    JsonObject,
    JsonValue,
    ModelVerificationResult,
    OpsAgentOutput,
    TokenCall,
    TokenUsage,
)
from heatgrid_ops.agent.run_models import AgentRunResult
from heatgrid_ops.agent.review_models import AgentRunReviewCaptureSource


class FrozenStateModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RequestState(FrozenStateModel):
    run_id: str
    alert_id: str
    card_id: str
    source_input: JsonObject = Field(default_factory=dict)


class EvidenceState(FrozenStateModel):
    ops_evidence: JsonObject = Field(default_factory=dict)
    external_context: JsonObject = Field(default_factory=dict)
    model_verification: ModelVerificationResult | None = None
    model_attempts: int = 0
    active_model_artifact_uri: str | None = None
    diagnostic_summary: DiagnosticSummary | None = None
    diagnostic_calls: list[TokenCall] = Field(default_factory=list)


class LoopState(FrozenStateModel):
    assessment: EvidenceAssessment | None = None
    iteration: int = 1
    max_iterations: int = 4
    revision_count: int = 0
    revision_feedback: list[str] = Field(default_factory=list)
    force_review: bool = False
    model_review_task_id: str | None = None
    review_task_id: str | None = None
    diagnostic_attempted: bool = False


class OutputState(FrozenStateModel):
    value: OpsAgentOutput | None = None
    token_usage: TokenUsage | None = None
    mode: Literal["llm", "fallback"] | None = None
    validation: OutputValidation | None = None
    report_artifacts: list[JsonObject] = Field(default_factory=list)
    report_errors: list[str] = Field(default_factory=list)


class AuditState(FrozenStateModel):
    used_tools: list[str] = Field(default_factory=list)
    action_decisions: list[JsonObject] = Field(default_factory=list)


class ResultState(FrozenStateModel):
    value: AgentRunResult | None = None
    review_capture_source: AgentRunReviewCaptureSource | None = None
    error: str | None = None


class AgentState(FrozenStateModel):
    request: RequestState
    evidence: EvidenceState = Field(default_factory=EvidenceState)
    loop: LoopState = Field(default_factory=LoopState)
    output: OutputState = Field(default_factory=OutputState)
    audit: AuditState = Field(default_factory=AuditState)
    result: ResultState = Field(default_factory=ResultState)


class AgentStateUpdate(TypedDict, total=False):
    request: RequestState
    evidence: EvidenceState
    loop: LoopState
    output: OutputState
    audit: AuditState
    result: ResultState


class AgentGraphInput(TypedDict):
    request: RequestState
    evidence: EvidenceState
    loop: LoopState
    output: OutputState
    audit: AuditState
    result: ResultState


class AgentGraphOutput(TypedDict):
    result: ResultState


def json_objects(values: list[JsonObject]) -> list[JsonValue]:
    return [value for value in values]
