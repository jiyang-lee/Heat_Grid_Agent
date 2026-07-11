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
    approved_action_task_id: str | None = None
