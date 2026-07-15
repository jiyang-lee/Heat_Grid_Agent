/**
 * mock API ??계약 ?�드?�인?��? in-memory store�?구현.
 * backend.ts가 USE_MOCK????real client ?�???�걸 export?�다.
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
  ReviewChatCancelRequest,
  ReviewChatMessagePage,
  ReviewChatMessageRequest,
  ReviewChatMessageResponse,
  ReviewChatOpenRequest,
  ReviewChatProposalResponse,
  ReviewChatSubmissionResponse,
  ReviewChatThreadResponse,
  ReplayCommandType,
  ReplayDataset,
  ReplayImportRequest,
  ReplayRunCreateRequest,
  ReplayRunCreateResponse,
  ReplayRunCommandRequest,
  ReplayRunCommandResponse,
  ReplayRunSnapshot,
  RunLineageResponse,
  CostBreakdownProjection,
  ModelCallProjection,
  ToolCallProjection,
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
const mockOperatorReviews = new Map<string, OperatorReviewRecord[]>()
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

/** mock 결정??기�? ?�각(mockData BASE_MS?� ?�일 �? */
const BASE_TIME_MS = Date.parse('2026-07-09T09:00:00+09:00')

/** ?��? 9?�계 stage ?�서 ??백엔??STAGE_ORDER?� 1:1 */
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

type MockReviewChatThread = {
  thread: ReviewChatThreadResponse
  messages: ReviewChatMessageResponse[]
  proposals: Map<string, ReviewChatProposalResponse>
}

const mockReviewThreads = new Map<string, MockReviewChatThread>()
let mockReviewMessageSeq = 1
let mockReviewProposalSeq = 1

const mockReplayDatasets: ReplayDataset[] = [
  {
    dataset_id: 'replay-demo-001',
    dataset_version: 'replay-v1',
    status: 'available',
    expected_substations: [1, 2, 3],
    source_interval_seconds: 30,
    window_ticks: 36,
    replay_start: '2026-07-09T00:00:00.000Z',
    replay_end: '2026-07-09T00:18:00.000Z',
    validated_at: '2026-07-09T00:00:00.000Z',
  },
  {
    dataset_id: 'replay-demo-002',
    dataset_version: 'replay-v2',
    status: 'available',
    expected_substations: [4, 5],
    source_interval_seconds: 60,
    window_ticks: 18,
    replay_start: '2026-07-08T23:00:00.000Z',
    replay_end: '2026-07-09T00:00:00.000Z',
    validated_at: null,
  },
]

let mockReplayRunSeq = 1
const mockReplayRuns = new Map<string, ReplayRunSnapshot>()

function buildReplaySnapshot(runId: string, dataset: ReplayDataset): ReplayRunSnapshot {
  return {
    run_id: runId,
    stream_key: `stream-${runId}`,
    state: 'created',
    version: 1,
    current_simulated_at: dataset.replay_start,
    last_emitted_sequence: 0,
    last_scored_window_end: null,
    last_evaluation_run_id: null,
    speed_multiplier: 1,
    tick_seconds: dataset.source_interval_seconds,
    dataset_version: dataset.dataset_version,
    window_ticks: dataset.window_ticks,
    last_event_id: 0,
    window_progress: 0,
    synthetic: true,
    readings: [],
  }
}

function snapshotToReading(runId: string, seq: number, at: string): ReplayRunSnapshot['readings'][number] {
  return {
    manufacturer_id: `manufacturer ${((seq % 3) + 1)}`,
    substation_id: ((seq % 5) + 1),
    sequence: seq,
    simulated_at: at,
    values: {
      generator_temperature_c: 22 + (seq % 7),
      feeder_load_kw: 400 + seq * 3,
      anomaly_score: Number(((seq * 0.97) % 10 / 10).toFixed(2)),
      requested_by: 'ops-console',
      run_id: runId,
    },
    quality: null,
  }
}

function createReviewThread(runId: string): ReviewChatThreadResponse {
  const thread: ReviewChatThreadResponse = {
    thread_id: `thread-${runId}`,
    run_id: runId,
    status: 'open',
    context_hash: `ctx-${runId}`,
    base_review_version: 1,
    created_at: new Date().toISOString(),
  }
  const welcome: ReviewChatMessageResponse = {
    message_id: `msg-${mockReviewMessageSeq++}`,
    thread_id: thread.thread_id,
    sequence: 1,
    role: 'system_event',
    message_kind: 'explanation',
    content: `Review chat mock thread opened for run ${runId}.`,
    structured_payload: {},
    citations: [],
    context_hash: thread.context_hash,
    created_at: new Date().toISOString(),
  }
  mockReviewThreads.set(runId, { thread, messages: [welcome], proposals: new Map() })
  return thread
}

/** ??'?��??�류' ?�안 ?�치(3�? ?�현??검???��?문서. run ?�성 ????task가 ?�에 ?�인?? */
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


/** 백엔??목록 projection�??�일 규칙: reject??ELSE 분기??pending?�로 ?�영?�다. */
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
    if (!alert) throw new ApiError(404, '/agent-runs', 'alert_id�?찾을 ???�습?�다.')
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
      { artifact_id: `${runId}-ev`, run_id: runId, kind: 'evidence', name: `evidence_${alert.card_id}.json`, uri: `/artifacts/${runId}/evidence.json`, created_at: run.created_at },
      { artifact_id: `${runId}-rp`, run_id: runId, kind: 'anomaly_report', name: 'ops_action_report.md', uri: `/artifacts/${runId}/report.md`, created_at: run.created_at },
    ])
    mockReviewTasks.unshift({
      task_id: `${runId}-review`,
      task_type: 'final_output',
      status: 'pending',
      risk_level: alert.priority_level === 'urgent' ? 'critical' : 'high',
      title: `?�이?�트 최종 ?�영 결과 검?? ${alert.card_id}`,
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
    if (!r) throw new ApiError(404, `/agent-runs/${runId}`, 'run_id�?찾을 ???�습?�다.')
    return r
  },
  async review(runId: string): Promise<AgentRunReviewSnapshotResponse> {
    await delay(100)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/review`, 'run_id�?찾을 ???�습?�다.')
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
            { sequence: 1, decision: 'collect_evidence', reason: '?�선?�위 카드?� ?��? 근거�??�집?�습?�다.' },
            { sequence: 2, decision: 'finalize', reason: '?�집 근거가 충분?�여 최종 보고�??�정?�습?�다.' },
          ],
          loop_count: r.loop_summary?.iterations ?? 0,
          handling_reason: r.ops_output?.summary ?? '?�료???�행?�니??',
          diagnostic: {
            trigger: null,
            status: 'completed',
            hypotheses: [
              {
                hypothesis_id: `${runId}-hyp-1`,
                title: '?�교?�기 2차측 ?��???감소 가?�성',
                rationale: '공급?�도 ?�락�??�량 변?��? ?�시??관측되??2차측 부??변?�을 ?�선 검?�합?�다.',
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
            reason: '?�???�수?� ?�계???�수가 ?�치?�니??',
          },
          weather: {
            status: 'available',
            observed_at: r.created_at,
            temperature_c: 26.1,
            humidity_percent: 78,
            precipitation_mm: 2.1,
            wind_speed_mps: 1.4,
            provenance: { source: 'KMA 관�?mock)', source_owner: 'kma', snapshot_id: null, retrieval_id: null, document_id: null, chunk_id: null, error_type: null, message: null },
          },
          evidence: [
            {
              evidence_id: `${runId}-ev-1`,
              document_type: 'internal_rag',
              source_owner: 'ops',
              source: '?��? ?�영 문서(mock)',
              title: '?�교?�기 ?�량 ?�승 ?�???��?',
              section: '조치 ?�차',
              score: 0.87,
              excerpt: '2차측 ?�량 증�??� 공급?�도 ?�락???�반?�면 ?�교?�기 ?�결부 ?��????�선?�다.',
              provenance: { source: 'internal(mock)', source_owner: 'ops', snapshot_id: null, retrieval_id: null, document_id: 'R-021', chunk_id: null, error_type: null, message: null },
            },
            {
              evidence_id: `${runId}-ev-2`,
              document_type: 'operator_manual_evidence',
              source_owner: 'operator',
              source: '?�영 ?�트(mock)',
              title: '?�장 ?�림 밸브 ?�인 기록',
              section: null,
              score: 0.8,
              excerpt: '보충??밸브 ?�정 변�??�력???�어 ?�장 ?�인???�요?�다.',
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
            reason: alert?.enqueue_reason ?? 'Alert review reason generated from the source card',
          },
          budget: { parent_token_limit: 60000, parent_tokens_used: 4200, diagnostic_token_limit: 3000, diagnostic_tokens_used: 1520 },
          checkpoint: { thread_id: runId, namespace: 'mock', checkpoint_id: null, durability: 'sync' },
        }
        : null,
      created_at: r.status === 'completed' ? r.created_at : null,
      unavailable_reason: r.status === 'completed' ? null : '?�행???�직 ?�료?��? ?�았?�니??',
    }
  },
  /** 9?�계 stage snapshot projection ???�료 run?� ???�계 passed�?결정??구성 */
  async stages(runId: string): Promise<StageProjectionResponse> {
    await delay(80)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/stages`, 'run_id�?찾을 ???�습?�다.')
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
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/result`, 'run_id�?찾을 ???�습?�다.')
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
        { label: '?�영 근거', content: 'mock priority card evidence', source: 'manual' },
      ],
      actions: [{ priority: 1, title: '권장 조치', detail: output.action_plan }],
      cautions: [output.caution],
      report: {
        title: 'Summary report',
        format: 'markdown',
        content: `# Daily operations summary
## Recommended action
${output.summary}
## Action plan
${output.action_plan}

## Cautions
${output.caution}
`,
      },
    }
  },
  async artifacts(runId: string): Promise<AgentRunArtifact[]> {
    await delay(150)
    if (!store.runs.has(runId)) throw new ApiError(404, `/agent-runs/${runId}/artifacts`, 'run_id�?찾을 ???�습?�다.')
    return store.artifacts.get(runId) ?? []
  },
  async dailyReport(runId: string, _body: AgentReportCreateRequest): Promise<AgentRunArtifact> {
    await delay(400)
    if (!store.runs.has(runId)) throw new ApiError(404, `/agent-runs/${runId}`, 'run_id�?찾을 ???�습?�다.')
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
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/iterations`, 'run_id�?찾을 ???�습?�다.')
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

export const reviewTasksApi = {
  async list(query?: { status?: string; task_type?: string }): Promise<HumanReviewTask[]> {
    await delay(80)
    return mockReviewTasks.filter(
      (task) => (!query?.status || task.status === query.status) && (!query?.task_type || task.task_type === query.task_type),
    )
  },
  async get(taskId: string): Promise<HumanReviewTask> {
    const task = mockReviewTasks.find((item) => item.task_id === taskId)
    if (!task) throw new ApiError(404, `/review-tasks/${taskId}`, 'task_id�?찾을 ???�습?�다.')
    return task
  },
  async submit(taskId: string, body: ReviewTaskSubmitRequest): Promise<ReviewSubmitResponse> {
    await delay(100)
    const task = mockReviewTasks.find((item) => item.task_id === taskId)
    if (!task) throw new ApiError(404, `/review-tasks/${taskId}`, 'task_id�?찾을 ???�습?�다.')
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
    if (!item) throw new ApiError(404, `/evidence-candidates/${candidateId}`, 'candidate_id�?찾을 ???�습?�다.')
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
    if (!job) throw new ApiError(404, `/retrain-jobs/${jobId}`, 'job_id�?찾을 ???�습?�다.')
    job.status = 'approved'
    job.approved_by = body.reviewer
    job.approved_at = new Date().toISOString()
    return job
  },
  async reject(jobId: string, body: RetrainJobActionRequest): Promise<RetrainJob> {
    const job = mockRetrainJobs.find((item) => item.job_id === jobId)
    if (!job) throw new ApiError(404, `/retrain-jobs/${jobId}`, 'job_id�?찾을 ???�습?�다.')
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
    if (!candidate) throw new ApiError(404, `/model-candidates/${candidateId}`, 'candidate_id�?찾을 ???�습?�다.')
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

export const reviewChatApi = {
  async open(runId: string, body: ReviewChatOpenRequest): Promise<ReviewChatThreadResponse> {
    await delay(80)
    const run = store.runs.get(runId)
    if (!run) throw new ApiError(404, `/agent-runs/${runId}/review-chat/threads`, 'run_id is not found')
    if (!body.created_by) throw new ApiError(400, `/agent-runs/${runId}/review-chat/threads`, 'created_by is required')
    const existing = mockReviewThreads.get(runId)
    if (existing) return existing.thread
    return createReviewThread(runId)
  },
  async messages(threadId: string): Promise<ReviewChatMessagePage> {
    await delay(70)
    const run = [...mockReviewThreads.values()].find((item) => item.thread.thread_id === threadId)
    if (!run) throw new ApiError(404, `/review-chat/threads/${threadId}/messages`, 'thread_id is not found')
    return { items: run.messages }
  },
  async postMessage(threadId: string, body: ReviewChatMessageRequest): Promise<ReviewChatSubmissionResponse> {
    await delay(120)
    const state = [...mockReviewThreads.values()].find((item) => item.thread.thread_id === threadId)
    if (!state) throw new ApiError(404, `/review-chat/threads/${threadId}/messages`, 'thread_id is not found')
    const operatorMessage: ReviewChatMessageResponse = {
      message_id: `msg-${mockReviewMessageSeq++}`,
      thread_id: threadId,
      sequence: state.messages.length + 1,
      role: 'operator',
      message_kind: 'question',
      content: body.content,
      structured_payload: {},
      citations: [],
      context_hash: state.thread.context_hash,
      created_at: new Date().toISOString(),
    }
    state.messages.push(operatorMessage)
    const assistantMessage: ReviewChatMessageResponse = {
      message_id: `msg-${mockReviewMessageSeq++}`,
      thread_id: threadId,
      sequence: state.messages.length + 1,
      role: 'assistant',
      message_kind: 'explanation',
      content: `?�청 메시지�??�인?�습?�다: ${body.content}`,
      structured_payload: {},
      citations: [],
      context_hash: state.thread.context_hash,
      created_at: new Date().toISOString(),
    }
    state.messages.push(assistantMessage)
    let proposal: ReviewChatProposalResponse | null = null
    if (body.content.toLowerCase().includes('proposal') || body.content.includes('?�안')) {
      const proposalId = `proposal-${mockReviewProposalSeq++}`
      proposal = {
        proposal_id: proposalId,
        thread_id: threadId,
        run_id: state.thread.run_id,
        expected_review_version: state.thread.base_review_version,
        context_hash: state.thread.context_hash,
        status: 'awaiting_confirmation',
        decision: 'approve',
        next_action: 'manual_investigation',
        reason: body.content.slice(0, 120),
        reason_category: null,
        disposition: null,
        correction: null,
        target_stage: 'report_fidelity',
        expires_at: new Date(Date.now() + 1000 * 60 * 30).toISOString(),
      }
      state.proposals.set(proposalId, proposal)
    }
    return { operator_message: operatorMessage, assistant_message: assistantMessage, proposal }
  },
  async confirmProposal(
    proposalId: string,
    _body: { confirmed_by: string; idempotency_key: string; expected_proposal_status: 'awaiting_confirmation'; expected_review_version: number },
  ): Promise<ReviewChatProposalResponse> {
    await delay(80)
    const state = [...mockReviewThreads.values()].find((item) => item.proposals.has(proposalId))
    if (!state) throw new ApiError(404, `/review-chat/proposals/${proposalId}/confirm`, 'proposal_id is not found')
    const proposal = state.proposals.get(proposalId)
    if (!proposal) throw new ApiError(404, `/review-chat/proposals/${proposalId}/confirm`, 'proposal_id is not found')
    state.proposals.set(proposalId, { ...proposal, status: 'confirmed' })
    return state.proposals.get(proposalId)!
  },
  async cancelProposal(
    proposalId: string,
    _body: ReviewChatCancelRequest,
  ): Promise<ReviewChatProposalResponse> {
    await delay(80)
    const state = [...mockReviewThreads.values()].find((item) => item.proposals.has(proposalId))
    if (!state) throw new ApiError(404, `/review-chat/proposals/${proposalId}/cancel`, 'proposal_id is not found')
    const proposal = state.proposals.get(proposalId)
    if (!proposal) throw new ApiError(404, `/review-chat/proposals/${proposalId}/cancel`, 'proposal_id is not found')
    state.proposals.set(proposalId, { ...proposal, status: 'cancelled' })
    return state.proposals.get(proposalId)!
  },
}

export const replayApi = {
  async listDatasets(): Promise<ReplayDataset[]> {
    await delay(100)
    return mockReplayDatasets
  },
  async importDataset(body: ReplayImportRequest): Promise<ReplayDataset> {
    await delay(180)
    if (!body.package_path.trim()) throw new ApiError(400, '/replay-datasets/import', 'package_path is required')
    const datasetId = `replay-imported-${mockReplayDatasets.length + 1}`
    const start = new Date().toISOString()
    const dataset: ReplayDataset = {
      dataset_id: datasetId,
      dataset_version: 'imported',
      status: 'imported',
      expected_substations: [1, 2, 3],
      source_interval_seconds: 30,
      window_ticks: 24,
      replay_start: start,
      replay_end: new Date(Date.now() + 60_000 * 24).toISOString(),
      validated_at: new Date().toISOString(),
    }
    mockReplayDatasets.unshift(dataset)
    return dataset
  },
  async createRun(body: ReplayRunCreateRequest): Promise<ReplayRunCreateResponse> {
    await delay(150)
    const dataset = mockReplayDatasets.find((item) => item.dataset_id === body.dataset_id)
    if (!dataset) throw new ApiError(404, '/replay-runs', 'dataset_id is not found')
    const runId = `replay-run-${String(mockReplayRunSeq++).padStart(4, '0')}`
    const snapshot = buildReplaySnapshot(runId, dataset)
    mockReplayRuns.set(runId, snapshot)
    return { run_id: runId, stream_key: snapshot.stream_key, state: snapshot.state, version: snapshot.version }
  },
  async snapshot(runId: string): Promise<ReplayRunSnapshot> {
    await delay(90)
    const snapshot = mockReplayRuns.get(runId)
    if (!snapshot) throw new ApiError(404, `/replay-runs/${runId}/snapshot`, 'run_id is not found')
    if (snapshot.state === 'running') {
      const nextSeq = (snapshot.last_emitted_sequence ?? 0) + 1
      const tick = snapshot.tick_seconds
      const baseline = snapshot.current_simulated_at ?? new Date().toISOString()
      snapshot.last_emitted_sequence = nextSeq
      snapshot.window_progress = Math.min(100, Number(((nextSeq / snapshot.window_ticks) * 100).toFixed(2)))
      snapshot.last_event_id = nextSeq
      const current = new Date(Date.parse(baseline) + nextSeq * tick * 1000).toISOString()
      snapshot.current_simulated_at = current
      const reading = snapshotToReading(runId, nextSeq, current)
      snapshot.readings = [reading, ...snapshot.readings].slice(0, 20)
      return { ...snapshot }
    }
    return { ...snapshot }
  },
  async command(runId: string, body: ReplayRunCommandRequest): Promise<ReplayRunCommandResponse> {
    await delay(120)
    const snapshot = mockReplayRuns.get(runId)
    if (!snapshot) throw new ApiError(404, `/replay-runs/${runId}/commands`, 'run_id is not found')
    const version = Number(body.expected_run_version ?? snapshot.version)
    if (snapshot.version !== version) {
      throw new ApiError(409, `/replay-runs/${runId}/commands`, 'run version mismatch')
    }
    snapshot.version = version + 1
    switch (body.command_type) {
      case 'start':
      case 'resume':
        snapshot.state = 'running'
        if (!snapshot.current_simulated_at) snapshot.current_simulated_at = new Date().toISOString()
        break
      case 'pause':
        snapshot.state = 'paused'
        break
      case 'reset':
        snapshot.state = 'created'
        snapshot.current_simulated_at = null
        snapshot.last_emitted_sequence = 0
        snapshot.window_progress = 0
        snapshot.last_event_id = 0
        snapshot.readings = []
        break
      case 'seek':
        if (typeof body.payload?.target_at === 'string') {
          snapshot.current_simulated_at = body.payload.target_at
        } else if (typeof body.payload?.target_simulated_at === 'string') {
          snapshot.current_simulated_at = body.payload.target_simulated_at
        }
        break
      case 'set_speed':
        if (typeof body.payload?.speed_multiplier === 'number') {
          snapshot.speed_multiplier = body.payload.speed_multiplier
        }
        break
      case 'cancel':
        snapshot.state = 'cancelled'
        break
      default:
        throw new ApiError(400, `/replay-runs/${runId}/commands`, 'command type is invalid')
    }
    snapshot.last_scored_window_end = snapshot.current_simulated_at
    return { command_id: `replay-command-${runId}-${snapshot.version}`, status: snapshot.state }
  },
}

export const agentQualityApi = {
  async lineage(runId: string): Promise<RunLineageResponse> {
    await delay(90)
    const run = store.runs.get(runId)
    if (!run) throw new ApiError(404, `/agent-runs/${runId}/rerun-lineage`, 'run_id is not found')
    const ancestors: RunLineageResponse['ancestors'] = []
    let cursor = run
    let depth = 0
    while (cursor.parent_run_id) {
      const parent = store.runs.get(cursor.parent_run_id)
      if (!parent) break
      ancestors.push({
        run_id: parent.run_id,
        parent_run_id: parent.parent_run_id,
        root_run_id: parent.parent_run_id ?? null,
        lineage_depth: depth,
        status: parent.status,
        target_stage: 'report_fidelity',
      })
      cursor = parent
      depth += 1
    }
    return {
      root_run_id: cursor.run_id,
      current_run_id: run.run_id,
      depth,
      ancestors: ancestors.reverse(),
      children: [],
      requests: [],
    }
  },
  async modelCalls(runId: string): Promise<ModelCallProjection[]> {
    await delay(90)
    const run = store.runs.get(runId)
    if (!run) throw new ApiError(404, `/agent-runs/${runId}/model-calls`, 'run_id is not found')
    return [
      {
        model_call_id: `${runId}-mc-01`,
        stage_name: 'rag_retrieval',
        stage_attempt: 1,
        execution_profile: 'mock-profile',
        status: run.status,
        snapshot_bundle_hash: `${runId}-snapshot`,
        allowed_tools: ['get_ops_evidence', 'rag_lookup'],
        actual_tool_calls: 2,
        actual_model_turns: 3,
        input_tokens: run.token_usage?.input_tokens ?? 100,
        output_tokens: run.token_usage?.output_tokens ?? 40,
        total_tokens: run.token_usage?.total_tokens ?? 140,
      },
    ]
  },
  async toolCalls(runId: string): Promise<ToolCallProjection[]> {
    await delay(90)
    const run = store.runs.get(runId)
    if (!run) throw new ApiError(404, `/agent-runs/${runId}/tool-calls`, 'run_id is not found')
    return [
      {
        tool_call_id: `${runId}-tc-01`,
        model_call_id: `${runId}-mc-01`,
        stage_name: 'rag_retrieval',
        tool_name: 'get_ops_evidence',
        status: run.status,
        call_sequence: 1,
      },
      {
        tool_call_id: `${runId}-tc-02`,
        model_call_id: `${runId}-mc-01`,
        stage_name: 'fault_analysis',
        tool_name: 'model_decision_support',
        status: run.status,
        call_sequence: 2,
      },
    ]
  },
  async cost(runId: string): Promise<CostBreakdownProjection> {
    await delay(90)
    const run = store.runs.get(runId)
    if (!run) throw new ApiError(404, `/agent-runs/${runId}/cost-breakdown`, 'run_id is not found')
    return {
      run_id: runId,
      model_call_count: 2,
      tool_call_count: 2,
      input_tokens: run.token_usage?.input_tokens ?? 0,
      output_tokens: run.token_usage?.output_tokens ?? 0,
      total_tokens: run.token_usage?.total_tokens ?? 0,
    }
  },
}

/** mock SSE ???�제 EventSource ?�???�?�머�?계약 ?�벤?��? 방출. */
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

/* ===== AI ?�동 ???�업지?�서/보고??projection mock ===== */

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

/** mock 초기 ?�연 ?�이?????�행/?�업지?�서/보고??목록??비�? ?�게 ?�료 2·?�패 1 run ?�드 */
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
      trigger_reason: '?�림 기반 ?�동 분석',
      approved_action_task_id: null,
      agent_mode: seed.status === 'completed' ? 'llm' : null,
      ops_output: opsOutput,
      token_usage: opsOutput ? buildTokenUsage(opsOutput) : null,
      loop_summary: null,
      review_status: 'pending',
      review_task_id: null,
      error: seed.status === 'failed' ? '진단 ?�계?�서 근거 ?�집???�패?�습?�다.' : null,
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
          reason: '보고 ?�용???�장 ?�황�??�치?�여 ?�인?�니??',
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
