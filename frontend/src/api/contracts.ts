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
  /** additive: 백엔드 substations 정규화 uid */
  substation_uid: string | null
  /** additive: DB agent_runs.created_at — 상세 헤더 시작 시간 */
  created_at: string | null
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

/** 내부 9단계 stage 이름 (agent_stage_repository.STAGE_ORDER와 1:1) */
export type StageName =
  | 'ml_validation'
  | 'weather_context'
  | 'rag_retrieval'
  | 'rag_interpretation'
  | 'fault_analysis'
  | 'higher_model_reassessment'
  | 'parent_disposition'
  | 'report_draft'
  | 'report_fidelity'

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
  /* additive enrichment — AI 활동 목록 표시용 */
  readonly manufacturer_id: string | null
  readonly substation_id: number | null
  readonly substation_uid: string | null
  readonly alert_reason: string | null
  readonly current_stage: StageName | null
  readonly has_result: boolean
  readonly report_artifact_count: number
  readonly latest_report_name: string | null
}

export interface AgentRunListPage {
  readonly items: readonly AgentRunListItem[]
  readonly next_cursor: string | null
  /** 커서 조건 제외 필터 전체 건수 */
  readonly total_count: number | null
}

/** GET /api/agent-runs 쿼리 — 백엔드 agent_review_routes와 1:1 */
export interface AgentRunListQuery {
  readonly status?: AgentRunStatus
  readonly operator_review_status?: OperatorReviewStatus
  readonly worker_status?: WorkerStatus
  readonly priority?: string
  readonly substation_id?: number
  readonly search?: string
  readonly created_from?: string
  readonly created_to?: string
  readonly cursor?: string
  readonly limit?: number
}

/* ===== 검토 스냅샷 v1 (heatgrid_ops.agent.review_models.AgentRunReviewSnapshotV1) ===== */

export interface ReviewFinalResultSnapshot {
  readonly status: 'completed' | 'failed'
  readonly agent_mode: AgentMode | null
  readonly ops_output: OpsAgentOutput | null
  readonly error: string | null
}

export interface ReviewDecisionStep {
  readonly sequence: number
  readonly decision: string
  readonly reason: string
}

export interface ReviewDiagnosticHypothesis {
  readonly hypothesis_id: string
  readonly title: string
  readonly rationale: string
  readonly evidence_ids: readonly string[]
  readonly confidence: number
}

export interface AgentReviewDiagnostic {
  readonly trigger: string | null
  readonly status: WorkerStatus
  readonly hypotheses: readonly ReviewDiagnosticHypothesis[]
  readonly attempts: number
  readonly input_tokens: number
  readonly output_tokens: number
  readonly input_token_limit: number
  readonly output_token_limit: number
  readonly deadline_seconds: number
  readonly fallback_reason: string | null
}

export interface ReviewComponentResult {
  readonly component: string
  readonly agreement: boolean
}

export interface ReviewModelVerificationSnapshot {
  readonly status: 'verified' | 'partial' | 'unavailable' | 'error'
  readonly agreement: boolean | null
  readonly component_results: readonly ReviewComponentResult[]
  readonly stored_score: number | null
  readonly current_score: number | null
  readonly score_delta: number | null
  readonly reason: string
}

export interface ReviewProvenance {
  readonly source: string
  readonly source_owner: string | null
  readonly snapshot_id: string | null
  readonly retrieval_id: string | null
  readonly document_id: string | null
  readonly chunk_id: string | null
  readonly error_type: string | null
  readonly message: string | null
}

export interface ReviewWeatherSnapshot {
  readonly status: string
  readonly observed_at: string | null
  readonly temperature_c: number | null
  readonly humidity_percent: number | null
  readonly precipitation_mm: number | null
  readonly wind_speed_mps: number | null
  readonly provenance: ReviewProvenance
}

export interface ReviewEvidenceSnapshot {
  readonly evidence_id: string
  readonly document_type: 'internal_rag' | 'operator_manual_evidence'
  readonly source_owner: string | null
  readonly source: string
  readonly title: string
  readonly section: string | null
  readonly score: number
  readonly excerpt: string
  readonly provenance: ReviewProvenance
}

export interface ReviewSourceCardSnapshot {
  readonly card_id: string
  readonly substation_id: number | null
  readonly manufacturer_id: string | null
  readonly priority_level: string
  readonly status: string | null
  readonly review_required: boolean
  readonly reason: string
}

export interface ReviewBudgetLineage {
  readonly parent_token_limit: number
  readonly parent_tokens_used: number
  readonly diagnostic_token_limit: number
  readonly diagnostic_tokens_used: number
}

export interface ReviewCheckpointLineage {
  readonly thread_id: string
  readonly namespace: string
  readonly checkpoint_id: string | null
  readonly durability: 'sync'
}

export interface AgentRunReviewSnapshot {
  readonly schema_version: 'agent_run_review.v1'
  readonly run_id: string
  readonly result: ReviewFinalResultSnapshot
  readonly decisions: readonly ReviewDecisionStep[]
  readonly loop_count: number
  readonly handling_reason: string
  readonly diagnostic: AgentReviewDiagnostic
  readonly model_verification: ReviewModelVerificationSnapshot | null
  readonly weather: ReviewWeatherSnapshot | null
  readonly evidence: readonly ReviewEvidenceSnapshot[]
  readonly source_card: ReviewSourceCardSnapshot
  readonly budget: ReviewBudgetLineage
  readonly checkpoint: ReviewCheckpointLineage
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
export type OperatorReviewDecision = 'approve' | 'reject' | 'correct' | 'keep_human_review'
export type OperatorReviewDisposition = 'normal_observation' | 'inspection_recommended' | 'urgent_review'
/** reject/keep_human_review/targeted_rerun 시 필수 */
export type ReasonCategory =
  | 'ml_prediction_issue'
  | 'weather_context_issue'
  | 'rag_retrieval_issue'
  | 'rag_interpretation_issue'
  | 'fault_analysis_issue'
  | 'escalation_issue'
  | 'report_draft_issue'
  | 'insufficient_evidence'
  | 'operational_policy_issue'
export type OperatorReviewNextAction =
  | 'none'
  | 'targeted_rerun'
  | 'manual_investigation'
  | 'close_without_rerun'
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
  /** reject/keep_human_review(및 targeted_rerun) 시 필수 — 빠지면 422 */
  readonly reason_category?: ReasonCategory | null
  readonly next_action?: OperatorReviewNextAction
  readonly correction?: Record<string, string> | null
  readonly evidence_annotations?: readonly Record<string, string | null>[]
  readonly operator_labels?: readonly string[]
}

export interface OperatorReviewRecord {
  readonly review_id: string
  readonly run_id: string | null
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
  /* additive — v2 rerun/subject 확장(백엔드 OperatorReviewRecordResponse) */
  readonly review_task_id?: string
  readonly subject_type?: string
  readonly subject_key?: string
  readonly review_contract_version?: number
  readonly reason_category?: string | null
  readonly next_action?: string
  readonly child_run_id?: string | null
  readonly routing_status?: string | null
  readonly target_stage?: string | null
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
  /** additive: DB agent_run_artifacts.created_at */
  created_at: string | null
}

/* ===== AI 활동 stage/projection 계약 (agent_quality_routes·agent_review_routes) ===== */

/** GET /api/agent-runs/{run_id}/stages 항목 */
export interface StageProjection {
  readonly stage_snapshot_id: string
  readonly stage_name: StageName
  readonly attempt: number
  readonly execution_status: 'passed' | 'failed' | 'unavailable' | 'skipped' | 'reused'
  readonly quality_status:
    | 'passed'
    | 'partial'
    | 'retry'
    | 'insufficient'
    | 'unavailable'
    | 'skipped'
    | null
  readonly score: number | null
  readonly threshold: number | null
  readonly reasons: readonly string[]
  readonly retry_exhausted: boolean
  readonly force_review: boolean
  readonly contract_version: string
  readonly reused_from_snapshot_id: string | null
  readonly created_at: string
}

export interface StageProjectionResponse {
  readonly run_id: string
  readonly graph_contract_version: string
  readonly items: readonly StageProjection[]
}

export type ReviewChatRole = 'system_event' | 'operator' | 'assistant'
export type ReviewChatMessageKind =
  | 'question'
  | 'explanation'
  | 'action_request'
  | 'action_proposal'
  | 'confirmation'
  | 'execution_result'
  | 'error'

export type ReviewChatProposalStatus =
  | 'draft'
  | 'awaiting_confirmation'
  | 'confirmed'
  | 'executing'
  | 'executed'
  | 'cancelled'
  | 'expired'
  | 'stale'
  | 'conflict'
  | 'failed'

export type ReviewChatDecision = 'approve' | 'reject' | 'correct' | 'keep_human_review'
export type ReviewChatNextAction = 'none' | 'targeted_rerun' | 'manual_investigation' | 'close_without_rerun'

export interface ReviewChatOpenRequest {
  readonly created_by: string
  readonly idempotency_key: string
}

export interface ReviewChatThreadResponse {
  readonly thread_id: string
  readonly run_id: string
  readonly status: 'open' | 'closed' | 'archived'
  readonly context_hash: string
  readonly base_review_version: number
  readonly created_at: string
}

export interface ReviewChatMessageRequest {
  readonly content: string
  readonly created_by: string
  readonly idempotency_key: string
}

export interface ReviewChatMessageResponse {
  readonly message_id: string
  readonly thread_id: string
  readonly sequence: number
  readonly role: ReviewChatRole
  readonly message_kind: ReviewChatMessageKind
  readonly content: string
  readonly structured_payload: Record<string, unknown>
  readonly citations: readonly Record<string, string>[]
  readonly context_hash: string
  readonly created_at: string
}

export interface ReviewChatMessagePage {
  readonly items: readonly ReviewChatMessageResponse[]
}

export interface ReviewChatProposalResponse {
  readonly proposal_id: string
  readonly thread_id: string
  readonly run_id: string
  readonly expected_review_version: number
  readonly context_hash: string
  readonly status: ReviewChatProposalStatus
  readonly decision: ReviewChatDecision
  readonly next_action: ReviewChatNextAction
  readonly reason: string
  readonly reason_category: string | null
  readonly disposition: string | null
  readonly correction: Record<string, string> | null
  readonly target_stage: string | null
  readonly expires_at: string
}

export interface ReviewChatSubmissionResponse {
  readonly operator_message: ReviewChatMessageResponse
  readonly assistant_message: ReviewChatMessageResponse
  readonly proposal: ReviewChatProposalResponse | null
}

export interface ReviewChatConfirmRequest {
  readonly confirmed_by: string
  readonly idempotency_key: string
  readonly expected_proposal_status: 'awaiting_confirmation'
  readonly expected_review_version: number
}

export interface ReviewChatConfirmationResponse {
  readonly proposal_id: string
  readonly status: ReviewChatProposalStatus
  readonly review_id: string | null
  readonly child_run_id: string | null
  readonly target_stage: string | null
}

export interface ReviewChatCancelRequest {
  readonly cancelled_by: string
  readonly idempotency_key: string
}

export interface ReplayDataset {
  readonly dataset_id: string
  readonly dataset_version: string
  readonly status: 'available' | 'processing' | 'failed' | 'imported'
  readonly expected_substations: readonly number[]
  readonly source_interval_seconds: number
  readonly window_ticks: number
  readonly replay_start: string
  readonly replay_end: string
  readonly validated_at: string | null
}

export interface ReplayImportRequest {
  readonly package_path: string
  readonly imported_by: string
}

export interface ReplayRunCreateRequest {
  readonly dataset_id: string
  readonly start_at: string
  readonly tick_seconds: number
  readonly requested_by: string
}

export interface ReplayRunCreateResponse {
  readonly run_id: string
  readonly stream_key: string
  readonly state: string
  readonly version: number
}

export interface ReplayReading {
  readonly manufacturer_id: string | null
  readonly substation_id: number | null
  readonly sequence: number | null
  readonly simulated_at: string | null
  readonly values: Record<string, unknown>
  readonly quality: unknown | null
}

export interface ReplayRunSnapshot {
  readonly run_id: string
  readonly stream_key: string
  readonly state: string
  readonly version: number
  readonly current_simulated_at: string | null
  readonly last_emitted_sequence: number | null
  readonly last_scored_window_end: string | null
  readonly last_evaluation_run_id: string | null
  readonly speed_multiplier: number | null
  readonly tick_seconds: number
  readonly dataset_version: string
  readonly window_ticks: number
  readonly last_event_id: number
  readonly window_progress: number
  readonly synthetic: boolean
  readonly readings: readonly ReplayReading[]
}

export type ReplayCommandType = 'start' | 'pause' | 'resume' | 'reset' | 'seek' | 'set_speed' | 'cancel'

export interface ReplayRunCommandRequest {
  readonly command_type: ReplayCommandType
  readonly expected_run_version: number
  readonly payload: Record<string, unknown>
  readonly requested_by: string
  readonly idempotency_key: string
}

export interface ReplayRunCommandResponse {
  readonly command_id: string
  readonly status: string
}

export interface ModelCallProjection {
  readonly model_call_id: string
  readonly stage_name: string
  readonly stage_attempt: number
  readonly execution_profile: string
  readonly status: string
  readonly snapshot_bundle_hash: string | null
  readonly allowed_tools: readonly string[]
  readonly actual_tool_calls: number
  readonly actual_model_turns: number
  readonly input_tokens: number
  readonly output_tokens: number
  readonly total_tokens: number
}

export interface ToolCallProjection {
  readonly tool_call_id: string
  readonly model_call_id: string
  readonly stage_name: string
  readonly tool_name: string
  readonly status: string
  readonly call_sequence: number
}

export interface CostBreakdownProjection {
  readonly run_id: string
  readonly model_call_count: number
  readonly tool_call_count: number
  readonly input_tokens: number
  readonly output_tokens: number
  readonly total_tokens: number
}

export interface RunLineageProjection {
  readonly run_id: string
  readonly parent_run_id: string | null
  readonly root_run_id: string | null
  readonly lineage_depth: number
  readonly status: string
  readonly target_stage: string | null
}

export interface RunRerunRequestProjection {
  readonly rerun_request_id: string
  readonly source_run_id: string
  readonly child_run_id: string | null
  readonly target_stage: string
  readonly status: string
  readonly created_at: string
}

export interface RunLineageResponse {
  readonly root_run_id: string
  readonly current_run_id: string
  readonly depth: number
  readonly ancestors: readonly RunLineageProjection[]
  readonly children: readonly RunLineageProjection[]
  readonly requests: readonly RunRerunRequestProjection[]
}
/** GET /api/work-orders, /api/agent-reports 공통 쿼리 */
export interface ActivityProjectionQuery {
  readonly operator_review_status?: OperatorReviewStatus
  readonly substation_id?: number
  readonly search?: string
  readonly created_from?: string
  readonly created_to?: string
  readonly cursor?: string
  readonly limit?: number
}

/** GET /api/work-orders 항목 — result 보유 완료 run projection */
export interface WorkOrderListItem {
  readonly run_id: string
  readonly priority: string | null
  readonly alert_reason: string | null
  readonly manufacturer_id: string | null
  readonly substation_id: number | null
  readonly substation_uid: string | null
  readonly operator_review_status: OperatorReviewStatus
  readonly created_at: string
}

export interface WorkOrderListPage {
  readonly items: readonly WorkOrderListItem[]
  readonly next_cursor: string | null
  readonly total_count: number | null
}

/** GET /api/agent-reports 항목 — anomaly_report/daily_report artifact projection */
export interface AgentReportListItem {
  readonly artifact_id: string
  readonly run_id: string
  readonly kind: string
  readonly name: string
  readonly uri: string
  readonly priority: string | null
  readonly manufacturer_id: string | null
  readonly substation_id: number | null
  readonly substation_uid: string | null
  readonly operator_review_status: OperatorReviewStatus
  readonly created_at: string
}

export interface AgentReportListPage {
  readonly items: readonly AgentReportListItem[]
  readonly next_cursor: string | null
  readonly total_count: number | null
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
  database: string // "connected" | "unavailable"
  openai: string // "configured" | "missing_key"
  rag?: string
}
