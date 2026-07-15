/**
 * mock API — 계약 엔드포인트를 in-memory store로 구현.
 * backend.ts가 USE_MOCK일 때 real client 대신 이걸 export한다.
 */

import type {
  ActivityProjectionQuery,
  AgentOperationsMetrics,
  AgentReportListPage,
  AgentRunArtifact,
  AgentReportCreateRequest,
  AgentLoopIteration,
  AgentRunCreateRequest,
  AgentRunEvaluationItem,
  AgentRunEvaluationPage,
  AgentRunListItem,
  AgentRunListPage,
  AgentRunListQuery,
  AgentRunReviewSnapshotResponse,
  AgentRunResponse,
  OperatorReviewHistory,
  OperatorReviewRecord,
  OperatorReviewStatus,
  OperatorReviewSubmitRequest,
  StageName,
  StageProjectionResponse,
  WorkOrderListPage,
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

/** mock 결정적 기준 시각(mockData BASE_MS와 동일 값) */
const BASE_TIME_MS = Date.parse('2026-07-09T09:00:00+09:00')

/** 내부 9단계 stage 순서 — 백엔드 STAGE_ORDER와 1:1 */
const STAGE_NAMES: readonly StageName[] = [
  'ml_validation',
  'weather_context',
  'rag_retrieval',
  'rag_interpretation',
  'fault_analysis',
  'higher_model_reassessment',
  'parent_disposition',
  'report_draft',
  'report_fidelity',
]

/** 홈 '대기 서류' 시안 수치(3건) 재현용 검토 대기 문서. run 생성 시 새 task가 앞에 쌓인다. */
function seedReviewTask(seq: number, title: string, riskLevel: HumanReviewTask['risk_level'], createdAt: string): HumanReviewTask {
  return {
    task_id: `review-seed-${seq}`,
    task_type: 'final_output',
    status: 'pending',
    risk_level: riskLevel,
    title,
    run_id: null,
    candidate_id: null,
    retrain_job_id: null,
    model_candidate_id: null,
    payload: {},
    resolution: {},
    assigned_to: null,
    reviewed_by: null,
    created_at: createdAt,
    reviewed_at: null,
  }
}

const mockReviewTasks: HumanReviewTask[] = [
  seedReviewTask(1, '작업 지시 보고서 승인: 공급온도 과다 대응', 'high', '2026-07-09T08:40:00.000Z'),
  seedReviewTask(2, '점검 결과 보고서 검토: 압력 상승 경향', 'medium', '2026-07-09T08:10:00.000Z'),
  seedReviewTask(3, '일일 운영 보고서 발행 승인', 'medium', '2026-07-09T07:30:00.000Z'),
]
const mockEvidenceCandidates: EvidenceCandidate[] = []
const mockTrainingFeedback: TrainingFeedback[] = []
const mockRetrainJobs: RetrainJob[] = []
const mockModelCandidates: ModelCandidate[] = []
let mockActiveDeployment: ModelDeployment | null = null
const mockAsOfTime = '2026-07-09T00:00:00.000Z'
const mockEvaluationRunId = 'evaluation-mock-latest'
const mockPriorityResults: PriorityEvaluationResult[] = complexes.map((complex) => {
  const score = Number((100 - complex.id * 1.5).toFixed(3))
  // 홈 시안 수치 재현: 위험 2 / 주의 5 / 정상 24 (medium·low는 홈 집계상 정상).
  const level = complex.id <= 2 ? 'urgent' : complex.id <= 7 ? 'high' : complex.id <= 23 ? 'medium' : 'low'
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

/** 백엔드 목록 projection과 동일 규칙: reject는 ELSE 분기라 pending으로 투영된다. */
function latestOperatorStatus(runId: string): OperatorReviewStatus {
  const latest = mockOperatorReviews.get(runId)?.at(-1)
  if (!latest) return 'pending'
  if (latest.decision === 'approve') return 'approved'
  if (latest.decision === 'correct') return 'corrected'
  if (latest.decision === 'keep_human_review') return 'keep_human_review'
  return 'pending'
}

const REPORT_KINDS = ['anomaly_report', 'daily_report'] as const

function reportArtifactsOf(runId: string): AgentRunArtifact[] {
  return (store.artifacts.get(runId) ?? []).filter((artifact) =>
    (REPORT_KINDS as readonly string[]).includes(artifact.kind),
  )
}

function runListItem(run: AgentRunResponse): AgentRunListItem {
  const alert = store.alerts.get(run.alert_id)
  const reports = reportArtifactsOf(run.run_id)
  return {
    run_id: run.run_id,
    status: run.status,
    alert_id: run.alert_id,
    card_id: run.card_id,
    priority: alert?.priority_level ?? null,
    operator_review_status: latestOperatorStatus(run.run_id),
    worker_status: run.status === 'completed' ? 'completed' : run.status === 'failed' ? 'failed' : 'running',
    review_snapshot_status: run.status === 'completed' ? 'available' : 'pending',
    created_at: run.created_at ?? new Date(BASE_TIME_MS).toISOString(),
    updated_at: run.created_at ?? new Date(BASE_TIME_MS).toISOString(),
    manufacturer_id: run.manufacturer_id,
    substation_id: run.substation_id,
    substation_uid: run.substation_uid,
    alert_reason: alert?.enqueue_reason ?? null,
    current_stage: run.status === 'completed' ? 'report_fidelity' : run.status === 'failed' ? 'fault_analysis' : 'rag_interpretation',
    has_result: run.ops_output != null,
    report_artifact_count: reports.length,
    latest_report_name: reports.at(-1)?.name ?? null,
  }
}

function matchesPeriod(createdAt: string, query?: { created_from?: string; created_to?: string }): boolean {
  const at = Date.parse(createdAt)
  if (query?.created_from && at < Date.parse(query.created_from)) return false
  if (query?.created_to && at > Date.parse(query.created_to)) return false
  return true
}

export const agentRunsApi = {
  async list(query?: AgentRunListQuery): Promise<AgentRunListPage> {
    await delay(100)
    const needle = query?.search?.toLowerCase()
    const items = [...store.runs.values()]
      .map(runListItem)
      .filter((item) => (query?.status ? item.status === query.status : true))
      .filter((item) => (query?.operator_review_status ? item.operator_review_status === query.operator_review_status : true))
      .filter((item) => (query?.substation_id != null ? item.substation_id === query.substation_id : true))
      .filter((item) => matchesPeriod(item.created_at, query))
      .filter((item) =>
        needle
          ? [item.alert_reason, item.manufacturer_id, item.run_id, item.card_id, item.latest_report_name]
              .some((value) => value?.toLowerCase().includes(needle))
          : true,
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.run_id.localeCompare(a.run_id))
    const limit = query?.limit ?? 50
    return {
      items: items.slice(0, limit),
      next_cursor: null,
      total_count: items.length,
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
      substation_uid: null,
      created_at: new Date().toISOString(),
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
      { artifact_id: `${runId}-ev`, run_id: runId, kind: 'evidence', name: `evidence_${alert.card_id}.json`, uri: `/artifacts/${runId}/evidence.json`, created_at: run.created_at },
      { artifact_id: `${runId}-rp`, run_id: runId, kind: 'anomaly_report', name: 'ops_action_report.md', uri: `/artifacts/${runId}/report.md`, created_at: run.created_at },
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
    const alert = store.alerts.get(r.alert_id)
    return {
      run_id: runId,
      status: r.status === 'completed' ? 'available' : 'pending',
      schema_version: r.status === 'completed' ? 'agent_run_review.v1' : null,
      snapshot_hash: r.status === 'completed' ? `mock-${runId}` : null,
      snapshot: r.status === 'completed'
        ? {
          schema_version: 'agent_run_review.v1',
          run_id: runId,
          result: { status: 'completed', agent_mode: r.agent_mode, ops_output: r.ops_output, error: null },
          decisions: [
            { sequence: 1, decision: 'collect_evidence', reason: '우선순위 카드와 내부 근거를 수집했습니다.' },
            { sequence: 2, decision: 'finalize', reason: '수집 근거가 충분하여 최종 보고를 확정했습니다.' },
          ],
          loop_count: r.loop_summary?.iterations ?? 0,
          handling_reason: r.ops_output?.summary ?? '완료된 실행입니다.',
          diagnostic: {
            trigger: null,
            status: 'completed',
            hypotheses: [
              {
                hypothesis_id: `${runId}-hyp-1`,
                title: '열교환기 2차측 열부하 감소 가능성',
                rationale: '공급온도 하락과 유량 변화가 동시에 관측되어 2차측 부하 변동을 우선 검토합니다.',
                evidence_ids: [`${runId}-ev-1`],
                confidence: 0.82,
              },
            ],
            attempts: 1,
            input_tokens: 1200,
            output_tokens: 320,
            input_token_limit: 3000,
            output_token_limit: 1000,
            deadline_seconds: 60,
            fallback_reason: null,
          },
          model_verification: {
            status: 'verified',
            agreement: true,
            component_results: [
              { component: 'risk', agreement: true },
              { component: 'anomaly', agreement: true },
              { component: 'priority', agreement: true },
            ],
            stored_score: alert?.priority_score ?? null,
            current_score: alert?.priority_score ?? null,
            score_delta: 0,
            reason: '저장 점수와 재계산 점수가 일치합니다.',
          },
          weather: {
            status: 'available',
            observed_at: r.created_at,
            temperature_c: 26.1,
            humidity_percent: 78,
            precipitation_mm: 2.1,
            wind_speed_mps: 1.4,
            provenance: { source: 'KMA 관측(mock)', source_owner: 'kma', snapshot_id: null, retrieval_id: null, document_id: null, chunk_id: null, error_type: null, message: null },
          },
          evidence: [
            {
              evidence_id: `${runId}-ev-1`,
              document_type: 'internal_rag',
              source_owner: 'ops',
              source: '내부 운영 문서(mock)',
              title: '열교환기 유량 상승 대응 사례',
              section: '조치 절차',
              score: 0.87,
              excerpt: '2차측 유량 증가와 공급온도 하락이 동반되면 열교환기 연결부 점검을 우선한다.',
              provenance: { source: 'internal(mock)', source_owner: 'ops', snapshot_id: null, retrieval_id: null, document_id: 'R-021', chunk_id: null, error_type: null, message: null },
            },
            {
              evidence_id: `${runId}-ev-2`,
              document_type: 'operator_manual_evidence',
              source_owner: 'operator',
              source: '운영 노트(mock)',
              title: '현장 열림 밸브 확인 기록',
              section: null,
              score: 0.8,
              excerpt: '보충수 밸브 설정 변경 이력이 있어 현장 확인이 필요하다.',
              provenance: { source: 'note(mock)', source_owner: 'operator', snapshot_id: null, retrieval_id: null, document_id: 'N-20260711-01', chunk_id: null, error_type: null, message: null },
            },
          ],
          source_card: {
            card_id: r.card_id,
            substation_id: r.substation_id,
            manufacturer_id: r.manufacturer_id,
            priority_level: alert?.priority_level ?? 'high',
            status: alert?.status ?? null,
            review_required: true,
            reason: alert?.enqueue_reason ?? '우선순위 카드 검토 대상',
          },
          budget: { parent_token_limit: 60000, parent_tokens_used: 4200, diagnostic_token_limit: 3000, diagnostic_tokens_used: 1520 },
          checkpoint: { thread_id: runId, namespace: 'mock', checkpoint_id: null, durability: 'sync' },
        }
        : null,
      created_at: r.status === 'completed' ? r.created_at : null,
      unavailable_reason: r.status === 'completed' ? null : '실행이 아직 완료되지 않았습니다.',
    }
  },
  /** 9단계 stage snapshot projection — 완료 run은 전 단계 passed로 결정적 구성 */
  async stages(runId: string): Promise<StageProjectionResponse> {
    await delay(80)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/stages`, 'run_id를 찾을 수 없습니다.')
    const baseMs = Date.parse(r.created_at ?? new Date(BASE_TIME_MS).toISOString())
    const completedCount = r.status === 'completed' ? STAGE_NAMES.length : r.status === 'failed' ? 5 : 4
    return {
      run_id: runId,
      graph_contract_version: 'agent_graph_v2.v3',
      items: STAGE_NAMES.slice(0, completedCount).map((stageName, index) => ({
        stage_snapshot_id: `${runId}-stage-${index + 1}`,
        stage_name: stageName,
        attempt: 1,
        execution_status: r.status === 'failed' && index === completedCount - 1 ? 'failed' : 'passed',
        quality_status: ['higher_model_reassessment', 'parent_disposition'].includes(stageName) ? null : 'passed',
        score: ['higher_model_reassessment', 'parent_disposition'].includes(stageName) ? null : 92,
        threshold: ['higher_model_reassessment', 'parent_disposition'].includes(stageName) ? null : 70,
        reasons: [],
        retry_exhausted: false,
        force_review: false,
        contract_version: 'stage.v1',
        reused_from_snapshot_id: null,
        created_at: new Date(baseMs + (index + 1) * 45_000).toISOString(),
      })),
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
      created_at: new Date().toISOString(),
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

/* ===== AI 활동 — 작업지시서/보고서 projection mock ===== */

function projectionFilter<
  T extends { operator_review_status: OperatorReviewStatus; substation_id: number | null; created_at: string },
>(
  rows: T[],
  query: ActivityProjectionQuery | undefined,
  searchText: (item: T) => readonly (string | null)[],
): { items: T[]; total: number } {
  const needle = query?.search?.toLowerCase()
  const filtered = rows
    .filter((item) => (query?.operator_review_status ? item.operator_review_status === query.operator_review_status : true))
    .filter((item) => (query?.substation_id != null ? item.substation_id === query.substation_id : true))
    .filter((item) => matchesPeriod(item.created_at, query))
    .filter((item) => (needle ? searchText(item).some((value) => value?.toLowerCase().includes(needle)) : true))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
  return { items: filtered.slice(0, query?.limit ?? 50), total: filtered.length }
}

export const workOrdersApi = {
  async list(query?: ActivityProjectionQuery): Promise<WorkOrderListPage> {
    await delay(100)
    const rows = [...store.runs.values()]
      .filter((run) => run.ops_output != null)
      .map((run) => {
        const alert = store.alerts.get(run.alert_id)
        return {
          run_id: run.run_id,
          priority: alert?.priority_level ?? null,
          alert_reason: alert?.enqueue_reason ?? null,
          manufacturer_id: run.manufacturer_id,
          substation_id: run.substation_id,
          substation_uid: run.substation_uid,
          operator_review_status: latestOperatorStatus(run.run_id),
          created_at: run.created_at ?? new Date(BASE_TIME_MS).toISOString(),
        }
      })
    const { items, total } = projectionFilter(rows, query, (item) => [item.alert_reason, item.manufacturer_id, item.run_id])
    return { items, next_cursor: null, total_count: total }
  },
}

export const agentReportsApi = {
  async list(query?: ActivityProjectionQuery): Promise<AgentReportListPage> {
    await delay(100)
    const rows = [...store.runs.values()].flatMap((run) => {
      const alert = store.alerts.get(run.alert_id)
      return reportArtifactsOf(run.run_id).map((artifact) => ({
        artifact_id: artifact.artifact_id,
        run_id: run.run_id,
        kind: artifact.kind,
        name: artifact.name,
        uri: artifact.uri,
        priority: alert?.priority_level ?? null,
        manufacturer_id: run.manufacturer_id,
        substation_id: run.substation_id,
        substation_uid: run.substation_uid,
        operator_review_status: latestOperatorStatus(run.run_id),
        created_at: artifact.created_at ?? run.created_at ?? new Date(BASE_TIME_MS).toISOString(),
      }))
    })
    const { items, total } = projectionFilter(rows, query, (item) => [item.name, item.manufacturer_id, item.run_id])
    return { items, next_cursor: null, total_count: total }
  },
}

/** mock 초기 시연 데이터 — 실행/작업지시서/보고서 목록이 비지 않게 완료 2·실패 1 run 시드 */
function seedMockAgentRuns(): void {
  const seeds = [
    { runId: 'run-seed-0001', alertId: 'alert-001', offsetMin: 120, status: 'completed' as const, approve: true, daily: false },
    { runId: 'run-seed-0002', alertId: 'alert-002', offsetMin: 60, status: 'completed' as const, approve: false, daily: true },
    { runId: 'run-seed-0003', alertId: 'alert-003', offsetMin: 30, status: 'failed' as const, approve: false, daily: false },
  ]
  for (const seed of seeds) {
    const alert = store.alerts.get(seed.alertId)
    if (!alert) continue
    const createdAt = new Date(BASE_TIME_MS - seed.offsetMin * 60_000).toISOString()
    const complex = complexForAlert(seed.alertId)
    const opsOutput = seed.status === 'completed' && complex ? buildMockOpsOutput(complex) : null
    store.runs.set(seed.runId, {
      run_id: seed.runId,
      status: seed.status,
      input_source: 'alert',
      alert_id: seed.alertId,
      card_id: alert.card_id,
      evaluation_run_id: alert.evaluation_run_id,
      manufacturer_id: alert.manufacturer_id,
      substation_id: alert.substation_id,
      substation_uid: null,
      created_at: createdAt,
      parent_run_id: null,
      trigger_type: 'alert',
      requested_by: 'ops-manager',
      trigger_reason: '알림 기반 자동 분석',
      approved_action_task_id: null,
      agent_mode: seed.status === 'completed' ? 'llm' : null,
      ops_output: opsOutput,
      token_usage: opsOutput ? buildTokenUsage(opsOutput) : null,
      loop_summary: null,
      review_status: 'pending',
      review_task_id: null,
      error: seed.status === 'failed' ? '진단 단계에서 근거 수집에 실패했습니다.' : null,
    })
    if (seed.status === 'completed') {
      const artifacts: AgentRunArtifact[] = [
        { artifact_id: `${seed.runId}-rp`, run_id: seed.runId, kind: 'anomaly_report', name: 'ops_action_report.md', uri: `/artifacts/${seed.runId}/report.md`, created_at: createdAt },
      ]
      if (seed.daily) {
        artifacts.push({ artifact_id: `${seed.runId}-daily`, run_id: seed.runId, kind: 'daily_report', name: 'daily_report.json', uri: `/artifacts/${seed.runId}/daily_report.json`, created_at: createdAt })
      }
      store.artifacts.set(seed.runId, artifacts)
    }
    if (seed.approve) {
      mockOperatorReviews.set(seed.runId, [
        {
          review_id: `${seed.runId}-rv-1`,
          run_id: seed.runId,
          review_version: 1,
          idempotency_key: `${seed.runId}-seed`,
          request_hash: 'mock'.padEnd(64, '0'),
          decision: 'approve',
          reviewer: 'ops-manager',
          reason: '보고 내용이 현장 상황과 일치하여 승인합니다.',
          disposition: 'normal_observation',
          correction: null,
          evidence_annotations: [],
          operator_labels: [],
          created_at: createdAt,
        },
      ])
    }
  }
}

seedMockAgentRuns()
