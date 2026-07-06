from __future__ import annotations

from pydantic import BaseModel, ConfigDict

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class AppModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class WindowContext(AppModel):
    window_id: str
    manufacturer_id: str
    substation_id: int | str
    configuration_type: str | None
    window_start: str
    window_end: str


class FeatureContext(AppModel):
    feature_name: str
    source_sensor: str
    meaning: str
    feature_value: float | str | None


class RawContext(AppModel):
    window: WindowContext
    features: list[FeatureContext]


class CardContext(AppModel):
    card_id: str
    operational_label: str | None
    primary_state: str | None
    review_required: bool
    trust_level: str | None


class PriorityContextBlock(AppModel):
    priority_decision_id: str
    priority_score: float | None
    priority_level: str | None
    priority_source: str | None
    m1_priority_agreement: str | None


class ModelSignals(AppModel):
    current_best_priority_score: float | None
    current_best_priority_level: str | None
    m1_specialist_priority_score: float | None
    m1_specialist_priority_level: str | None


class ExplanationContext(AppModel):
    why_reason: str | None
    recommended_action: str | None


class PriorityContext(AppModel):
    card: CardContext
    priority: PriorityContextBlock
    model_signals: ModelSignals
    explanation: ExplanationContext


class OpsAgentInput(AppModel):
    raw_context: RawContext
    priority_context: PriorityContext


class OpsAgentOutput(AppModel):
    summary: str
    action_plan: str
    caution: str


class HealthResponse(AppModel):
    database: str
    openai: str


class StatusResponse(AppModel):
    status: str


class SimulationResponse(AppModel):
    input_source: str
    saved_to_db: bool
    ops_input: OpsAgentInput
    ops_output: OpsAgentOutput
