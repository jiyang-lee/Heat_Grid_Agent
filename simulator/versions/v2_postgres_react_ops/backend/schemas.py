from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, Any]
AlertStatus: TypeAlias = Literal["open", "acked", "resolved"]
AgentRunStatus: TypeAlias = Literal["queued", "running", "completed", "failed"]
PriorityEvaluationStatus: TypeAlias = Literal["running", "completed", "failed"]
FreshnessStatus: TypeAlias = Literal["fresh", "stale", "missing"]
ReviewStatus: TypeAlias = Literal["pending", "approved", "rejected", "corrected"]
ReviewTaskStatus: TypeAlias = Literal[
    "pending",
    "auto_approved",
    "approved",
    "rejected",
    "corrected",
    "cancelled",
]
ReviewTaskType: TypeAlias = Literal[
    "final_output",
    "model_disagreement",
    "evidence_candidate",
    "label_correction",
    "retrain_approval",
    "model_promotion",
    "external_search",
]
EvidenceCandidateStatus: TypeAlias = Literal[
    "pending",
    "auto_approved",
    "approved",
    "rejected",
    "ingest_failed",
]
AutomationMode: TypeAlias = Literal["human_only", "assisted", "guarded_auto"]
RetrainJobStatus: TypeAlias = Literal[
    "pending_approval",
    "approved",
    "running",
    "completed",
    "failed",
    "rejected",
    "cancelled",
]
ModelCandidateStatus: TypeAlias = Literal[
    "awaiting_validation",
    "awaiting_promotion",
    "promoted",
    "rejected",
]
OpsAgentEvidenceSource: TypeAlias = Literal[
    "postgres",
    "pgvector",
    "jsonl",
    "kma",
    "fallback",
    "manual",
]


class OpsAgentOutput(BaseModel):
    summary: str
    action_plan: str
    caution: str


class OpsAgentEvidenceItem(BaseModel):
    label: str
    content: str
    source: OpsAgentEvidenceSource


class OpsAgentActionItem(BaseModel):
    priority: int
    title: str
    detail: str


class OpsAgentReport(BaseModel):
    title: str
    format: Literal["markdown"] = "markdown"
    content: str


class OpsAgentResultV4(BaseModel):
    schema_version: Literal["ops_agent_result.v4"] = "ops_agent_result.v4"
    run_id: str
    card_id: str
    evaluation_run_id: str | None = None
    manufacturer_id: str | None = None
    substation_id: int | None = None
    headline: str
    situation: str
    evidence: list[OpsAgentEvidenceItem]
    actions: list[OpsAgentActionItem]
    cautions: list[str]
    report: OpsAgentReport


class TokenCall(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class CostEstimate(BaseModel):
    model: str
    input_usd_per_1m: float
    cached_input_usd_per_1m: float
    output_usd_per_1m: float
    input_cost_usd: float
    cached_input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_source: str


class TokenUsage(BaseModel):
    model_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    evidence_payload_chars: int = 0
    cost_estimate: CostEstimate | None = None
    calls: list[TokenCall] = Field(default_factory=list)


class SimulationResponse(BaseModel):
    card_id: str
    input_source: Literal["postgresql"]
    agent_mode: Literal["llm", "fallback"]
    ops_output: OpsAgentOutput
    token_usage: TokenUsage


class ApiMetadata(BaseModel):
    service: str
    health: str
    docs: str
    apis: list[str]


class AgentRunCreateRequest(BaseModel):
    alert_id: str
    force_new: bool = False
    requested_by: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str | None = Field(default=None, min_length=1, max_length=500)


class AgentReportCreateRequest(BaseModel):
    requested_by: str = Field(min_length=1, max_length=120)


class ModelVerificationResult(BaseModel):
    status: Literal["verified", "partial", "unavailable", "error"]
    attempt: int = 1
    feature_count: int = 0
    feature_coverage: float = 0.0
    risk_score: float | None = None
    stored_risk_score: float | None = None
    risk_score_delta: float | None = None
    anomaly_score: float | None = None
    anomaly_label: bool | None = None
    leadtime_bucket: str | None = None
    stored_leadtime_bucket: str | None = None
    priority_score: float | None = None
    stored_priority_score: float | None = None
    priority_score_delta: float | None = None
    priority_level: str | None = None
    m1_specialist_priority_score: float | None = None
    component_agreement: dict[str, bool] = Field(default_factory=dict)
    agreement: bool | None = None
    active_model_version: str | None = None
    evaluation_run_id: str | None = None
    manufacturer_id: str | None = None
    substation_id: int | None = None
    reasons: list[str] = Field(default_factory=list)


class AgentLoopSummary(BaseModel):
    iterations: int = 0
    max_iterations: int = 0
    decision: str = "finalize"
    confidence: float = 0.0
    evidence_score: float = 0.0
    missing_evidence: list[str] = Field(default_factory=list)
    external_candidate_ids: list[str] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    action_decisions: list[JsonObject] = Field(default_factory=list)
    model_verification: ModelVerificationResult | None = None
    review_required: bool = True
    review_task_id: str | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    status: AgentRunStatus
    input_source: Literal["alert"]
    alert_id: str
    card_id: str
    evaluation_run_id: str | None = None
    manufacturer_id: str | None = None
    substation_id: int | None = None
    parent_run_id: str | None = None
    trigger_type: str = "alert"
    requested_by: str | None = None
    trigger_reason: str | None = None
    approved_action_task_id: str | None = None
    agent_mode: Literal["llm", "fallback"] | None = None
    ops_output: OpsAgentOutput | None = None
    token_usage: TokenUsage | None = None
    loop_summary: AgentLoopSummary | None = None
    review_status: ReviewStatus = "pending"
    review_task_id: str | None = None
    error: str | None = None
    # additive: DB agent_runs.created_at (상세 헤더 시작 시간 표시용)
    created_at: datetime | None = None


class AgentRunArtifact(BaseModel):
    artifact_id: str
    run_id: str
    kind: str
    name: str
    uri: str
    # additive: DB agent_run_artifacts.created_at (보고서 생성 시간 표시용)
    created_at: datetime | None = None


class AgentRunEvent(BaseModel):
    event_id: int
    run_id: str
    event_type: str
    message: str
    payload: JsonObject | None = None


class AgentLoopIteration(BaseModel):
    iteration_id: int
    run_id: str
    iteration: int
    phase: str
    decision: str
    confidence: float
    evidence_score: float
    missing_evidence: list[str] = Field(default_factory=list)
    model_verification: ModelVerificationResult | None = None
    created_at: str


class EvidenceCandidateCreateRequest(BaseModel):
    run_id: str | None = None
    source_type: Literal["web", "manual", "internal"] = "manual"
    source_uri: str | None = None
    title: str
    content: str
    query: str | None = None
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: JsonObject = Field(default_factory=dict)
    requested_by: str = "agent"


class EvidenceCandidate(BaseModel):
    candidate_id: str
    run_id: str | None = None
    source_type: str
    source_uri: str | None = None
    title: str
    content: str
    query: str | None = None
    risk_level: str
    trust_score: float
    status: EvidenceCandidateStatus
    metadata: JsonObject = Field(default_factory=dict)
    requested_by: str
    reviewed_by: str | None = None
    review_reason: str | None = None
    rag_document_id: str | None = None
    rag_chunk_id: str | None = None
    created_at: str
    reviewed_at: str | None = None


class EvidenceCandidateReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str
    reason: str = ""
    trust_score: float | None = Field(default=None, ge=0.0, le=1.0)


class HumanReviewTask(BaseModel):
    task_id: str
    task_type: ReviewTaskType
    status: ReviewTaskStatus
    risk_level: Literal["low", "medium", "high", "critical"]
    title: str
    run_id: str | None = None
    candidate_id: str | None = None
    retrain_job_id: str | None = None
    model_candidate_id: str | None = None
    payload: JsonObject = Field(default_factory=dict)
    resolution: JsonObject = Field(default_factory=dict)
    assigned_to: str | None = None
    reviewed_by: str | None = None
    created_at: str
    reviewed_at: str | None = None


class ReviewTaskSubmitRequest(BaseModel):
    decision: Literal["approve", "reject", "correct"]
    reviewer: str
    reason: str = ""
    corrected_output: OpsAgentOutput | None = None
    corrected_label: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class TrainingFeedback(BaseModel):
    feedback_id: str
    task_id: str
    run_id: str | None = None
    card_id: str | None = None
    reviewer: str
    decision: str
    original_output: JsonObject = Field(default_factory=dict)
    corrected_output: JsonObject = Field(default_factory=dict)
    corrected_label: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
    created_at: str


class ReviewSubmitResponse(BaseModel):
    task: HumanReviewTask
    feedback: TrainingFeedback | None = None
    automatic_retrain_job_id: str | None = None
    automatic_retrain_status: RetrainJobStatus | None = None
    resumed_agent_run_id: str | None = None
    resumed_agent_run_status: AgentRunStatus | None = None


class AutomationPolicy(BaseModel):
    policy_id: Literal["default"] = "default"
    mode: AutomationMode = "human_only"
    auto_transition_enabled: bool = False
    minimum_review_count: int = 100
    minimum_approval_rate: float = 0.95
    minimum_confidence: float = 0.9
    minimum_source_trust: float = 0.85
    maximum_drift_score: float = 0.1
    final_review_required: bool = True
    reviewed_count: int = 0
    approval_rate: float = 0.0
    eligible_for_guarded_auto: bool = False
    updated_by: str = "system"
    updated_at: str


class AutomationPolicyUpdateRequest(BaseModel):
    mode: AutomationMode | None = None
    auto_transition_enabled: bool | None = None
    minimum_review_count: int | None = Field(default=None, ge=1)
    minimum_approval_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_source_trust: float | None = Field(default=None, ge=0.0, le=1.0)
    maximum_drift_score: float | None = Field(default=None, ge=0.0, le=1.0)
    updated_by: str


class RetrainJobCreateRequest(BaseModel):
    requested_by: str
    reason: str
    feedback_ids: list[str] = Field(default_factory=list)
    auto_start_when_approved: bool = False


class RetrainJobActionRequest(BaseModel):
    reviewer: str
    reason: str = ""


class RetrainJob(BaseModel):
    job_id: str
    status: RetrainJobStatus
    requested_by: str
    reason: str
    feedback_ids: list[str] = Field(default_factory=list)
    dataset_snapshot: JsonObject = Field(default_factory=dict)
    execution_metadata: JsonObject = Field(default_factory=dict)
    approved_by: str | None = None
    error: str | None = None
    model_candidate_id: str | None = None
    created_at: str
    approved_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ModelCandidate(BaseModel):
    candidate_id: str
    job_id: str
    version: str
    artifact_uri: str
    status: ModelCandidateStatus
    baseline_metrics: JsonObject = Field(default_factory=dict)
    candidate_metrics: JsonObject = Field(default_factory=dict)
    validation_summary: JsonObject = Field(default_factory=dict)
    promoted_by: str | None = None
    promotion_reason: str | None = None
    created_at: str
    promoted_at: str | None = None


class ModelPromotionRequest(BaseModel):
    reviewer: str
    reason: str
    decision: Literal["promote", "reject"] = "promote"


class ModelDeployment(BaseModel):
    deployment_id: str
    candidate_id: str
    version: str
    artifact_uri: str
    active: bool
    promoted_by: str
    created_at: str


class PriorityEvaluationCreateRequest(BaseModel):
    as_of_time: datetime | None = None
    stale_after_hours: int | None = Field(default=None, ge=1)


class PriorityEvaluationRun(BaseModel):
    evaluation_run_id: str
    as_of_time: str
    stale_after_seconds: int
    model_version: str
    status: PriorityEvaluationStatus
    is_active: bool
    target_count: int
    success_count: int
    stale_count: int
    missing_count: int
    ranked_count: int
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class PriorityEvaluationResult(BaseModel):
    evaluation_result_id: str
    evaluation_run_id: str
    manufacturer_id: str
    substation_id: int
    source_window_id: str | None = None
    source_window_start: str | None = None
    source_window_end: str | None = None
    source_card_id: str | None = None
    source_priority_decision_id: str | None = None
    priority_score: float | None = None
    priority_rank: int | None = None
    rank_included: bool
    priority_level: str | None = None
    risk_score: float | None = None
    anomaly_score: float | None = None
    anomaly_label: bool | None = None
    leadtime_bucket: str | None = None
    leadtime_urgency_score: float | None = None
    leadtime_hours: float | None = None
    freshness_status: FreshnessStatus
    data_age_seconds: float | None = None
    model_components: JsonObject = Field(default_factory=dict)
    created_at: str


class PriorityEvaluationSnapshot(BaseModel):
    evaluation: PriorityEvaluationRun
    results: list[PriorityEvaluationResult]


class PrioritySubstationSnapshot(BaseModel):
    evaluation: PriorityEvaluationRun
    result: PriorityEvaluationResult


class CardSummary(BaseModel):
    card_id: str
    manufacturer_id: str
    substation_id: str | int | None
    operational_label: str | None
    primary_state: str | None
    review_required: bool
    trust_level: str | None
    priority_level: str | None
    priority_score: float | None
    current_best_weight: float | None
    m1_specialist_weight: float | None
    current_best_priority_score: float | None
    m1_specialist_priority_score: float | None
    why_reason: str | None
    recommended_action: str | None
    stable_crossing_lead_hours: float | None
    window_start: str | None
    window_end: str | None
    window_label: str | None
    fault_event_id: str | None


class AlertSummary(BaseModel):
    alert_id: str
    card_id: str
    evaluation_run_id: str | None = None
    as_of_time: str | None = None
    manufacturer_id: str | None = None
    substation_id: int | None = None
    priority_rank: int | None = None
    freshness_status: FreshnessStatus | None = None
    priority_level: Literal["urgent", "high"]
    priority_score: float | None
    status: AlertStatus
    enqueue_reason: str
    created_at: str
    acked_at: str | None
    acked_by: str | None


class AlertEnqueueResponse(BaseModel):
    queued_count: int
    existing_count: int
    open_count: int
    total_count: int
    evaluation_run_id: str | None = None
    as_of_time: str | None = None


class AlertAckRequest(BaseModel):
    acked_by: str = "operator"


class AlertAckResponse(AlertSummary):
    pass
