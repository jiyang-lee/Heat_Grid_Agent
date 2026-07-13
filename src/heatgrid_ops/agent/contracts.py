from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from heatgrid_ops.agent.errors import AgentInputContractError
from heatgrid_ops.agent.models import (
    JsonObject,
    ModelVerificationResult,
    OpsAgentOutput,
    SimulationResponse,
    TokenUsage,
)
from heatgrid_ops.agent.run_models import (
    AgentLoopSummary,
    EvidenceCandidateRequest,
)


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
    approved_action_task_id: str | None = None


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


class EvidenceCandidateStage(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate: EvidenceCandidateRequest
    status: Literal["pending", "auto_approved"]
    reviewed_by: str | None = None
    review_reason: str | None = None


class AgentOutputContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    output: OpsAgentOutput
    usage: TokenUsage
