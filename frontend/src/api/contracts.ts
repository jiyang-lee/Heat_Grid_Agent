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

/** GET /api/alerts, GET /api/alerts/{alert_id} 응답 항목 */
export interface AlertSummary {
  alert_id: string
  card_id: string
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
}

/** GET /api/alerts 쿼리 파라미터 */
export interface AlertListQuery {
  status?: AlertStatus | 'all'
  priority_level?: PriorityLevel
}

// ---------------------------------------------------------------------------
// Agent runs
// ---------------------------------------------------------------------------

export type AgentRunStatus = 'completed' | 'failed'
export type AgentMode = 'llm' | 'fallback'

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
}

/** POST /api/agent-runs, GET /api/agent-runs/{run_id} 응답 */
export interface AgentRunResponse {
  run_id: string
  status: AgentRunStatus
  input_source: 'alert'
  alert_id: string
  card_id: string
  agent_mode: AgentMode | null
  ops_output: OpsAgentOutput | null
  token_usage: TokenUsage | null
  error: string | null
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
