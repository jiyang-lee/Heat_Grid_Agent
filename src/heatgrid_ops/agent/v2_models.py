from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.models import JsonObject


StageName = Literal[
    "ml_validation",
    "weather_context",
    "rag_retrieval",
    "rag_interpretation",
    "fault_analysis",
    "higher_model_reassessment",
    "parent_disposition",
    "report_draft",
    "report_fidelity",
]

ReasonCategory = Literal[
    "ml_prediction_issue",
    "weather_context_issue",
    "rag_retrieval_issue",
    "rag_interpretation_issue",
    "fault_analysis_issue",
    "escalation_issue",
    "report_draft_issue",
    "insufficient_evidence",
    "operational_policy_issue",
]

STAGE_ORDER: Final[tuple[StageName, ...]] = (
    "ml_validation",
    "weather_context",
    "rag_retrieval",
    "rag_interpretation",
    "fault_analysis",
    "higher_model_reassessment",
    "parent_disposition",
    "report_draft",
    "report_fidelity",
)
STATE_SCHEMA_VERSION: Final = "agent_v2_state.v2"
SNAPSHOT_SCHEMA_VERSION: Final = "agent_stage_snapshot.v2"


class V2FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StageQualityEnvelope(V2FrozenModel):
    threshold: float | None = None
    reasons: tuple[str, ...] = ()
    retry_exhausted: bool = False


class StageControlEnvelope(V2FrozenModel):
    force_review: bool = False
    suggested_query: str | None = None
    broaden: bool = False


class StageSnapshotEnvelope(V2FrozenModel):
    schema_version: Literal["agent_stage_snapshot.v2"] = SNAPSHOT_SCHEMA_VERSION
    state_schema_version: str = STATE_SCHEMA_VERSION
    stage_name: StageName
    data: JsonObject = Field(default_factory=dict)
    quality: StageQualityEnvelope = Field(default_factory=StageQualityEnvelope)
    control: StageControlEnvelope = Field(default_factory=StageControlEnvelope)
