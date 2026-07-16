from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.errors import AgentInputContractError
from heatgrid_ops.agent.models import (
    JsonObject,
    ModelVerificationResult,
    OpsAgentOutput,
    SimulationResponse,
    TokenUsage,
)
from heatgrid_ops.agent.run_models import AgentLoopSummary


type SimulateCard = Callable[[str], Awaitable[SimulationResponse]]

_REQUIRED_AGENT_INPUT_KEYS = (
    "card_id",
    "sections",
    "priority_context",
    "raw_context",
)


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    run_id: str
    alert_id: str
    card_id: str


class AgentInputSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_input: JsonObject


def validate_agent_input(
    snapshot: AgentInputSnapshot,
    request: AgentRunRequest,
) -> JsonObject:
    source_input = snapshot.source_input
    missing = [name for name in _REQUIRED_AGENT_INPUT_KEYS if name not in source_input]
    if missing:
        raise AgentInputContractError(
            detail="agent input missing required keys: " + ", ".join(missing)
        )
    source_card_id = source_input["card_id"]
    if not isinstance(source_card_id, str) or not source_card_id:
        raise AgentInputContractError(
            detail="agent input card_id must be a non-empty string"
        )
    for name in _REQUIRED_AGENT_INPUT_KEYS[1:]:
        if not isinstance(source_input[name], dict):
            raise AgentInputContractError(
                detail=f"agent input {name} must be a JSON object"
            )
    if source_card_id != request.card_id:
        raise AgentInputContractError(
            detail="agent input card_id does not match requested card_id"
        )
    return source_input


class AgentRunCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulation: SimulationResponse
    loop_summary: AgentLoopSummary
    review_task_id: str | None = None


class AgentLoopIterationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    iteration: int
    phase: str
    decision: str
    confidence: float
    evidence_score: float
    missing_evidence: list[str]
    model_verification: ModelVerificationResult | None = None


class AgentReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_type: str
    risk_level: Literal["low", "medium", "high", "critical"]
    title: str
    payload: JsonObject
    run_id: str | None = None
    candidate_id: str | None = None
    status: str = "pending"
    reviewed_by: str | None = None


class AgentOutputContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    output: OpsAgentOutput
    usage: TokenUsage


ExecutionProfile: TypeAlias = Literal[
    "parent_evidence_agent",
    "report_snapshot_only",
    "child_targeted_recovery",
    "report_revision_only",
    "diagnostic_worker",
]


class ToolPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    allowed_tools: tuple[str, ...]
    max_total_tool_calls: int = Field(ge=0)
    max_calls_per_tool: dict[str, int] = Field(default_factory=dict)
    max_model_turns: int = Field(ge=1)
    stop_on_duplicate_args: bool = True
    deny_unlisted_tool: bool = True
    trace_required: bool = True


class ModelCallBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_input_chars: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    max_total_tokens: int = Field(ge=1)
    max_duration_ms: int = Field(ge=1)


class ReportDraftSnapshotBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["report_draft_bundle.v1"] = "report_draft_bundle.v1"
    run_id: str
    root_run_id: str
    parent_run_id: str | None = None
    target_stage: str | None = None
    source_input_hash: str
    bundle_hash: str
    stages: JsonObject


class ChatModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    card_id: str
    stage_name: str
    stage_attempt: int = Field(ge=1)
    execution_profile: ExecutionProfile
    source_input: JsonObject
    evidence_context: JsonObject
    snapshot_bundle: ReportDraftSnapshotBundle | None = None
    snapshot_bundle_hash: str | None = None
    tool_policy: ToolPolicy
    model_budget: ModelCallBudget
    model_verification: ModelVerificationResult | None = None
    evidence_assessment: EvidenceAssessment | None = None
    revision_feedback: list[str] = Field(default_factory=list)


class EvidenceAssessmentRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_input: JsonObject
    evidence_context: JsonObject
    model_verification: ModelVerificationResult | None = None
    iteration: int
    max_iterations: int
    deterministic: EvidenceAssessment


class ReportWriteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    card_id: str
    source_input: JsonObject
    evidence_context: JsonObject
    ops_output: OpsAgentOutput
    source_output_hash: str | None = None
