/**
 * 프론트/백엔드 API 계약 타입.
 *
 * 정본:
 *   - docs/report/01_frontend_backend_contract_status_ko.md (엔드포인트 목록)
 *   - simulator/versions/v2_postgres_react_ops/backend/schemas.py (응답 스키마)
 *
 * 이 파일은 백엔드 schemas.py와 1:1로 유지한다. 백엔드 계약이 바뀌면 여기부터 고친다.
 */

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export type AlertStatus = 'open' | 'acked' | 'resolved'
export type PriorityLevel = 'urgent' | 'high'
export type FreshnessStatus = 'fresh' | 'stale' | 'missing'

/** GET /api/alerts, GET /api/alerts/{alert_id} 응답 항목 */
export interface AlertSummary {
  alert_id: string
  card_id: string
  evaluation_run_id: string | null
  as_of_time: string | null
  manufacturer_id: string | null
  substation_id: number | null
  priority_rank: number | null
  freshness_status: FreshnessStatus | null
  priority_level: PriorityLevel
  priority_score: number | null
  status: AlertStatus
  enqueue_reason: string
  created_at: string
  acked_at: string | null
  acked_by: string | null
}

/** POST /api/alerts/{alert_id}/ack, /resolve 요청 body */
export interface AlertAckRequest {
  acked_by: string
}

/** POST /api/alerts/{alert_id}/ack, /resolve 응답 (AlertSummary와 동일 shape) */
export type AlertAckResponse = AlertSummary

/** POST /api/alerts/enqueue 응답 (local/dev bootstrap 전용) */
export interface AlertEnqueueResponse {
  queued_count: number
  existing_count: number
  open_count: number
  total_count: number
  evaluation_run_id: string | null
  as_of_time: string | null
}

/** GET /api/alerts 쿼리 파라미터 */
export interface AlertListQuery {
  status?: AlertStatus | 'all'
  priority_level?: PriorityLevel
}

// ---------------------------------------------------------------------------
// Priority evaluation snapshots
// ---------------------------------------------------------------------------

export interface PriorityEvaluationRun {
  evaluation_run_id: string
  as_of_time: string
  stale_after_seconds: number
  model_version: string
  status: 'running' | 'completed' | 'failed'
  is_active: boolean
  target_count: number
  success_count: number
  stale_count: number
  missing_count: number
  ranked_count: number
  error: string | null
  created_at: string
  completed_at: string | null
}

export interface PriorityEvaluationResult {
  evaluation_result_id: string
  evaluation_run_id: string
  manufacturer_id: string
  substation_id: number
  source_window_id: string | null
  source_window_start: string | null
  source_window_end: string | null
  source_card_id: string | null
  source_priority_decision_id: string | null
  priority_score: number | null
  priority_rank: number | null
  rank_included: boolean
  priority_level: string | null
  risk_score: number | null
  anomaly_score: number | null
  anomaly_label: boolean | null
  leadtime_bucket: string | null
  leadtime_urgency_score: number | null
  leadtime_hours: number | null
  freshness_status: FreshnessStatus
  data_age_seconds: number | null
  model_components: Record<string, unknown>
  created_at: string
}

export interface PriorityEvaluationSnapshot {
  evaluation: PriorityEvaluationRun
  results: PriorityEvaluationResult[]
}

export interface PrioritySubstationSnapshot {
  evaluation: PriorityEvaluationRun
  result: PriorityEvaluationResult
}

export interface PriorityEvaluationCreateRequest {
  as_of_time?: string
  stale_after_hours?: number
}

// ---------------------------------------------------------------------------
// Agent runs
// ---------------------------------------------------------------------------

export type AgentRunStatus = 'queued' | 'running' | 'completed' | 'failed'
export type AgentMode = 'llm' | 'fallback'
export type OpsAgentEvidenceSource = 'postgres' | 'pgvector' | 'jsonl' | 'kma' | 'fallback' | 'manual'

/** 에이전트 운영 산출물 (contracts/ops_agent_output.schema.json) */
export interface OpsAgentOutput {
  summary: string
  action_plan: string
  caution: string
}

export interface TokenCall {
  input_tokens: number
  cached_input_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface CostEstimate {
  model: string
  input_usd_per_1m: number
  cached_input_usd_per_1m: number
  output_usd_per_1m: number
  input_cost_usd: number
  cached_input_cost_usd: number
  output_cost_usd: number
  total_cost_usd: number
  pricing_source: string
}

export interface TokenUsage {
  model_calls: number
  input_tokens: number
  cached_input_tokens: number
  output_tokens: number
  total_tokens: number
  evidence_payload_chars: number
  cost_estimate: CostEstimate | null
  calls: TokenCall[]
}

/** POST /api/agent-runs 요청 body */
export interface AgentRunCreateRequest {
  alert_id: string
  force_new?: boolean
  requested_by?: string
  reason?: string
}

export interface AgentReportCreateRequest {
  requested_by: string
}

/** POST /api/agent-runs, GET /api/agent-runs/{run_id} 응답 */
export interface AgentRunResponse {
  run_id: string
  status: AgentRunStatus
  input_source: 'alert'
  alert_id: string
  card_id: string
  evaluation_run_id: string | null
  manufacturer_id: string | null
  substation_id: number | null
  parent_run_id: string | null
  trigger_type: string
  requested_by: string | null
  trigger_reason: string | null
  approved_action_task_id: string | null
  agent_mode: AgentMode | null
  ops_output: OpsAgentOutput | null
  token_usage: TokenUsage | null
  loop_summary: AgentLoopSummary | null
  review_status: ReviewStatus
  review_task_id: string | null
  error: string | null
}

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'corrected'
export type OperatorReviewStatus = 'pending' | 'approved' | 'corrected' | 'keep_human_review'
export type WorkerStatus =
  | 'not_triggered'
  | 'running'
  | 'completed'
  | 'failed'
  | 'timeout'
  | 'invalid'
  | 'budget_exceeded'
export type ReviewSnapshotStatus = 'pending' | 'available' | 'unavailable' | 'legacy_unavailable'

export interface AgentRunListItem {
  readonly run_id: string
  readonly status: AgentRunStatus
  readonly alert_id: string
  readonly card_id: string
  readonly priority: string | null
  readonly operator_review_status: OperatorReviewStatus
  readonly worker_status: WorkerStatus
  readonly review_snapshot_status: ReviewSnapshotStatus
  readonly created_at: string
  readonly updated_at: string
}

export interface AgentRunListPage {
  readonly items: readonly AgentRunListItem[]
  readonly next_cursor: string | null
}

export interface AgentReviewDiagnostic {
  readonly status: WorkerStatus
}

export interface AgentRunReviewSnapshot {
  readonly handling_reason: string | null
  readonly loop_count: number
  readonly diagnostic: AgentReviewDiagnostic
  readonly evidence: readonly OpsAgentEvidenceItem[]
}

export interface AgentRunReviewSnapshotResponse {
  readonly run_id: string
  readonly status: ReviewSnapshotStatus
  readonly schema_version: 'agent_run_review.v1' | null
  readonly snapshot_hash: string | null
  readonly snapshot: AgentRunReviewSnapshot | null
  readonly created_at: string | null
  readonly unavailable_reason: string | null
}

/* ===== v3-02 운영자 검토·평가 projection·정책 후보·운영 지표 =====
 * 백엔드 agent_review_api_models.py와 1:1 대응. */

export type CitationCoverage = 'complete' | 'partial' | 'missing' | 'not_applicable'
export type InputValidity = 'valid' | 'invalid' | 'unavailable'
export type ParentHandling = 'used_as_support' | 'invalid' | 'unavailable' | 'fallback_to_human'
export type EvidenceCompleteness = 'complete' | 'partial' | 'missing'
export type OperatorReviewDecision = 'approve' | 'correct' | 'keep_human_review'
export type OperatorReviewDisposition = 'normal_observation' | 'inspection_recommended' | 'urgent_review'
export type PolicyCandidateStatus = 'pending' | 'approved' | 'rejected'

/** GET /api/agent-run-evaluations 항목 — snapshot 기준 parent/worker 결정적 평가 */
export interface AgentRunEvaluationItem {
  readonly run_id: string
  readonly status: AgentRunStatus
  readonly alert_id: string
  readonly card_id: string
  readonly operator_review_status: OperatorReviewStatus
  readonly worker_status: WorkerStatus
  readonly citation_coverage: CitationCoverage
  readonly input_validity: InputValidity
  readonly parent_handling: ParentHandling
  readonly evidence_completeness: EvidenceCompleteness
  readonly review_snapshot_status: ReviewSnapshotStatus
  readonly created_at: string
  readonly updated_at: string
}

export interface AgentRunEvaluationPage {
  readonly items: readonly AgentRunEvaluationItem[]
  readonly next_cursor: string | null
}

/** POST /api/agent-runs/{run_id}/reviews 요청 — append-only, 낙관적 버전 검사(409) */
export interface OperatorReviewSubmitRequest {
  readonly expected_review_version: number
  readonly idempotency_key: string
  readonly decision: OperatorReviewDecision
  readonly reviewer: string
  readonly reason: string
  readonly disposition: OperatorReviewDisposition
  readonly correction?: Record<string, string> | null
  readonly evidence_annotations?: readonly Record<string, string | null>[]
  readonly operator_labels?: readonly string[]
}

export interface OperatorReviewRecord {
  readonly review_id: string
  readonly run_id: string
  readonly review_version: number
  readonly idempotency_key: string
  readonly request_hash: string
  readonly decision: OperatorReviewDecision
  readonly reviewer: string
  readonly reason: string
  readonly disposition: string | null
  readonly correction: Record<string, string> | null
  readonly evidence_annotations: readonly Record<string, string | null>[]
  readonly operator_labels: readonly string[]
  readonly created_at: string
}

export interface OperatorReviewHistory {
  readonly run_id: string
  readonly items: readonly OperatorReviewRecord[]
}

export interface PolicyCandidateDecisionRequest {
  readonly expected_version: number
  readonly reviewer: string
  readonly reason: string
}

/** 교정(correct) 검토에서 생성되는 정책 후보 — 승인돼도 v3 런타임 자동 반영은 없음 */
export interface PolicyCandidate {
  readonly candidate_id: string
  readonly source_review_id: string
  readonly status: PolicyCandidateStatus
  readonly version: number
  readonly scope: string
  readonly proposal: Record<string, string | number | boolean>
  readonly supporting_evidence_ids: readonly string[]
  readonly decision_history: readonly Record<string, string | number>[]
  readonly created_at: string
  readonly updated_at: string
}

export interface PolicyCandidatePage {
  readonly items: readonly PolicyCandidate[]
}

/** GET /api/agent-operations/metrics — review/worker/정책 후보 운영 지표 */
export interface AgentOperationsMetrics {
  readonly run_count: number
  readonly pending_review_count: number
  readonly approved_review_count: number
  readonly corrected_review_count: number
  readonly keep_human_review_count: number
  readonly diagnostic_completed_count: number
  readonly diagnostic_timeout_count: number
  readonly diagnostic_invalid_count: number
  readonly diagnostic_budget_exceeded_count: number
  readonly policy_candidate_pending_count: number
  readonly policy_candidate_approved_count: number
  readonly policy_candidate_rejected_count: number
  readonly approval_rate: number
  readonly correction_rate: number
}

export interface ModelVerificationResult {
  status: 'verified' | 'partial' | 'unavailable' | 'error'
  attempt: number
  feature_count: number
  feature_coverage: number
  risk_score: number | null
  stored_risk_score: number | null
  risk_score_delta: number | null
  anomaly_score: number | null
  anomaly_label: boolean | null
  leadtime_bucket: string | null
  stored_leadtime_bucket: string | null
  priority_score: number | null
  stored_priority_score: number | null
  priority_score_delta: number | null
  priority_level: string | null
  m1_specialist_priority_score: number | null
  component_agreement: Record<string, boolean>
  agreement: boolean | null
  active_model_version: string | null
  evaluation_run_id: string | null
  manufacturer_id: string | null
  substation_id: number | null
  reasons: string[]
}

export interface AgentLoopSummary {
  iterations: number
  max_iterations: number
  decision: string
  confidence: number
  evidence_score: number
  missing_evidence: string[]
  external_candidate_ids: string[]
  used_tools: string[]
  action_decisions: Record<string, unknown>[]
  model_verification: ModelVerificationResult | null
  review_required: boolean
  review_task_id: string | null
}

export interface AgentLoopIteration {
  iteration_id: number
  run_id: string
  iteration: number
  phase: string
  decision: string
  confidence: number
  evidence_score: number
  missing_evidence: string[]
  model_verification: ModelVerificationResult | null
  created_at: string
}

/** POST /simulate/{card_id} 응답 */
export interface SimulationResponse {
  card_id: string
  input_source: 'postgresql'
  agent_mode: AgentMode
  ops_output: OpsAgentOutput
  token_usage: TokenUsage
}

export interface OpsAgentEvidenceItem {
  label: string
  content: string
  source: OpsAgentEvidenceSource
}

export interface OpsAgentActionItem {
  priority: number
  title: string
  detail: string
}

export interface OpsAgentReport {
  title: string
  format: 'markdown'
  content: string
}

export interface OpsAgentResultV4 {
  schema_version: 'ops_agent_result.v4'
  run_id: string
  card_id: string
  evaluation_run_id: string | null
  manufacturer_id: string | null
  substation_id: number | null
  headline: string
  situation: string
  evidence: OpsAgentEvidenceItem[]
  actions: OpsAgentActionItem[]
  cautions: string[]
  report: OpsAgentReport
}

/** GET /api/agent-runs/{run_id}/artifacts 응답 항목 */
export interface AgentRunArtifact {
  artifact_id: string
  run_id: string
  kind: string
  name: string
  uri: string
}

// ---------------------------------------------------------------------------
// Automation review and evidence
// ---------------------------------------------------------------------------

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type ReviewTaskStatus =
  | 'pending'
  | 'auto_approved'
  | 'approved'
  | 'rejected'
  | 'corrected'
  | 'cancelled'
export type ReviewTaskType =
  | 'final_output'
  | 'model_disagreement'
  | 'evidence_candidate'
  | 'label_correction'
  | 'retrain_approval'
  | 'model_promotion'
  | 'external_search'

export interface HumanReviewTask {
  task_id: string
  task_type: ReviewTaskType
  status: ReviewTaskStatus
  risk_level: RiskLevel
  title: string
  run_id: string | null
  candidate_id: string | null
  retrain_job_id: string | null
  model_candidate_id: string | null
  payload: Record<string, unknown>
  resolution: Record<string, unknown>
  assigned_to: string | null
  reviewed_by: string | null
  created_at: string
  reviewed_at: string | null
}

export interface ReviewTaskSubmitRequest {
  decision: 'approve' | 'reject' | 'correct'
  reviewer: string
  reason: string
  corrected_output?: OpsAgentOutput
  corrected_label?: string
  metadata?: Record<string, unknown>
}

export interface TrainingFeedback {
  feedback_id: string
  task_id: string
  run_id: string | null
  card_id: string | null
  reviewer: string
  decision: string
  original_output: Record<string, unknown>
  corrected_output: Record<string, unknown>
  corrected_label: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface ReviewSubmitResponse {
  task: HumanReviewTask
  feedback: TrainingFeedback | null
  automatic_retrain_job_id: string | null
  automatic_retrain_status: RetrainJobStatus | null
  resumed_agent_run_id: string | null
  resumed_agent_run_status: AgentRunStatus | null
}

export type EvidenceCandidateStatus =
  | 'pending'
  | 'auto_approved'
  | 'approved'
  | 'rejected'
  | 'ingest_failed'

export interface EvidenceCandidate {
  candidate_id: string
  run_id: string | null
  source_type: string
  source_uri: string | null
  title: string
  content: string
  query: string | null
  risk_level: RiskLevel
  trust_score: number
  status: EvidenceCandidateStatus
  metadata: Record<string, unknown>
  requested_by: string
  reviewed_by: string | null
  review_reason: string | null
  rag_document_id: string | null
  rag_chunk_id: string | null
  created_at: string
  reviewed_at: string | null
}

export interface EvidenceCandidateReviewRequest {
  decision: 'approve' | 'reject'
  reviewer: string
  reason: string
  trust_score?: number
}

export type AutomationMode = 'human_only' | 'assisted' | 'guarded_auto'

export interface AutomationPolicy {
  policy_id: 'default'
  mode: AutomationMode
  auto_transition_enabled: boolean
  minimum_review_count: number
  minimum_approval_rate: number
  minimum_confidence: number
  minimum_source_trust: number
  maximum_drift_score: number
  final_review_required: boolean
  reviewed_count: number
  approval_rate: number
  eligible_for_guarded_auto: boolean
  updated_by: string
  updated_at: string
}

export interface AutomationPolicyUpdateRequest {
  mode?: AutomationMode
  auto_transition_enabled?: boolean
  minimum_review_count?: number
  minimum_approval_rate?: number
  minimum_confidence?: number
  minimum_source_trust?: number
  maximum_drift_score?: number
  updated_by: string
}

// ---------------------------------------------------------------------------
// Retraining and model deployment
// ---------------------------------------------------------------------------

export type RetrainJobStatus =
  | 'pending_approval'
  | 'approved'
  | 'running'
  | 'completed'
  | 'failed'
  | 'rejected'
  | 'cancelled'

export interface RetrainJob {
  job_id: string
  status: RetrainJobStatus
  requested_by: string
  reason: string
  feedback_ids: string[]
  dataset_snapshot: Record<string, unknown>
  execution_metadata: Record<string, unknown>
  approved_by: string | null
  error: string | null
  model_candidate_id: string | null
  created_at: string
  approved_at: string | null
  started_at: string | null
  completed_at: string | null
}

export interface RetrainJobCreateRequest {
  requested_by: string
  reason: string
  feedback_ids: string[]
  auto_start_when_approved: boolean
}

export interface RetrainJobActionRequest {
  reviewer: string
  reason: string
}

export type ModelCandidateStatus =
  | 'awaiting_validation'
  | 'awaiting_promotion'
  | 'promoted'
  | 'rejected'

export interface ModelCandidate {
  candidate_id: string
  job_id: string
  version: string
  artifact_uri: string
  status: ModelCandidateStatus
  baseline_metrics: Record<string, unknown>
  candidate_metrics: Record<string, unknown>
  validation_summary: Record<string, unknown>
  promoted_by: string | null
  promotion_reason: string | null
  created_at: string
  promoted_at: string | null
}

export interface ModelPromotionRequest {
  reviewer: string
  reason: string
  decision: 'promote' | 'reject'
}

export interface ModelDeployment {
  deployment_id: string
  candidate_id: string
  version: string
  artifact_uri: string
  active: boolean
  promoted_by: string
  created_at: string
}

// ---------------------------------------------------------------------------
// SSE 이벤트 (GET /api/alerts/events, /api/agent-runs/{run_id}/events)
// data: {"type", "message", "payload"}\n\n
// ---------------------------------------------------------------------------

export type SseEventType =
  | 'alerts_snapshot' // /api/alerts/events
  | 'run_started' // /api/agent-runs/{run_id}/events
  | 'run_completed'

export interface SseEnvelope<TPayload = unknown> {
  type: SseEventType | string
  message?: string
  payload: TPayload
}

// ---------------------------------------------------------------------------
// Health (GET /health, 서버 루트 — /api prefix 없음)
// ---------------------------------------------------------------------------

export interface HealthStatus {
  input: string // "postgresql"
  database: string // "connected" | "unavailable" | "mock"
  openai: string // "configured" | "missing_key" | "mock"
  rag?: string
}
