/**
 * mock API — 계약 엔드포인트를 in-memory store로 구현.
 * backend.ts가 USE_MOCK일 때 real client 대신 이걸 export한다.
 */

import type {
  AgentOperationsMetrics,
  AgentRunArtifact,
  AgentReportCreateRequest,
  AgentLoopIteration,
  AgentRunCreateRequest,
  AgentRunEvaluationItem,
  AgentRunEvaluationPage,
  AgentRunListPage,
  AgentRunReviewSnapshotResponse,
  AgentRunResponse,
  OperatorReviewHistory,
  OperatorReviewRecord,
  OperatorReviewSubmitRequest,
  PolicyCandidate,
  PolicyCandidateDecisionRequest,
  PolicyCandidatePage,
  AlertAckRequest,
  AlertEnqueueResponse,
  AlertListQuery,
  AlertSummary,
  HealthStatus,
  OpsAgentResultV4,
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
} from './contracts'
import { ApiError } from './client'
import { buildTokenUsage, complexForAlert, store } from './mockData'
import { buildMockOpsOutput } from './workOrder'
import { complexes } from '../data/complexes'

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
const mockReviewTasks: HumanReviewTask[] = []
const mockEvidenceCandidates: EvidenceCandidate[] = []
const mockTrainingFeedback: TrainingFeedback[] = []
const mockRetrainJobs: RetrainJob[] = []
const mockModelCandidates: ModelCandidate[] = []
let mockActiveDeployment: ModelDeployment | null = null
const mockAsOfTime = '2026-07-09T00:00:00.000Z'
const mockEvaluationRunId = 'evaluation-mock-latest'
const mockPriorityResults: PriorityEvaluationResult[] = complexes.map((complex) => {
  const score = Number((100 - complex.id * 1.5).toFixed(3))
  const level = complex.id <= 6 ? 'urgent' : complex.id <= 15 ? 'high' : complex.id <= 23 ? 'medium' : 'low'
  return {
    evaluation_result_id: `evaluation-result-${complex.id}`,
    evaluation_run_id: mockEvaluationRunId,
    manufacturer_id: 'manufacturer 1',
    substation_id: complex.id,
    source_window_id: `window-${complex.id}`,
    source_window_start: '2026-07-08T18:00:00.000Z',
    source_window_end: mockAsOfTime,
    source_card_id: `card-${String(complex.id).padStart(3, '0')}`,
    source_priority_decision_id: `decision-${complex.id}`,
    priority_score: score,
    priority_rank: complex.id,
    rank_included: true,
    priority_level: level,
    risk_score: Number(Math.max(0.05, 1 - complex.id * 0.025).toFixed(3)),
    anomaly_score: Number(Math.max(0.05, 1 - complex.id * 0.03).toFixed(3)),
    anomaly_label: complex.id <= 8,
    leadtime_bucket: complex.id <= 6 ? '1-3d' : '7d+',
    leadtime_urgency_score: Number(Math.max(0.05, 1 - complex.id * 0.02).toFixed(3)),
    leadtime_hours: complex.id <= 6 ? 72 : null,
    freshness_status: 'fresh',
    data_age_seconds: 0,
    model_components: { priority_source: 'mock-m1-hybrid' },
    created_at: mockAsOfTime,
  }
})
const mockPrioritySnapshot: PriorityEvaluationSnapshot = {
  evaluation: {
    evaluation_run_id: mockEvaluationRunId,
    as_of_time: mockAsOfTime,
    stale_after_seconds: 2592000,
    model_version: 'mock-active-priority-contract-v1',
    status: 'completed',
    is_active: true,
    target_count: 31,
    success_count: 31,
    stale_count: 0,
    missing_count: 0,
    ranked_count: 31,
    error: null,
    created_at: mockAsOfTime,
    completed_at: mockAsOfTime,
  },
  results: mockPriorityResults,
}
let mockPolicy: AutomationPolicy = {
  policy_id: 'default',
  mode: 'human_only',
  auto_transition_enabled: false,
  minimum_review_count: 100,
  minimum_approval_rate: 0.95,
  minimum_confidence: 0.9,
  minimum_source_trust: 0.85,
  maximum_drift_score: 0.1,
  final_review_required: true,
  reviewed_count: 0,
  approval_rate: 0,
  eligible_for_guarded_auto: false,
  updated_by: 'system',
  updated_at: new Date().toISOString(),
}

function transition(alertId: string, status: 'acked' | 'resolved', ackedBy: string): AlertSummary {
  const a = store.alerts.get(alertId)
  if (!a) throw new ApiError(404, `/alerts/${alertId}`, 'alert_id를 찾을 수 없습니다.')
  const updated: AlertSummary = { ...a, status, acked_at: new Date().toISOString(), acked_by: ackedBy }
  store.alerts.set(alertId, updated)
  return updated
}

export const alertsApi = {
  async list(query?: AlertListQuery): Promise<AlertSummary[]> {
    await delay(250)
    const status = query?.status ?? 'open'
    let rows = [...store.alerts.values()]
    if (status !== 'all') rows = rows.filter((a) => a.status === status)
    if (query?.priority_level) rows = rows.filter((a) => a.priority_level === query.priority_level)
    return rows.sort(
      (a, b) => b.created_at.localeCompare(a.created_at) || (b.priority_score ?? 0) - (a.priority_score ?? 0),
    )
  },
  async get(alertId: string): Promise<AlertSummary> {
    await delay(120)
    const a = store.alerts.get(alertId)
    if (!a) throw new ApiError(404, `/alerts/${alertId}`, 'alert_id를 찾을 수 없습니다.')
    return a
  },
  async ack(alertId: string, body: AlertAckRequest): Promise<AlertSummary> {
    await delay(200)
    return transition(alertId, 'acked', body.acked_by)
  },
  async resolve(alertId: string, body: AlertAckRequest): Promise<AlertSummary> {
    await delay(200)
    return transition(alertId, 'resolved', body.acked_by)
  },
  async enqueue(): Promise<AlertEnqueueResponse> {
    await delay(150)
    const open = [...store.alerts.values()].filter((a) => a.status === 'open').length
    return {
      queued_count: 0,
      existing_count: store.alerts.size,
      open_count: open,
      total_count: store.alerts.size,
      evaluation_run_id: mockEvaluationRunId,
      as_of_time: mockAsOfTime,
    }
  },
}

export const priorityEvaluationsApi = {
  async latest(): Promise<PriorityEvaluationSnapshot> {
    await delay(100)
    return mockPrioritySnapshot
  },
  async get(evaluationRunId: string): Promise<PriorityEvaluationSnapshot> {
    if (evaluationRunId !== mockEvaluationRunId) {
      throw new ApiError(404, `/priority-evaluations/${evaluationRunId}`, '평가 실행을 찾을 수 없습니다.')
    }
    return mockPrioritySnapshot
  },
  async create(_body: PriorityEvaluationCreateRequest = {}): Promise<PriorityEvaluationSnapshot> {
    return mockPrioritySnapshot
  },
  async alerts(): Promise<PriorityEvaluationResult[]> {
    return mockPriorityResults.filter((row) => row.priority_level === 'urgent' || row.priority_level === 'high')
  },
  async substation(substationId: number): Promise<PrioritySubstationSnapshot> {
    const result = mockPriorityResults.find((row) => row.substation_id === substationId)
    if (!result) throw new ApiError(404, `/priority-evaluations/latest/substations/${substationId}`, 'Substation을 찾을 수 없습니다.')
    return { evaluation: mockPrioritySnapshot.evaluation, result }
  },
}

export const agentRunsApi = {
  async list(): Promise<AgentRunListPage> {
    await delay(100)
    return {
      items: [...store.runs.values()].map((run) => ({
        run_id: run.run_id,
        status: run.status,
        alert_id: run.alert_id,
        card_id: run.card_id,
        priority: run.review_status === 'pending' ? 'critical' : 'high',
        operator_review_status: run.review_status === 'rejected' ? 'keep_human_review' : run.review_status,
        worker_status: run.status === 'completed' ? 'completed' : run.status === 'failed' ? 'failed' : 'running',
        review_snapshot_status: run.status === 'completed' ? 'available' : 'pending',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })),
      next_cursor: null,
    }
  },
  async create(body: AgentRunCreateRequest): Promise<AgentRunResponse> {
    const existing = [...store.runs.values()].find(
      (run) => run.alert_id === body.alert_id && run.status !== 'failed',
    )
    if (existing && !body.force_new) return existing
    await delay(1100)
    const alert = store.alerts.get(body.alert_id)
    if (!alert) throw new ApiError(404, '/agent-runs', 'alert_id를 찾을 수 없습니다.')
    const complex = complexForAlert(body.alert_id)
    const opsOutput = complex
      ? buildMockOpsOutput(complex)
      : { summary: '-', action_plan: '-', caution: '-' }
    const tokenUsage = buildTokenUsage(opsOutput)
    const runId = `run-${String(store.runSeq++).padStart(4, '0')}`
    const run: AgentRunResponse = {
      run_id: runId,
      status: 'completed',
      input_source: 'alert',
      alert_id: body.alert_id,
      card_id: alert.card_id,
      evaluation_run_id: alert.evaluation_run_id,
      manufacturer_id: alert.manufacturer_id,
      substation_id: alert.substation_id,
      parent_run_id: existing?.run_id ?? null,
      trigger_type: body.force_new ? 'manual_rerun' : 'alert',
      requested_by: body.requested_by ?? null,
      trigger_reason: body.reason ?? null,
      approved_action_task_id: null,
      agent_mode: 'llm',
      ops_output: opsOutput,
      token_usage: tokenUsage,
      loop_summary: {
        iterations: 2,
        max_iterations: 4,
        decision: 'request_human',
        confidence: 0.82,
        evidence_score: 0.78,
        missing_evidence: [],
        external_candidate_ids: [],
        used_tools: ['get_ops_evidence', 'get_external_context'],
        action_decisions: [],
        model_verification: {
          status: 'verified',
          attempt: 1,
          feature_count: 313,
          feature_coverage: 1,
          risk_score: alert.priority_score,
          stored_risk_score: alert.priority_score,
          risk_score_delta: 0,
          anomaly_score: 0.7,
          anomaly_label: false,
          leadtime_bucket: '1-3d',
          stored_leadtime_bucket: '1-3d',
          priority_score: alert.priority_score,
          stored_priority_score: alert.priority_score,
          priority_score_delta: 0,
          priority_level: alert.priority_level,
          m1_specialist_priority_score: alert.priority_score,
          component_agreement: { risk: true, anomaly: true, leadtime: true, priority: true },
          agreement: true,
          active_model_version: 'mock-v1',
          evaluation_run_id: alert.evaluation_run_id,
          manufacturer_id: alert.manufacturer_id,
          substation_id: alert.substation_id,
          reasons: [],
        },
        review_required: true,
        review_task_id: `${runId}-review`,
      },
      review_status: 'pending',
      review_task_id: `${runId}-review`,
      error: null,
    }
    store.runs.set(runId, run)
    store.artifacts.set(runId, [
      { artifact_id: `${runId}-ev`, run_id: runId, kind: 'evidence', name: `evidence_${alert.card_id}.json`, uri: `/artifacts/${runId}/evidence.json` },
      { artifact_id: `${runId}-rp`, run_id: runId, kind: 'report', name: 'ops_action_report.md', uri: `/artifacts/${runId}/report.md` },
    ])
    mockReviewTasks.unshift({
      task_id: `${runId}-review`,
      task_type: 'final_output',
      status: 'pending',
      risk_level: alert.priority_level === 'urgent' ? 'critical' : 'high',
      title: `에이전트 최종 운영 결과 검수: ${alert.card_id}`,
      run_id: runId,
      candidate_id: null,
      retrain_job_id: null,
      model_candidate_id: null,
      payload: { ops_output: opsOutput },
      resolution: {},
      assigned_to: null,
      reviewed_by: null,
      created_at: new Date().toISOString(),
      reviewed_at: null,
    })
    return run
  },
  async get(runId: string): Promise<AgentRunResponse> {
    await delay(120)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}`, 'run_id를 찾을 수 없습니다.')
    return r
  },
  async review(runId: string): Promise<AgentRunReviewSnapshotResponse> {
    await delay(100)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/review`, 'run_id를 찾을 수 없습니다.')
    return {
      run_id: runId,
      status: r.status === 'completed' ? 'available' : 'pending',
      schema_version: r.status === 'completed' ? 'agent_run_review.v1' : null,
      snapshot_hash: r.status === 'completed' ? `mock-${runId}` : null,
      snapshot: r.status === 'completed'
        ? {
          handling_reason: r.ops_output?.summary ?? null,
          loop_count: r.loop_summary?.iterations ?? 0,
          diagnostic: { status: 'completed' },
          evidence: [{ label: '운영 근거', content: 'mock priority card evidence', source: 'manual' }],
        }
        : null,
      created_at: r.status === 'completed' ? new Date().toISOString() : null,
      unavailable_reason: r.status === 'completed' ? null : '실행이 아직 완료되지 않았습니다.',
    }
  },
  async result(runId: string): Promise<OpsAgentResultV4> {
    await delay(160)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/result`, 'run_id를 찾을 수 없습니다.')
    const output = r.ops_output
    if (!output) throw new ApiError(409, `/agent-runs/${runId}/result`, 'agent run result is not ready.')
    return {
      schema_version: 'ops_agent_result.v4',
      run_id: r.run_id,
      card_id: r.card_id,
      evaluation_run_id: r.evaluation_run_id,
      manufacturer_id: r.manufacturer_id,
      substation_id: r.substation_id,
      headline: output.summary,
      situation: output.summary,
      evidence: [
        { label: '운영 근거', content: 'mock priority card evidence', source: 'manual' },
      ],
      actions: [{ priority: 1, title: '권장 조치', detail: output.action_plan }],
      cautions: [output.caution],
      report: {
        title: '작업 지시 보고서',
        format: 'markdown',
        content: `# 작업 지시 보고서\n\n## 상황 요약\n${output.summary}\n\n## 권장 조치\n${output.action_plan}\n\n## 주의 사항\n${output.caution}\n`,
      },
    }
  },
  async artifacts(runId: string): Promise<AgentRunArtifact[]> {
    await delay(150)
    if (!store.runs.has(runId)) throw new ApiError(404, `/agent-runs/${runId}/artifacts`, 'run_id를 찾을 수 없습니다.')
    return store.artifacts.get(runId) ?? []
  },
  async dailyReport(runId: string, _body: AgentReportCreateRequest): Promise<AgentRunArtifact> {
    await delay(400)
    if (!store.runs.has(runId)) throw new ApiError(404, `/agent-runs/${runId}`, 'run_id를 찾을 수 없습니다.')
    const artifacts = store.artifacts.get(runId) ?? []
    const existing = artifacts.find((item) => item.name === 'daily_report.json')
    if (existing) return existing
    const artifact: AgentRunArtifact = {
      artifact_id: `${runId}-daily`,
      run_id: runId,
      kind: 'daily_report',
      name: 'daily_report.json',
      uri: `output/ops_agent/reports/${runId}/daily_report.json`,
    }
    store.artifacts.set(runId, [...artifacts, artifact])
    return artifact
  },
  async iterations(runId: string): Promise<AgentLoopIteration[]> {
    await delay(80)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/iterations`, 'run_id를 찾을 수 없습니다.')
    const summary = r.loop_summary
    return [
      {
        iteration_id: 1,
        run_id: runId,
        iteration: 1,
        phase: 'evidence_assessment',
        decision: summary?.decision ?? 'finalize',
        confidence: summary?.confidence ?? 0,
        evidence_score: summary?.evidence_score ?? 0,
        missing_evidence: summary?.missing_evidence ?? [],
        model_verification: summary?.model_verification ?? null,
        created_at: new Date().toISOString(),
      },
    ]
  },
}

/* ===== v3-02 mock (계약 shape 동일, 데모 최소 구현) ===== */

const mockOperatorReviews = new Map<string, OperatorReviewRecord[]>()

export const agentRunEvaluationsApi = {
  async list(query?: { run_id?: string; limit?: number }): Promise<AgentRunEvaluationPage> {
    await delay(90)
    const items = [...store.runs.values()]
      .filter((run) => !query?.run_id || run.run_id === query.run_id)
      .slice(0, query?.limit ?? 20)
      .map((run): AgentRunEvaluationItem => ({
        run_id: run.run_id,
        status: run.status,
        alert_id: run.alert_id,
        card_id: run.card_id,
        operator_review_status: (mockOperatorReviews.get(run.run_id)?.at(-1)?.decision === 'approve' ? 'approved' : mockOperatorReviews.get(run.run_id)?.at(-1)?.decision === 'correct' ? 'corrected' : mockOperatorReviews.get(run.run_id)?.length ? 'keep_human_review' : 'pending'),
        worker_status: run.status === 'completed' ? 'completed' : 'not_triggered',
        citation_coverage: 'partial',
        input_validity: 'valid',
        parent_handling: 'used_as_support',
        evidence_completeness: 'partial',
        review_snapshot_status: run.status === 'completed' ? 'available' : 'pending',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }))
    return { items, next_cursor: null }
  },
}

export const operatorReviewsApi = {
  async history(runId: string): Promise<OperatorReviewHistory> {
    await delay(80)
    return { run_id: runId, items: mockOperatorReviews.get(runId) ?? [] }
  },
  async submit(runId: string, body: OperatorReviewSubmitRequest): Promise<OperatorReviewRecord> {
    await delay(200)
    const items = mockOperatorReviews.get(runId) ?? []
    const latest = items.at(-1)?.review_version ?? 0
    if (body.expected_review_version !== latest) {
      throw new ApiError(409, `/agent-runs/${runId}/reviews`, 'review version is stale')
    }
    const record: OperatorReviewRecord = {
      review_id: `mock-review-${latest + 1}`,
      run_id: runId,
      review_version: latest + 1,
      idempotency_key: body.idempotency_key,
      request_hash: 'mock'.padEnd(64, '0'),
      decision: body.decision,
      reviewer: body.reviewer,
      reason: body.reason,
      disposition: body.disposition,
      correction: body.correction ?? null,
      evidence_annotations: body.evidence_annotations ?? [],
      operator_labels: body.operator_labels ?? [],
      created_at: new Date().toISOString(),
    }
    mockOperatorReviews.set(runId, [...items, record])
    return record
  },
}

export const policyCandidatesApi = {
  async list(): Promise<PolicyCandidatePage> {
    await delay(80)
    return { items: [] }
  },
  async approve(candidateId: string, _body: PolicyCandidateDecisionRequest): Promise<PolicyCandidate> {
    await delay(100)
    throw new ApiError(404, `/agent-policy-candidates/${candidateId}/approve`, 'mock에는 정책 후보가 없습니다.')
  },
  async reject(candidateId: string, _body: PolicyCandidateDecisionRequest): Promise<PolicyCandidate> {
    await delay(100)
    throw new ApiError(404, `/agent-policy-candidates/${candidateId}/reject`, 'mock에는 정책 후보가 없습니다.')
  },
}

export const operationsMetricsApi = {
  async get(): Promise<AgentOperationsMetrics> {
    await delay(80)
    const reviews = [...mockOperatorReviews.values()].flat()
    const approved = reviews.filter((item) => item.decision === 'approve').length
    const corrected = reviews.filter((item) => item.decision === 'correct').length
    const runCount = store.runs.size
    return {
      run_count: runCount,
      pending_review_count: Math.max(0, runCount - approved - corrected),
      approved_review_count: approved,
      corrected_review_count: corrected,
      keep_human_review_count: reviews.filter((item) => item.decision === 'keep_human_review').length,
      diagnostic_completed_count: runCount,
      diagnostic_timeout_count: 0,
      diagnostic_invalid_count: 0,
      diagnostic_budget_exceeded_count: 0,
      policy_candidate_pending_count: 0,
      policy_candidate_approved_count: 0,
      policy_candidate_rejected_count: 0,
      approval_rate: runCount === 0 ? 0 : approved / runCount,
      correction_rate: runCount === 0 ? 0 : corrected / runCount,
    }
  },
}

export const reviewTasksApi = {
  async list(query?: { status?: string; task_type?: string }): Promise<HumanReviewTask[]> {
    await delay(80)
    return mockReviewTasks.filter(
      (task) => (!query?.status || task.status === query.status) && (!query?.task_type || task.task_type === query.task_type),
    )
  },
  async get(taskId: string): Promise<HumanReviewTask> {
    const task = mockReviewTasks.find((item) => item.task_id === taskId)
    if (!task) throw new ApiError(404, `/review-tasks/${taskId}`, 'task_id를 찾을 수 없습니다.')
    return task
  },
  async submit(taskId: string, body: ReviewTaskSubmitRequest): Promise<ReviewSubmitResponse> {
    await delay(100)
    const task = mockReviewTasks.find((item) => item.task_id === taskId)
    if (!task) throw new ApiError(404, `/review-tasks/${taskId}`, 'task_id를 찾을 수 없습니다.')
    task.status = body.decision === 'approve' ? 'approved' : body.decision === 'reject' ? 'rejected' : 'corrected'
    task.reviewed_by = body.reviewer
    task.reviewed_at = new Date().toISOString()
    task.resolution = body as unknown as Record<string, unknown>
    const feedback: TrainingFeedback | null = task.task_type === 'final_output'
      ? {
          feedback_id: `feedback-${taskId}`,
          task_id: taskId,
          run_id: task.run_id,
          card_id: null,
          reviewer: body.reviewer,
          decision: body.decision,
          original_output: task.payload,
          corrected_output: (body.corrected_output ?? {}) as Record<string, unknown>,
          corrected_label: body.corrected_label ?? null,
          metadata: body.metadata ?? {},
          created_at: new Date().toISOString(),
        }
      : null
    if (feedback) mockTrainingFeedback.unshift(feedback)
    if (task.run_id) {
      const run = store.runs.get(task.run_id)
      if (run) {
        run.review_status = task.status
        if (body.corrected_output) run.ops_output = body.corrected_output
      }
    }
    return {
      task,
      feedback,
      automatic_retrain_job_id: null,
      automatic_retrain_status: null,
      resumed_agent_run_id: null,
      resumed_agent_run_status: null,
    }
  },
}

export const evidenceCandidatesApi = {
  async list(query?: { status?: string }): Promise<EvidenceCandidate[]> {
    await delay(80)
    return mockEvidenceCandidates.filter((item) => !query?.status || item.status === query.status)
  },
  async review(candidateId: string, body: EvidenceCandidateReviewRequest): Promise<EvidenceCandidate> {
    const item = mockEvidenceCandidates.find((candidate) => candidate.candidate_id === candidateId)
    if (!item) throw new ApiError(404, `/evidence-candidates/${candidateId}`, 'candidate_id를 찾을 수 없습니다.')
    item.status = body.decision === 'approve' ? 'approved' : 'rejected'
    item.reviewed_by = body.reviewer
    item.review_reason = body.reason
    item.reviewed_at = new Date().toISOString()
    return item
  },
}

export const trainingFeedbackApi = {
  async list(): Promise<TrainingFeedback[]> {
    return mockTrainingFeedback
  },
}

export const automationPolicyApi = {
  async get(): Promise<AutomationPolicy> {
    return mockPolicy
  },
  async update(body: AutomationPolicyUpdateRequest): Promise<AutomationPolicy> {
    mockPolicy = { ...mockPolicy, ...body, updated_at: new Date().toISOString() }
    return mockPolicy
  },
}

export const retrainJobsApi = {
  async list(query?: { status?: string }): Promise<RetrainJob[]> {
    return mockRetrainJobs.filter((item) => !query?.status || item.status === query.status)
  },
  async create(body: RetrainJobCreateRequest): Promise<RetrainJob> {
    const now = new Date().toISOString()
    const job: RetrainJob = {
      job_id: `retrain-${mockRetrainJobs.length + 1}`,
      status: 'pending_approval',
      requested_by: body.requested_by,
      reason: body.reason,
      feedback_ids: body.feedback_ids,
      dataset_snapshot: { feedback_count: mockTrainingFeedback.length },
      execution_metadata: {},
      approved_by: null,
      error: null,
      model_candidate_id: null,
      created_at: now,
      approved_at: null,
      started_at: null,
      completed_at: null,
    }
    mockRetrainJobs.unshift(job)
    return job
  },
  async approve(jobId: string, body: RetrainJobActionRequest): Promise<RetrainJob> {
    const job = mockRetrainJobs.find((item) => item.job_id === jobId)
    if (!job) throw new ApiError(404, `/retrain-jobs/${jobId}`, 'job_id를 찾을 수 없습니다.')
    job.status = 'approved'
    job.approved_by = body.reviewer
    job.approved_at = new Date().toISOString()
    return job
  },
  async reject(jobId: string, body: RetrainJobActionRequest): Promise<RetrainJob> {
    const job = mockRetrainJobs.find((item) => item.job_id === jobId)
    if (!job) throw new ApiError(404, `/retrain-jobs/${jobId}`, 'job_id를 찾을 수 없습니다.')
    job.status = 'rejected'
    job.approved_by = body.reviewer
    return job
  },
}

export const modelCandidatesApi = {
  async list(query?: { status?: string }): Promise<ModelCandidate[]> {
    return mockModelCandidates.filter((item) => !query?.status || item.status === query.status)
  },
  async promote(candidateId: string, body: ModelPromotionRequest): Promise<ModelCandidate> {
    const candidate = mockModelCandidates.find((item) => item.candidate_id === candidateId)
    if (!candidate) throw new ApiError(404, `/model-candidates/${candidateId}`, 'candidate_id를 찾을 수 없습니다.')
    candidate.status = body.decision === 'promote' ? 'promoted' : 'rejected'
    candidate.promoted_by = body.reviewer
    candidate.promotion_reason = body.reason
    candidate.promoted_at = new Date().toISOString()
    if (body.decision === 'promote') {
      mockActiveDeployment = {
        deployment_id: `deploy-${candidateId}`,
        candidate_id: candidateId,
        version: candidate.version,
        artifact_uri: candidate.artifact_uri,
        active: true,
        promoted_by: body.reviewer,
        created_at: new Date().toISOString(),
      }
    }
    return candidate
  },
  async active(): Promise<ModelDeployment | null> {
    return mockActiveDeployment
  },
}

export const healthApi = {
  async get(): Promise<HealthStatus> {
    await delay(80)
    return { input: 'postgresql', database: 'mock', openai: 'mock', rag: 'mock' }
  },
}

/** mock SSE — 실제 EventSource 대신 타이머로 계약 이벤트를 방출. */
export function subscribeSse(path: string, onEvent: (data: unknown) => void): () => void {
  const timers: ReturnType<typeof setTimeout>[] = []
  if (path.includes('/agent-runs/') && path.endsWith('/events')) {
    const runId = path.split('/agent-runs/')[1].replace('/events', '')
    const run = store.runs.get(runId)
    if (run) {
      timers.push(
        setTimeout(
          () => onEvent({ type: 'run_started', message: 'agent run loaded', payload: { run_id: run.run_id, alert_id: run.alert_id } }),
          200,
        ),
      )
      timers.push(
        setTimeout(
          () =>
            onEvent({
              type: 'run_completed',
              message: 'agent run completed',
              payload: {
                run_id: run.run_id,
                status: run.status,
                card_id: run.card_id,
                agent_mode: run.agent_mode,
                ops_output: run.ops_output,
                token_usage: run.token_usage,
              },
            }),
          700,
        ),
      )
    }
  } else if (path.endsWith('/alerts/events')) {
    const open = [...store.alerts.values()].filter((a) => a.status === 'open')
    timers.push(
      setTimeout(() => onEvent({ type: 'alerts_snapshot', message: 'current open alerts loaded', payload: { alerts: open } }), 200),
    )
  }
  return () => timers.forEach(clearTimeout)
}

export const alertEventsPath = '/alerts/events'
export const agentRunEventsPath = (runId: string) => `/agent-runs/${runId}/events`
