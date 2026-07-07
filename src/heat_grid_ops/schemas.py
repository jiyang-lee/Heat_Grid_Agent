from __future__ import annotations

from typing import Literal, assert_never

from pydantic import BaseModel, ConfigDict, field_validator

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


class SensorValueContext(AppModel):
    rank: int
    feature_name: str
    source_sensor: str
    source_column: str
    feature_value: JsonScalar
    unit: str | None
    calculation: str
    meaning: str


class CurrentBestSensorValues(AppModel):
    model_id: str
    model_version: str | None
    source_artifact: str
    selection_rule: str
    top_n: int
    values: list[SensorValueContext]


class M1SpecialistFeatures(AppModel):
    model_id: str
    model_version: str | None
    source_artifact: str
    feature_count: int
    features: list[SensorValueContext]


class RawContext(AppModel):
    window: WindowContext
    current_best_sensor_values: CurrentBestSensorValues
    m1_specialist_features: M1SpecialistFeatures


class CardContext(AppModel):
    card_id: str
    operational_label: str | None
    primary_state: str | None
    trust_level: str | None


class PriorityCalculation(AppModel):
    current_best_weight: float | None
    m1_specialist_weight: float | None
    expression: str | None


class PriorityContextBlock(AppModel):
    priority_decision_id: str
    priority_score: float | None
    priority_level: str | None
    priority_source: str | None
    m1_priority_agreement: str | None
    calculation: PriorityCalculation


class ModelSignals(AppModel):
    current_best_priority_score: float | None
    current_best_priority_level: str | None
    m1_specialist_priority_score: float | None
    m1_specialist_priority_level: str | None
    m1_specialist_primary_state: str | None
    m1_specialist_fault_group: str | None


class ExplanationContext(AppModel):
    why_reason: str | None
    recommended_action: str | None
    review_required: bool
    review_reasons: list[str]


class PriorityContext(AppModel):
    card: CardContext
    priority: PriorityContextBlock
    model_signals: ModelSignals
    explanation: ExplanationContext


class OpsAgentInput(AppModel):
    raw_context: RawContext
    priority_context: PriorityContext


class InternalContext(AppModel):
    llm_role: str
    language: str
    audience: str
    task_type: str
    situation_summary: str
    operator_goal: str


class PriorityCalculationTrace(AppModel):
    expression: str | None
    current_best_weight: float | None
    current_best_priority_score: float | None
    m1_specialist_weight: float | None
    m1_specialist_priority_score: float | None


class ModelInterpretation(AppModel):
    current_best_priority_level: str | None
    m1_specialist_priority_level: str | None
    m1_specialist_primary_state: str | None
    m1_specialist_fault_group: str | None
    m1_priority_agreement: str | None


class HumanReviewSignal(AppModel):
    review_required: bool
    review_reasons: list[str]
    trust_level: str | None


class DecisionTrace(AppModel):
    priority_score: float | None
    priority_level: str | None
    priority_source: str | None
    priority_calculation: PriorityCalculationTrace
    model_interpretation: ModelInterpretation
    human_review_signal: HumanReviewSignal


class EventContext(AppModel):
    raw_context: RawContext
    priority_context: PriorityContext
    internal_context: InternalContext
    decision_trace: DecisionTrace


class PolicyContext(AppModel):
    must_do: list[str]
    must_not_do: list[str]


class ActionContext(AppModel):
    llm_instruction: str
    focus_points: list[str]
    recommended_action_seed: str | None


class OutputFieldContract(AppModel):
    type: str
    description: str


class OutputContractProperties(AppModel):
    summary: OutputFieldContract
    action_plan: OutputFieldContract
    caution: OutputFieldContract


class OutputContract(AppModel):
    type: str
    required: list[str]
    additionalProperties: bool
    properties: OutputContractProperties


class PriorityRuleContext(AppModel):
    policy_context: PolicyContext
    output_contract: OutputContract


class ControlContext(AppModel):
    policy_context: PolicyContext
    action_context: ActionContext
    output_contract: OutputContract


class EscalationContext(AppModel):
    review_required: bool
    review_reasons: list[str]
    priority_level: str | None
    operational_label: str | None
    primary_state: str | None
    trust_level: str | None
    suspected_fault_group: str | None


class AuditContext(AppModel):
    input_kind: str
    card_id: str
    priority_decision_id: str
    window_id: str
    expected_output_storage: str


class HandoffContext(AppModel):
    escalation_context: EscalationContext
    audit_context: AuditContext


class OpsAgentLlmInput(AppModel):
    input_version: Literal["ops-agent-input-v0.2"] = "ops-agent-input-v0.2"
    event_context: EventContext
    control_context: ControlContext
    handoff_context: HandoffContext


class OpsAgentOutput(AppModel):
    summary: str
    action_plan: str
    caution: str

    @field_validator("summary", "action_plan", "caution", mode="before")
    @classmethod
    def normalize_text_field(cls, value: JsonValue) -> str:
        match value:
            case str():
                return value
            case bool():
                return str(value)
            case int() | float():
                return str(value)
            case None:
                return ""
            case list():
                return "\n".join(str(item) for item in value)
            case dict():
                return str(value)
            case unreachable:
                assert_never(unreachable)


class HealthResponse(AppModel):
    database: str
    openai: str


class StatusResponse(AppModel):
    status: str


class SimulationResponse(AppModel):
    input_source: str
    saved_to_db: bool
    ops_input: OpsAgentLlmInput
    ops_output: OpsAgentOutput
