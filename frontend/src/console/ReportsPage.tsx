import { useState } from 'react'
import { API_BASE, ApiError } from '../api/client'
import type {
  AgentRunArtifact,
  AgentRunListItem,
  AgentRunStatus,
  CitationCoverage,
  EvidenceCompleteness,
  InputValidity,
  OperatorReviewDecision,
  OperatorReviewDisposition,
  OperatorReviewStatus,
  ParentHandling,
  ReviewSnapshotStatus,
  WorkerStatus,
} from '../api/contracts'
import {
  useAgentIterations,
  useAgentRun,
  useAgentRunEvaluation,
  useAgentRunReviewSnapshot,
  useAgentRuns,
  useAgentRunResult,
  useArtifacts,
  useGenerateDailyReport,
  useOperatorReviews,
  useSubmitOperatorReview,
  useSubmitReviewTask,
} from '../api/hooks'
import { complexNameOf } from '../domain/model'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from './ui'

type ActivityTab = 'runs' | 'reports' | 'orders'

interface Props {
  readonly runId: string | null
  readonly onOpenAlerts: () => void
  readonly onSelectRun: (runId: string) => void
}

function runTone(status: AgentRunStatus): Tone {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'critical'
  return 'primary'
}

function artifactUrl(artifact: AgentRunArtifact): string {
  return `${API_BASE}/agent-runs/${encodeURIComponent(artifact.run_id)}/artifacts/${encodeURIComponent(artifact.artifact_id)}/content`
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

const operatorReviewLabels: Record<OperatorReviewStatus, string> = {
  pending: '검토 대기',
  approved: '승인',
  corrected: '수정',
  keep_human_review: '사람 검토',
}

const workerStatusLabels: Record<WorkerStatus, string> = {
  not_triggered: '대기',
  running: '실행 중',
  completed: '완료',
  failed: '실패',
  timeout: '시간 초과',
  invalid: '무효',
  budget_exceeded: '예산 초과',
}

const runStatusLabels: Record<AgentRunStatus, string> = {
  queued: '대기',
  running: '진행 중',
  completed: '완료',
  failed: '실패',
}

function reviewSnapshotTone(status: ReviewSnapshotStatus): Tone {
  if (status === 'available') return 'success'
  if (status === 'legacy_unavailable' || status === 'unavailable') return 'warning'
  return 'neutral'
}

/* ===== v3-02 라벨 매핑 ===== */

const citationLabels: Record<CitationCoverage, string> = {
  complete: '완전', partial: '부분', missing: '없음', not_applicable: '해당 없음',
}
const validityLabels: Record<InputValidity, string> = {
  valid: '유효', invalid: '무효', unavailable: '확인 불가',
}
const parentHandlingLabels: Record<ParentHandling, string> = {
  used_as_support: '근거로 사용', invalid: '무효 처리', unavailable: '확인 불가', fallback_to_human: '사람 검토 전환',
}
const completenessLabels: Record<EvidenceCompleteness, string> = {
  complete: '완전', partial: '부분', missing: '없음',
}
const decisionLabels: Record<OperatorReviewDecision, string> = {
  approve: '승인', correct: '교정', keep_human_review: '사람 검토 유지',
}
const dispositionLabels: Record<OperatorReviewDisposition, string> = {
  normal_observation: '정상 관찰', inspection_recommended: '점검 권장', urgent_review: '긴급 검토',
}

function decisionTone(decision: OperatorReviewDecision): Tone {
  if (decision === 'approve') return 'success'
  if (decision === 'correct') return 'warning'
  return 'primary'
}

/** v3-02 결정적 품질 평가 projection — GET /api/agent-run-evaluations?run_id= */
function EvaluationCard({ runId }: { readonly runId: string }) {
  const { data, isError, isLoading, refetch } = useAgentRunEvaluation(runId)
  return <SurfaceCard title="v3-02 품질 평가">
    <ApiState empty={data === null && !isLoading} error={isError} loading={isLoading} retry={() => void refetch()} />
    {data && <div className="detail-body"><div className="run-metrics">
      <span>인용 커버리지 <strong>{citationLabels[data.citation_coverage]}</strong></span>
      <span>입력 유효성 <strong>{validityLabels[data.input_validity]}</strong></span>
      <span>AI 판단 처리 <strong>{parentHandlingLabels[data.parent_handling]}</strong></span>
      <span>근거 완전성 <strong>{completenessLabels[data.evidence_completeness]}</strong></span>
      <span>운영자 검토 <strong>{operatorReviewLabels[data.operator_review_status]}</strong></span>
      <span>worker <strong>{workerStatusLabels[data.worker_status]}</strong></span>
    </div></div>}
  </SurfaceCard>
}

/** v3-02 운영자 검토 — POST /api/agent-runs/{id}/reviews (append) + 이력 조회 */
function OperatorReviewCard({ runId }: { readonly runId: string }) {
  const history = useOperatorReviews(runId)
  const submit = useSubmitOperatorReview()
  const [decision, setDecision] = useState<OperatorReviewDecision>('approve')
  const [disposition, setDisposition] = useState<OperatorReviewDisposition>('inspection_recommended')
  const [reason, setReason] = useState('')
  const [correctionSummary, setCorrectionSummary] = useState('')
  const items = history.data?.items ?? []
  const latestVersion = items.at(-1)?.review_version ?? 0
  const stale = submit.isError && submit.error instanceof ApiError && submit.error.status === 409

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!reason.trim() || submit.isPending) return
    submit.mutate(
      {
        runId,
        body: {
          expected_review_version: latestVersion,
          idempotency_key: crypto.randomUUID(),
          decision,
          reviewer: 'ops-manager',
          reason: reason.trim(),
          disposition,
          correction: decision === 'correct' && correctionSummary.trim() ? { summary: correctionSummary.trim() } : null,
        },
      },
      { onSuccess: () => { setReason(''); setCorrectionSummary('') } },
    )
  }

  return <SurfaceCard action={<span className="count-chip">검토 {items.length}건 · v{latestVersion}</span>} title="운영자 검토 (v3-02)">
    <form className="review-form" onSubmit={onSubmit}>
      <div className="review-fields">
        <label>판정<select onChange={(event) => setDecision(event.target.value as OperatorReviewDecision)} value={decision}>{(Object.keys(decisionLabels) as OperatorReviewDecision[]).map((value) => <option key={value} value={value}>{decisionLabels[value]}</option>)}</select></label>
        <label>처분<select onChange={(event) => setDisposition(event.target.value as OperatorReviewDisposition)} value={disposition}>{(Object.keys(dispositionLabels) as OperatorReviewDisposition[]).map((value) => <option key={value} value={value}>{dispositionLabels[value]}</option>)}</select></label>
      </div>
      {decision === 'correct' && <label>교정 내용<input onChange={(event) => setCorrectionSummary(event.target.value)} placeholder="AI 판단에서 바로잡을 내용" value={correctionSummary} /></label>}
      <label>사유<textarea onChange={(event) => setReason(event.target.value)} placeholder="검토 판단의 근거를 남겨 주세요 (append-only 기록)" required value={reason} /></label>
      <Button disabled={submit.isPending || !reason.trim()} tone="primary" type="submit">{submit.isPending ? '기록 중' : `${decisionLabels[decision]} 기록`}</Button>
      {stale && <p className="form-error">다른 검토가 먼저 기록되었습니다(409). 이력을 새로고침한 뒤 다시 시도해 주세요.</p>}
      {submit.isError && !stale && <p className="form-error">검토를 기록하지 못했습니다. 실행 상태를 확인해 주세요.</p>}
    </form>
    <ApiState empty={items.length === 0 && !history.isLoading} error={history.isError} loading={history.isLoading} retry={() => void history.refetch()} />
    {items.length > 0 && <ol className="review-history">{[...items].reverse().map((item) => <li key={item.review_id}><header><StatusBadge tone={decisionTone(item.decision)}>{decisionLabels[item.decision]}</StatusBadge><strong>v{item.review_version} · {item.reviewer}</strong><time>{formatDateTime(item.created_at)}</time></header><span>{item.reason}</span>{item.correction?.summary && <small>교정: {item.correction.summary}</small>}</li>)}</ol>}
  </SurfaceCard>
}

function reviewSnapshotTitle(status: ReviewSnapshotStatus): string {
  if (status === 'available') return '검토 스냅샷 사용 가능'
  if (status === 'legacy_unavailable') return '레거시 실행: 캡처 없음'
  if (status === 'unavailable') return '검토 스냅샷 없음'
  return '검토 스냅샷 대기'
}

function RunList({ selectedRunId, onSelectRun }: { readonly selectedRunId: string | null; readonly onSelectRun: (runId: string) => void }) {
  const runs = useAgentRuns()
  const rows = runs.data?.items ?? []
  return <SurfaceCard title="최근 AI 실행 목록"><ApiState empty={rows.length === 0} error={runs.isError} loading={runs.isLoading} retry={() => void runs.refetch()} />{rows.length > 0 && <div className="table-scroll"><table className="ops-table"><thead><tr><th>실행</th><th>상태</th><th>검토</th><th>스냅샷</th><th>생성</th><th>선택</th></tr></thead><tbody>{rows.map((item: AgentRunListItem) => <tr className={selectedRunId === item.run_id ? 'selected-row' : ''} key={item.run_id}><td><strong>{item.card_id}</strong><small>{item.run_id}</small></td><td><StatusBadge tone={runTone(item.status)}>{runStatusLabels[item.status]}</StatusBadge><small>worker {workerStatusLabels[item.worker_status]}</small></td><td><strong>{operatorReviewLabels[item.operator_review_status]}</strong><small>{item.priority ?? 'priority 없음'}</small></td><td><StatusBadge tone={reviewSnapshotTone(item.review_snapshot_status)}>{item.review_snapshot_status}</StatusBadge></td><td>{formatDateTime(item.created_at)}</td><td><Button disabled={selectedRunId === item.run_id} onClick={() => onSelectRun(item.run_id)}>{selectedRunId === item.run_id ? '선택됨' : '열기'}</Button></td></tr>)}</tbody></table></div>}</SurfaceCard>
}

function NoRun({ onOpenAlerts, onSelectRun }: { readonly onOpenAlerts: () => void; readonly onSelectRun: (runId: string) => void }) {
  return <div className="activity-stack"><div className="activity-empty"><h2>아직 선택된 AI 실행이 없습니다.</h2><p>알림에서 실제 AI 분석을 시작하거나, 아래 최근 실행 목록에서 기존 실행을 선택하면 보고서와 작업지시서가 연결됩니다.</p><Button onClick={onOpenAlerts} tone="primary">알림에서 AI 분석 시작</Button></div><RunList onSelectRun={onSelectRun} selectedRunId={null} /></div>
}

function RunProgress({ runId, onSelectRun }: { readonly runId: string; readonly onSelectRun: (runId: string) => void }) {
  const run = useAgentRun(runId)
  const review = useAgentRunReviewSnapshot(runId)
  const iterations = useAgentIterations(runId)
  const phases = ['알림 감지', '데이터 수집', 'AI 판단', '보고서 생성', '작업지시서 초안', '완료']
  const completed = run.data?.status === 'completed' ? phases.length : Math.min(4, Math.max(1, (iterations.data?.length ?? 0) + 2))
  return <div className="activity-stack"><RunList onSelectRun={onSelectRun} selectedRunId={runId} /><SurfaceCard title="선택된 AI 실행"><ApiState empty={false} error={run.isError} loading={run.isLoading} retry={() => void run.refetch()} />{run.data && <div className="detail-body"><div className="detail-title"><StatusBadge tone={runTone(run.data.status)}>{runStatusLabels[run.data.status]}</StatusBadge><h2>{complexNameOf(run.data.substation_id, run.data.manufacturer_id)} · 기계실 {run.data.substation_id ?? '-'}</h2><p>실행 ID {run.data.run_id} · 요청자 {run.data.requested_by ?? '운영자'}</p></div><div className="run-steps">{phases.map((phase, index) => <div className={index < completed ? 'complete' : index === completed ? 'active' : ''} key={phase}><b>{index + 1}</b><span>{phase}</span></div>)}</div><div className="run-metrics"><span>모드 <strong>{run.data.agent_mode ?? '대기'}</strong></span><span>검토 상태 <strong>{run.data.review_status}</strong></span><span>모델 호출 <strong>{run.data.token_usage?.model_calls ?? 0}회</strong></span><span>토큰 <strong>{run.data.token_usage?.total_tokens.toLocaleString() ?? 0}</strong></span></div>{run.data.error && <p className="form-error">{run.data.error}</p>}</div>}</SurfaceCard><SurfaceCard title="v3-01 검토 캡처"><ApiState empty={false} error={review.isError} loading={review.isLoading} retry={() => void review.refetch()} />{review.data && <div className="detail-body"><div className="detail-title"><StatusBadge tone={reviewSnapshotTone(review.data.status)}>{review.data.status}</StatusBadge><h2>{review.data.schema_version ?? reviewSnapshotTitle(review.data.status)}</h2><p>{review.data.unavailable_reason ?? review.data.snapshot?.handling_reason ?? '이 실행은 v3-01 캡처 저장 이전에 생성되어 스냅샷 본문이 없습니다.'}</p></div><div className="run-metrics"><span>진단 상태 <strong>{review.data.snapshot ? workerStatusLabels[review.data.snapshot.diagnostic.status] : '-'}</strong></span><span>루프 <strong>{review.data.snapshot?.loop_count ?? 0}회</strong></span><span>근거 <strong>{review.data.snapshot?.evidence.length ?? 0}건</strong></span><span>해시 <strong>{review.data.snapshot_hash?.slice(0, 12) ?? '-'}</strong></span></div></div>}</SurfaceCard><EvaluationCard runId={runId} /><OperatorReviewCard runId={runId} /><SurfaceCard title="실행 단계 로그"><ApiState empty={false} error={iterations.isError} loading={iterations.isLoading} retry={() => void iterations.refetch()} />{iterations.data && <ol className="activity-log">{iterations.data.length > 0 ? iterations.data.map((item) => <li key={item.iteration_id}><strong>{item.phase}</strong><span>{item.decision}</span><small>신뢰도 {(item.confidence * 100).toFixed(0)}% · 근거 {(item.evidence_score * 100).toFixed(0)}%</small></li>) : <li><span>백엔드가 실행 단계를 기록하는 중입니다.</span></li>}</ol>}</SurfaceCard></div>
}

function ReportPanel({ runId }: { readonly runId: string }) {
  const result = useAgentRunResult(runId)
  const artifacts = useArtifacts(runId)
  const generate = useGenerateDailyReport()
  return <div className="activity-stack"><SurfaceCard action={<Button disabled={generate.isPending || result.isLoading || result.isError} icon="document" onClick={() => generate.mutate({ runId, requestedBy: 'ops-manager' })} tone="primary">{generate.isPending ? '실제 보고서 저장 중' : '실제 보고서 파일 생성'}</Button>} title="AI 보고서"><ApiState empty={false} error={result.isError} loading={result.isLoading} retry={() => void result.refetch()} />{result.data && <article className="agent-report"><div><StatusBadge tone="critical">AI 분석 보고서</StatusBadge><h2>{result.data.report.title}</h2><p>{result.data.headline}</p></div><section><h3>상황 요약</h3><p>{result.data.situation}</p></section><section><h3>권장 조치</h3><ol>{result.data.actions.map((action) => <li key={action.priority}><strong>{action.title}</strong><span>{action.detail}</span></li>)}</ol></section><section><h3>주의 사항</h3><ul>{result.data.cautions.map((caution) => <li key={caution}>{caution}</li>)}</ul></section><details><summary>원본 Markdown 보고서 보기</summary><pre>{result.data.report.content}</pre></details></article>}{generate.isError && <p className="form-error">보고서 파일을 저장하지 못했습니다. 완료된 실행만 저장할 수 있습니다.</p>}</SurfaceCard><SurfaceCard title="서버에 저장된 문서"><ApiState empty={false} error={artifacts.isError} loading={artifacts.isLoading} retry={() => void artifacts.refetch()} />{artifacts.data && <ul className="artifact-list">{artifacts.data.length > 0 ? artifacts.data.map((artifact) => <li key={artifact.artifact_id}><span><strong>{artifact.name}</strong><small>{artifact.kind}</small></span><a href={artifactUrl(artifact)} rel="noreferrer" target="_blank">열기</a></li>) : <li>생성된 문서가 없습니다. 위 버튼으로 실제 JSON 보고서를 저장할 수 있습니다.</li>}</ul>}</SurfaceCard></div>
}

function WorkOrderPanel({ runId }: { readonly runId: string }) {
  const run = useAgentRun(runId)
  const result = useAgentRunResult(runId)
  const submit = useSubmitReviewTask()
  const approve = () => {
    if (!run.data?.review_task_id) return
    submit.mutate({ taskId: run.data.review_task_id, body: { decision: 'approve', reviewer: 'ops-manager', reason: '운영 콘솔에서 현장 작업지시서를 발행했습니다.' } })
  }
  return <div className="activity-stack"><SurfaceCard action={<Button disabled={!run.data?.review_task_id || run.data.review_status !== 'pending' || submit.isPending} onClick={approve} tone="primary">{submit.isPending ? '승인 기록 중' : run.data?.review_status === 'approved' ? '발행 승인됨' : '작업지시서 발행 승인'}</Button>} title="현장 작업지시서"><ApiState empty={false} error={run.isError || result.isError} loading={run.isLoading || result.isLoading} retry={() => { void run.refetch(); void result.refetch() }} />{run.data && result.data && <article className="work-order"><div className="detail-title"><StatusBadge tone={run.data.review_status === 'approved' ? 'success' : 'warning'}>{run.data.review_status === 'approved' ? '발행됨' : '승인 대기'}</StatusBadge><h2>{result.data.headline}</h2><p>대상: {complexNameOf(run.data.substation_id, run.data.manufacturer_id)} 기계실 {run.data.substation_id ?? '-'} · 실행 {run.data.run_id}</p></div><section><h3>작업 목적</h3><p>{run.data.ops_output?.summary ?? result.data.situation}</p></section><section><h3>현장 작업 내용</h3><ol>{result.data.actions.map((action) => <li key={action.priority}><strong>{action.title}</strong><span>{action.detail}</span></li>)}</ol></section><section><h3>안전 확인</h3><p>{run.data.ops_output?.caution ?? result.data.cautions.join(' ')}</p></section><div className="work-order-meta"><span>승인 작업 ID <strong>{run.data.review_task_id ?? '없음'}</strong></span><span>발행 상태 <strong>{run.data.review_status}</strong></span></div></article>}{submit.isError && <p className="form-error">승인 기록을 저장하지 못했습니다. 이미 처리된 작업인지 확인해 주세요.</p>}</SurfaceCard></div>
}

export function ReportsPage({ runId, onOpenAlerts, onSelectRun }: Props) {
  const [tab, setTab] = useState<ActivityTab>('runs')
  const tabs: readonly [ActivityTab, string][] = [['runs', '실행 현황'], ['reports', 'AI 보고서'], ['orders', '작업지시서']]
  if (!runId) return <div className="page-stack"><header className="page-title"><div><h1>AI 활동</h1><p>AI 실행부터 보고서와 현장 작업지시서 승인까지 한 흐름으로 관리합니다.</p></div></header><NoRun onOpenAlerts={onOpenAlerts} onSelectRun={onSelectRun} /></div>
  return <div className="page-stack activity-page"><header className="page-title"><div><h1>AI 활동</h1><p>실제 실행 결과를 확인하고, 보고서와 현장 작업지시서를 검토·발행합니다.</p></div></header><div className="activity-tabs" role="tablist">{tabs.map(([value, label]) => <button aria-selected={tab === value} className={tab === value ? 'active' : ''} key={value} onClick={() => setTab(value)} role="tab" type="button">{label}</button>)}</div>{tab === 'runs' && <RunProgress onSelectRun={onSelectRun} runId={runId} />}{tab === 'reports' && <ReportPanel runId={runId} />}{tab === 'orders' && <WorkOrderPanel runId={runId} />}</div>
}
