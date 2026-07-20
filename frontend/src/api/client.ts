/**
 * API 클라이언트 토대 (골격).
 *
 * fetch 래퍼와 SSE(EventSource) 헬퍼의 시그니처만 제공한다.
 * 실제 화면 훅(예: TanStack Query useQuery/useMutation, 컴포넌트별 데이터 바인딩)은
 * 이 위에서 각 화면을 만드는 쪽이 작성한다.
 *
 * 모든 경로는 상대경로 `/api/...`로 호출한다. 개발 시 Vite dev proxy가
 * http://127.0.0.1:8003 로 전달하고, 배포 시 동일 오리진 또는 리버스 프록시가 처리한다.
 */

import type {
  ActivityProjectionQuery,
  AgentOperationsMetrics,
  AgentReportListPage,
  AgentRunArtifact,
  AgentReportCreateRequest,
  AgentLoopIteration,
  AgentRunCreateRequest,
  AgentRunEvaluationPage,
  AgentRunListPage,
  AgentRunListQuery,
  AgentRunReviewSnapshotResponse,
  AgentRunResponse,
  StageProjectionResponse,
  WorkOrderListPage,
  OperatorReviewHistory,
  OperatorReviewRecord,
  OperatorReviewSubmitRequest,
  PolicyCandidate,
  PolicyCandidateDecisionRequest,
  PolicyCandidatePage,
  OpsAgentResultV4,
  SimulationResponse,
  AlertAckRequest,
  AlertAckResponse,
  AlertEnqueueResponse,
  AlertListQuery,
  AlertSummary,
  HealthStatus,
  AutomationPolicy,
  AutomationPolicyUpdateRequest,
  EvidenceCandidate,
  EvidenceCandidateReviewRequest,
  HumanReviewTask,
  ModelCandidate,
  ModelDeployment,
  ModelPromotionRequest,
  RetrainJob,
  RetrainJobActionRequest,
  RetrainJobCreateRequest,
  ReviewSubmitResponse,
  ReviewTaskSubmitRequest,
  TrainingFeedback,
  PriorityEvaluationCreateRequest,
  PriorityEvaluationResult,
  PriorityEvaluationSnapshot,
  PrioritySubstationSnapshot,
  ReviewChatConfirmRequest,
  ReviewChatMessagePage,
  ReviewChatMessageRequest,
  ReviewChatCancelRequest,
  ReviewChatOpenRequest,
  ReviewChatConfirmationResponse,
  ReviewChatPendingProposalPage,
  ReviewChatSubmissionResponse,
  ReviewChatThreadResponse,
  ReplayDataset,
  ReplayImportRequest,
  ReplayRunCommandRequest,
  ReplayRunCommandResponse,
  ReplayRunCreateRequest,
  ReplayRunCreateResponse,
  ReplayRunSnapshot,
  ScenarioAlertCreateRequest,
  RunLineageResponse,
  CostBreakdownProjection,
  ModelCallProjection,
  ToolCallProjection,
  CurrentUser,
  OperationsPolicy,
  OperationsPolicyUpdate,
  CurrentShiftMemo,
  IncidentDocumentApproveRequest,
  IncidentDocumentPage,
  IncidentDocumentResponse,
  OperationsReportPage,
  OperationsReportPeriod,
  OperationsReportVersion,
} from './contracts'

export const API_BASE = '/api'

export class ApiError extends Error {
  readonly status: number
  readonly url: string

  constructor(status: number, url: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

/** 공통 JSON fetch 래퍼. 비정상 응답은 ApiError로 던진다. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, url, body || res.statusText)
  }
  return res.json() as Promise<T>
}

/** 서버 루트 경로용(예: /health) — /api prefix를 붙이지 않는다. */
export async function rawFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, path, body || res.statusText)
  }
  return res.json() as Promise<T>
}

export async function rawText(path: string, init?: RequestInit): Promise<string> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'text/plain', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, url, body || res.statusText)
  }
  return res.text()
}

function toQueryString(
  query?: Record<string, string | number | undefined>,
): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v != null) params.set(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

// ---------------------------------------------------------------------------
// REST 엔드포인트 (계약 표면)
// ---------------------------------------------------------------------------

export const alertsApi = {
  list: (query?: AlertListQuery) =>
    apiFetch<AlertSummary[]>(
      `/alerts${toQueryString(query as Record<string, string | undefined> | undefined)}`,
    ),
  get: (alertId: string) => apiFetch<AlertSummary>(`/alerts/${alertId}`),
  ack: (alertId: string, body: AlertAckRequest) =>
    apiFetch<AlertAckResponse>(`/alerts/${alertId}/ack`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  read: (alertId: string, body: AlertAckRequest) =>
    apiFetch<AlertAckResponse>(`/alerts/${alertId}/read`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  resolve: (alertId: string, body: AlertAckRequest) =>
    apiFetch<AlertAckResponse>(`/alerts/${alertId}/resolve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  enqueue: () => apiFetch<AlertEnqueueResponse>('/alerts/enqueue', { method: 'POST' }),
}

export const healthApi = {
  get: () => rawFetch<HealthStatus>('/health'),
}

/**
 * GET /cards — 계약(/api) 밖의 읽기 전용 편의 엔드포인트.
 * 알림(AlertSummary)에는 건물명이 없어서, card_id → substation_id 매핑을 얻어
 * 프론트 로컬 단지 데이터(complexes.ts)로 건물명을 붙이는 enrichment 용도로만 쓴다.
 * 계약·백엔드는 무변경이며, 이 엔드포인트가 없거나 실패하면 이름 없이 degrade한다.
 */
export interface CardRef {
  card_id: string
  substation_id: number | null
}

export const cardsApi = {
  list: () => rawFetch<CardRef[]>('/cards'),
}

export const priorityEvaluationsApi = {
  latest: () => apiFetch<PriorityEvaluationSnapshot>('/priority-evaluations/latest'),
  get: (evaluationRunId: string) =>
    apiFetch<PriorityEvaluationSnapshot>(`/priority-evaluations/${evaluationRunId}`),
  create: (body: PriorityEvaluationCreateRequest = {}) =>
    apiFetch<PriorityEvaluationSnapshot>('/priority-evaluations', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  alerts: () =>
    apiFetch<PriorityEvaluationResult[]>('/priority-evaluations/latest/alerts'),
  substation: (substationId: number, manufacturerId?: string) =>
    apiFetch<PrioritySubstationSnapshot>(
      `/priority-evaluations/latest/substations/${substationId}${toQueryString({ manufacturer_id: manufacturerId })}`,
    ),
}

export const simulationsApi = {
  run: (cardId: string) =>
    rawFetch<SimulationResponse>(`/simulate/${encodeURIComponent(cardId)}`, {
      method: 'POST',
    }),
}

export const agentRunsApi = {
  list: (query?: AgentRunListQuery) =>
    apiFetch<AgentRunListPage>(
      `/agent-runs${toQueryString(query as Record<string, string | number | undefined> | undefined)}`,
    ),
  create: (body: AgentRunCreateRequest) =>
    apiFetch<AgentRunResponse>('/agent-runs', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  cancel: (runId: string) => apiFetch<AgentRunResponse>(`/agent-runs/${runId}/cancel`, { method: 'POST' }),
  get: (runId: string) => apiFetch<AgentRunResponse>(`/agent-runs/${runId}`),
  review: (runId: string) =>
    apiFetch<AgentRunReviewSnapshotResponse>(`/agent-runs/${runId}/review`),
  result: (runId: string) => apiFetch<OpsAgentResultV4>(`/agent-runs/${runId}/result`),
  artifacts: (runId: string) =>
    apiFetch<AgentRunArtifact[]>(`/agent-runs/${runId}/artifacts`),
  artifactContent: (runId: string, artifactId: string) =>
    rawText(`/agent-runs/${runId}/artifacts/${artifactId}/content`),
  /** 커밋 402482a 신설 — 9단계 stage snapshot projection */
  stages: (runId: string) =>
    apiFetch<StageProjectionResponse>(`/agent-runs/${runId}/stages`),
  dailyReport: (runId: string, body: AgentReportCreateRequest) =>
    apiFetch<AgentRunArtifact>(`/agent-runs/${runId}/reports/daily`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  iterations: (runId: string) =>
    apiFetch<AgentLoopIteration[]>(`/agent-runs/${runId}/iterations`),
}

export const scenarioAlertsApi = {
  create: (body: ScenarioAlertCreateRequest) =>
    apiFetch<AlertSummary>('/scenario-alerts', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const demoAiHistoryApi = {
  reset: () => apiFetch<{ readonly reset_at: string }>('/demo/ai-history/reset', { method: 'POST' }),
}

export const reviewChatApi = {
  open: (runId: string, body: ReviewChatOpenRequest) =>
    apiFetch<ReviewChatThreadResponse>(`/agent-runs/${runId}/review-chat/threads`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  messages: (threadId: string, query?: { readonly after_sequence?: number; readonly before_sequence?: number; readonly limit?: number }) =>
    apiFetch<ReviewChatMessagePage>(`/review-chat/threads/${threadId}/messages${toQueryString(query as Record<string, number | undefined> | undefined)}`),
  allMessages: async (threadId: string) => {
    const limit = 100
    const items: ReviewChatMessagePage['items'][number][] = []
    let beforeSequence: number | undefined
    let pendingProposal: ReviewChatMessagePage['pending_proposal'] = undefined
    for (let pageIndex = 0; pageIndex < 20; pageIndex += 1) {
      const page = await reviewChatApi.messages(threadId, beforeSequence == null
        ? { after_sequence: 0, limit }
        : { before_sequence: beforeSequence, limit })
      items.unshift(...page.items)
      if (page.pending_proposal !== undefined) pendingProposal = page.pending_proposal
      const firstSequence = page.items[0]?.sequence
      const nextSequence = page.next_before_sequence ?? firstSequence
      const hasMore = page.has_more ?? page.items.length === limit
      if (!hasMore || nextSequence == null || nextSequence <= 1 || (beforeSequence != null && nextSequence >= beforeSequence)) break
      beforeSequence = nextSequence
    }
    const uniqueItems = [...new Map(items.map((item) => [item.message_id, item])).values()]
      .sort((left, right) => left.sequence - right.sequence || left.created_at.localeCompare(right.created_at))
    return { items: uniqueItems, pending_proposal: pendingProposal } satisfies ReviewChatMessagePage
  },
  pendingProposals: (threadId: string) =>
    apiFetch<ReviewChatPendingProposalPage>(`/review-chat/threads/${threadId}/proposals/pending`),
  postMessage: (threadId: string, body: ReviewChatMessageRequest) =>
    apiFetch<ReviewChatSubmissionResponse>(`/review-chat/threads/${threadId}/messages`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  confirmProposal: (proposalId: string, body: ReviewChatConfirmRequest) =>
    apiFetch<ReviewChatConfirmationResponse>(`/review-chat/proposals/${proposalId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  cancelProposal: (proposalId: string, body: ReviewChatCancelRequest) =>
    apiFetch<ReviewChatConfirmationResponse>(`/review-chat/proposals/${proposalId}/cancel`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const incidentDocumentsApi = {
  list: (incidentId: string) =>
    apiFetch<IncidentDocumentPage>(`/incidents/${incidentId}/documents`),
  approveWorkOrder: (incidentId: string, body: IncidentDocumentApproveRequest) =>
    apiFetch<IncidentDocumentResponse>(`/incidents/${incidentId}/documents/work_order/approve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const replayApi = {
  listDatasets: () => apiFetch<ReplayDataset[]>('/replay-datasets'),
  importDataset: (body: ReplayImportRequest) =>
    apiFetch<ReplayDataset>('/replay-datasets/import', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createRun: (body: ReplayRunCreateRequest) =>
    apiFetch<ReplayRunCreateResponse>('/replay-runs', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  snapshot: (runId: string) => apiFetch<ReplayRunSnapshot>(`/replay-runs/${runId}/snapshot`),
  command: (runId: string, body: ReplayRunCommandRequest) =>
    apiFetch<ReplayRunCommandResponse>(`/replay-runs/${runId}/commands`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const operationsApi = {
  currentUser: () => apiFetch<CurrentUser>('/me'),
  policy: () => apiFetch<OperationsPolicy>('/operations-policy'),
  updatePolicy: (body: OperationsPolicyUpdate) => apiFetch<OperationsPolicy>('/operations-policy', {
    method: 'PUT',
    body: JSON.stringify(body),
  }),
}

export const operationsReportsApi = {
  currentShift: () => apiFetch<CurrentShiftMemo>('/operations-reports/current-shift'),
  saveMemo: (memo: string) => apiFetch<CurrentShiftMemo>('/operations-reports/current-shift/memo', {
    method: 'PUT',
    body: JSON.stringify({ memo }),
  }),
  list: (reportType?: 'shift' | 'daily') => apiFetch<OperationsReportPage>(
    `/operations-reports${toQueryString({ report_type: reportType })}`,
  ),
  get: (reportPeriodId: string) => apiFetch<OperationsReportPeriod>(`/operations-reports/${reportPeriodId}`),
  correct: (reportPeriodId: string, body: { readonly expected_latest_version: number; readonly content: Record<string, unknown>; readonly reason: string }) =>
    apiFetch<OperationsReportVersion>(`/operations-reports/${reportPeriodId}/corrections`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const agentQualityApi = {
  lineage: (runId: string) => apiFetch<RunLineageResponse>(`/agent-runs/${runId}/rerun-lineage`),
  modelCalls: (runId: string) => apiFetch<ModelCallProjection[]>(`/agent-runs/${runId}/model-calls`),
  toolCalls: (runId: string) => apiFetch<ToolCallProjection[]>(`/agent-runs/${runId}/tool-calls`),
  cost: (runId: string) => apiFetch<CostBreakdownProjection>(`/agent-runs/${runId}/cost-breakdown`),
}

/** AI 활동 — 작업지시서/보고서 read-only projection */
export const workOrdersApi = {
  list: (query?: ActivityProjectionQuery) =>
    apiFetch<WorkOrderListPage>(
      `/work-orders${toQueryString(query as Record<string, string | number | undefined> | undefined)}`,
    ),
}

export const agentReportsApi = {
  list: (query?: ActivityProjectionQuery) =>
    apiFetch<AgentReportListPage>(
      `/agent-reports${toQueryString(query as Record<string, string | number | undefined> | undefined)}`,
    ),
}

/* ===== v3-02 신규 계약 (docs/report/06_agent_v3_backend_completion_ko.md) ===== */

/** snapshot 기준 parent/worker 결정적 평가 projection */
export const agentRunEvaluationsApi = {
  list: (query?: { run_id?: string; limit?: number }) =>
    apiFetch<AgentRunEvaluationPage>(
      `/agent-run-evaluations${toQueryString({ run_id: query?.run_id, limit: query?.limit != null ? String(query.limit) : undefined })}`,
    ),
}

/** 운영자 검토 append(낙관적 버전, 초과 시 409) + 이력 조회 */
export const operatorReviewsApi = {
  history: (runId: string) =>
    apiFetch<OperatorReviewHistory>(`/agent-runs/${runId}/reviews`),
  submit: (runId: string, body: OperatorReviewSubmitRequest) =>
    apiFetch<OperatorReviewRecord>(`/agent-runs/${runId}/reviews`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

/** 교정 검토 기반 정책 후보 조회/결정 */
export const policyCandidatesApi = {
  list: () => apiFetch<PolicyCandidatePage>('/agent-policy-candidates'),
  approve: (candidateId: string, body: PolicyCandidateDecisionRequest) =>
    apiFetch<PolicyCandidate>(`/agent-policy-candidates/${candidateId}/approve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reject: (candidateId: string, body: PolicyCandidateDecisionRequest) =>
    apiFetch<PolicyCandidate>(`/agent-policy-candidates/${candidateId}/reject`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

/** review/worker/정책 후보 운영 지표 */
export const operationsMetricsApi = {
  get: () => apiFetch<AgentOperationsMetrics>('/agent-operations/metrics'),
}

export const reviewTasksApi = {
  list: (query?: { status?: string; task_type?: string }) =>
    apiFetch<HumanReviewTask[]>(
      `/review-tasks${toQueryString(query as Record<string, string | undefined> | undefined)}`,
    ),
  get: (taskId: string) => apiFetch<HumanReviewTask>(`/review-tasks/${taskId}`),
  submit: (taskId: string, body: ReviewTaskSubmitRequest) =>
    apiFetch<ReviewSubmitResponse>(`/review-tasks/${taskId}/submit`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const evidenceCandidatesApi = {
  list: (query?: { status?: string }) =>
    apiFetch<EvidenceCandidate[]>(
      `/evidence-candidates${toQueryString(query as Record<string, string | undefined> | undefined)}`,
    ),
  review: (candidateId: string, body: EvidenceCandidateReviewRequest) =>
    apiFetch<EvidenceCandidate>(`/evidence-candidates/${candidateId}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const trainingFeedbackApi = {
  list: () => apiFetch<TrainingFeedback[]>('/training-feedback'),
}

export const automationPolicyApi = {
  get: () => apiFetch<AutomationPolicy>('/automation-policy'),
  update: (body: AutomationPolicyUpdateRequest) =>
    apiFetch<AutomationPolicy>('/automation-policy', {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
}

export const retrainJobsApi = {
  list: (query?: { status?: string }) =>
    apiFetch<RetrainJob[]>(
      `/retrain-jobs${toQueryString(query as Record<string, string | undefined> | undefined)}`,
    ),
  create: (body: RetrainJobCreateRequest) =>
    apiFetch<RetrainJob>('/retrain-jobs', { method: 'POST', body: JSON.stringify(body) }),
  approve: (jobId: string, body: RetrainJobActionRequest) =>
    apiFetch<RetrainJob>(`/retrain-jobs/${jobId}/approve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reject: (jobId: string, body: RetrainJobActionRequest) =>
    apiFetch<RetrainJob>(`/retrain-jobs/${jobId}/reject`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export const modelCandidatesApi = {
  list: (query?: { status?: string }) =>
    apiFetch<ModelCandidate[]>(
      `/model-candidates${toQueryString(query as Record<string, string | undefined> | undefined)}`,
    ),
  promote: (candidateId: string, body: ModelPromotionRequest) =>
    apiFetch<ModelCandidate>(`/model-candidates/${candidateId}/promote`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  active: () => apiFetch<ModelDeployment | null>('/model-deployments/active'),
}

// ---------------------------------------------------------------------------
// SSE 헬퍼 (골격)
// ---------------------------------------------------------------------------

/**
 * SSE 스트림 구독 헬퍼. native EventSource를 감싼다.
 * onEvent에는 파싱된 SSE envelope({type, message, payload})가 전달된다.
 * 반환된 함수를 호출하면 구독을 해제한다.
 *
 * 사용 예:
 *   const stop = subscribeSse('/agent-runs/<run_id>/events', (evt) => { ... })
 *   // cleanup: stop()
 */
export function subscribeSse(
  path: string,
  onEvent: (data: unknown) => void,
  onError?: (err: Event) => void,
): () => void {
  const source = new EventSource(`${API_BASE}${path}`)
  source.onmessage = (e: MessageEvent) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch {
      onEvent(e.data)
    }
  }
  if (onError) source.onerror = onError
  return () => source.close()
}

export const alertEventsPath = '/alerts/events'
export const agentRunEventsPath = (runId: string) => `/agent-runs/${runId}/events`
