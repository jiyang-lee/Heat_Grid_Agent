import { useEffect, useState } from 'react'
import { ApiError, replayApi } from '../api/client'
import type { AutomationMode, PolicyCandidate, ReplayDataset } from '../api/contracts'
import { useAutomationPolicy, useDecidePolicyCandidate, useHealth, useOperationsMetrics, usePolicyCandidates, useUpdateAutomationPolicy } from '../api/hooks'
import { SCENARIO_ALERTS, SCENARIO_START_AT } from '../scenario/scenarioData'
import { useScenario } from '../scenario/useScenario'
import { Button, MetricCard, StatusBadge, SurfaceCard, type Tone } from './ui'

interface Props {
  readonly onModeChanged: () => void
  readonly refreshRevision: number
}

const TABS = ['시뮬레이션', '운영 지표', '정책 관리'] as const
type AdminTab = (typeof TABS)[number]

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return '다른 관리자가 먼저 저장했습니다. 최신 정책을 다시 불러오세요.'
  if (error instanceof ApiError && error.status === 403) return '관리자 권한이 필요합니다.'
  return error instanceof Error ? error.message : '요청을 처리하지 못했습니다.'
}

interface DatasetFaultSummary {
  readonly title: string
  readonly description: string
  readonly tags: readonly string[]
}

function faultSummaryFor(dataset: ReplayDataset): DatasetFaultSummary {
  if (dataset.dataset_version !== 'predist-synthetic-replay-v2') {
    return { title: '시나리오 데이터셋', description: '이 데이터셋에 대한 고장 시나리오 요약이 아직 등록되지 않았습니다.', tags: [] }
  }
  const urgentCount = SCENARIO_ALERTS.filter((alert) => alert.priority === 'urgent').length
  const minLeadTime = Math.min(...SCENARIO_ALERTS.map((alert) => alert.leadTimeHours))
  const tags = SCENARIO_ALERTS.flatMap((alert) => {
    const facilityLabel = alert.facility.split('·')[1]?.trim()
    return facilityLabel ? [facilityLabel] : []
  })
  return {
    title: '환수온도 급락 및 동시다발 설비 고장',
    description: `설비 이상 ${SCENARIO_ALERTS.length}건이 동시에 감지됩니다 (긴급 ${urgentCount}건 · 최단 리드타임 ${minLeadTime}시간).`,
    tags,
  }
}

/** 데이터셋의 기술적 replay_start~replay_end는 재생 인덱싱용 범위라 사용자에게는 의미가 없다.
 * 알려진 시나리오는 실제 사고 스토리의 날짜를 대신 보여준다. */
function datasetStoryDate(dataset: ReplayDataset): string {
  if (dataset.dataset_version === 'predist-synthetic-replay-v2') return formatDate(SCENARIO_START_AT)
  return `${formatDate(dataset.replay_start)} ~ ${formatDate(dataset.replay_end)}`
}

function datasetStatusTone(status: ReplayDataset['status']): Tone {
  if (status === 'available' || status === 'imported') return 'success'
  if (status === 'processing') return 'warning'
  if (status === 'failed') return 'critical'
  return 'neutral'
}

function datasetStatusLabel(status: ReplayDataset['status']): string {
  if (status === 'available') return '사용 가능'
  if (status === 'imported') return '임포트됨'
  if (status === 'processing') return '처리 중'
  return '실패'
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('ko-KR')
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ko-KR')
}

function healthTone(value: string | undefined): Tone {
  if (value == null) return 'neutral'
  return /connected|configured|ready|ok/i.test(value) ? 'success' : 'critical'
}

interface SimulationPanelProps {
  readonly datasets: readonly ReplayDataset[]
  readonly error: string | null
  readonly onModeChanged: () => void
  readonly onRetry: () => void
}

function SimulationPanel({ datasets, error, onModeChanged, onRetry }: SimulationPanelProps) {
  const scenario = useScenario()
  const usableDatasetCount = datasets.filter((item) => item.status === 'available' || item.status === 'imported').length

  const enterReplay = () => {
    scenario.startFaultScenario()
    onModeChanged()
  }

  const returnToNormal = () => {
    scenario.selectMode('normal')
    onModeChanged()
  }

  return <SurfaceCard
    action={scenario.state.mode === 'fault' ? <Button onClick={returnToNormal}>정상 운영으로 복귀</Button> : <Button disabled={usableDatasetCount === 0} onClick={enterReplay} tone="primary">시뮬레이션 시작</Button>}
    title="시뮬레이션"
  >
    <div className="admin-dataset-list">
      {datasets.length === 0 && <p className="admin-empty">등록된 재생 데이터셋이 없습니다.</p>}
      {datasets.map((dataset, index) => {
        const summary = faultSummaryFor(dataset)
        return <article className="admin-dataset-card" key={dataset.dataset_id}>
          <header>
            <StatusBadge tone={datasetStatusTone(dataset.status)}>{datasetStatusLabel(dataset.status)}</StatusBadge>
            <span>시뮬레이션 {index + 1}</span>
          </header>
          <strong>{summary.title}</strong>
          <p>{summary.description}</p>
          {summary.tags.length > 0 && <ul className="admin-dataset-tags">{summary.tags.map((tag) => <li key={tag}>{tag}</li>)}</ul>}
          <small>시나리오 날짜 {datasetStoryDate(dataset)}</small>
        </article>
      })}
    </div>
    {error && <p className="form-error">{error} <button onClick={onRetry} type="button">다시 불러오기</button></p>}
  </SurfaceCard>
}

function OperationsPanel() {
  const health = useHealth()
  const status = health.data
  const metrics = useOperationsMetrics()
  const data = metrics.data
  const diagnosticIssues = data ? data.diagnostic_timeout_count + data.diagnostic_invalid_count + data.diagnostic_budget_exceeded_count : 0

  return <div className="admin-operations-panel">
    <SurfaceCard title="시스템 헬스">
      {health.isError ? <p className="form-error">헬스 상태를 불러오지 못했습니다.</p> : <div className="metric-grid admin-metric-grid-three">
        <MetricCard icon="monitor" label="데이터베이스" tone={healthTone(status?.database)} value={status?.database === 'connected' ? '정상' : status == null ? '확인 중' : '오류'} />
        <MetricCard icon="settings" label="OpenAI" tone={healthTone(status?.openai)} value={status?.openai === 'configured' ? '정상' : status == null ? '확인 중' : '오류'} />
        <MetricCard icon="search" label="RAG" tone="neutral" value={status?.rag ?? '확인 중'} />
      </div>}
    </SurfaceCard>
    <SurfaceCard title="운영 지표">
      {data == null ? <p className="admin-empty">{metrics.isError ? '지표를 불러오지 못했습니다.' : '지표를 불러오는 중입니다.'}</p> : <div className="metric-grid admin-metric-grid">
        <MetricCard icon="activity" label="AI 실행" tone="primary" value={String(data.run_count)} />
        <MetricCard icon="clock" label="검토 대기" tone={data.pending_review_count > 0 ? 'warning' : 'success'} value={String(data.pending_review_count)} />
        <MetricCard icon="gauge" label="승인율" tone="primary" value={`${Math.round(data.approval_rate * 100)}%`} />
        <MetricCard icon="warning" label="진단 이슈" tone={diagnosticIssues > 0 ? 'critical' : 'success'} value={String(diagnosticIssues)} />
      </div>}
    </SurfaceCard>
  </div>
}

const AUTOMATION_MODE_LABELS: Record<AutomationMode, string> = {
  human_only: '사람 전결',
  assisted: 'AI 보조',
  guarded_auto: '가드레일 자동화',
}

function AutomationPolicyPanel() {
  const policy = useAutomationPolicy()
  const update = useUpdateAutomationPolicy()
  const data = policy.data
  const [draft, setDraft] = useState<{
    mode: AutomationMode
    autoTransitionEnabled: boolean
    minimumReviewCount: number
    minimumApprovalRate: number
    minimumConfidence: number
    minimumSourceTrust: number
    maximumDriftScore: number
  } | null>(null)

  useEffect(() => {
    if (data == null) return
    setDraft({
      mode: data.mode,
      autoTransitionEnabled: data.auto_transition_enabled,
      minimumReviewCount: data.minimum_review_count,
      minimumApprovalRate: data.minimum_approval_rate,
      minimumConfidence: data.minimum_confidence,
      minimumSourceTrust: data.minimum_source_trust,
      maximumDriftScore: data.maximum_drift_score,
    })
  }, [data])

  const save = () => {
    if (draft == null) return
    update.mutate({
      mode: draft.mode,
      auto_transition_enabled: draft.autoTransitionEnabled,
      minimum_review_count: draft.minimumReviewCount,
      minimum_approval_rate: draft.minimumApprovalRate,
      minimum_confidence: draft.minimumConfidence,
      minimum_source_trust: draft.minimumSourceTrust,
      maximum_drift_score: draft.maximumDriftScore,
      updated_by: 'ops-manager',
    })
  }

  const [showAdvanced, setShowAdvanced] = useState(false)

  if (data == null || draft == null) return <SurfaceCard title="자동화 정책"><p className="admin-empty">{policy.isError ? '정책을 불러오지 못했습니다.' : '불러오는 중입니다.'}</p></SurfaceCard>

  return <SurfaceCard title="자동화 정책">
    <p className="admin-panel-note">AI가 스스로 판단해 다음 단계로 넘어갈 수 있게 할지, 사람이 매번 확인할지를 정합니다.</p>
    <div className="admin-automation-status">
      <StatusBadge tone="primary">{AUTOMATION_MODE_LABELS[data.mode]}</StatusBadge>
      <span>검토 {data.reviewed_count}건 · 승인율 {Math.round(data.approval_rate * 100)}%</span>
      <StatusBadge tone={data.eligible_for_guarded_auto ? 'success' : 'neutral'}>{data.eligible_for_guarded_auto ? '가드레일 자동화 승격 가능' : '승격 기준 미달'}</StatusBadge>
      <small>마지막 변경 {data.updated_by} · {formatDateTime(data.updated_at)}</small>
    </div>
    <div className="form-grid admin-automation-form">
      <label>운영 모드
        <select onChange={(event) => setDraft({ ...draft, mode: event.target.value as AutomationMode })} value={draft.mode}>
          {(Object.keys(AUTOMATION_MODE_LABELS) as AutomationMode[]).map((mode) => <option key={mode} value={mode}>{AUTOMATION_MODE_LABELS[mode]}</option>)}
        </select>
      </label>
      <label className="toggle-label">
        <span className="switch"><input checked={draft.autoTransitionEnabled} onChange={(event) => setDraft({ ...draft, autoTransitionEnabled: event.target.checked })} type="checkbox" /><i /></span>
        자동 전환 사용
      </label>
    </div>
    <button className="admin-advanced-toggle" onClick={() => setShowAdvanced((value) => !value)} type="button">{showAdvanced ? '세부 기준 접기' : '세부 기준 펼치기 (전문가용)'}</button>
    {showAdvanced && <div className="form-grid admin-automation-form">
      <label>최소 검토 건수<input min="0" onChange={(event) => setDraft({ ...draft, minimumReviewCount: Number(event.target.value) })} type="number" value={draft.minimumReviewCount} /></label>
      <label>최소 승인율<input max="1" min="0" onChange={(event) => setDraft({ ...draft, minimumApprovalRate: Number(event.target.value) })} step="0.01" type="number" value={draft.minimumApprovalRate} /></label>
      <label>최소 신뢰도<input max="1" min="0" onChange={(event) => setDraft({ ...draft, minimumConfidence: Number(event.target.value) })} step="0.01" type="number" value={draft.minimumConfidence} /></label>
      <label>최소 근거 신뢰도<input max="1" min="0" onChange={(event) => setDraft({ ...draft, minimumSourceTrust: Number(event.target.value) })} step="0.01" type="number" value={draft.minimumSourceTrust} /></label>
      <label>최대 드리프트 점수<input max="1" min="0" onChange={(event) => setDraft({ ...draft, maximumDriftScore: Number(event.target.value) })} step="0.01" type="number" value={draft.maximumDriftScore} /></label>
    </div>}
    <div className="admin-policy-actions"><Button disabled={update.isPending} onClick={save} tone="primary">{update.isPending ? '저장 중' : '정책 저장'}</Button></div>
    {update.isError && <p className="form-error">정책을 저장하지 못했습니다. 다시 시도해 주세요.</p>}
  </SurfaceCard>
}

function candidateStatusTone(status: PolicyCandidate['status']): Tone {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'critical'
  return 'warning'
}

function candidateStatusLabel(status: PolicyCandidate['status']): string {
  if (status === 'approved') return '승인됨'
  if (status === 'rejected') return '반려됨'
  return '검토 대기'
}

function PolicyCandidateRow({ candidate }: { readonly candidate: PolicyCandidate }) {
  const decide = useDecidePolicyCandidate()
  const [reason, setReason] = useState('')
  const pending = candidate.status === 'pending'

  const submit = (approve: boolean) => {
    if (!reason.trim()) return
    decide.mutate(
      { candidateId: candidate.candidate_id, approve, body: { expected_version: candidate.version, reviewer: 'ops-manager', reason: reason.trim() } },
      { onSuccess: () => setReason('') },
    )
  }

  return <article className="admin-list-card">
    <header><StatusBadge tone={candidateStatusTone(candidate.status)}>{candidateStatusLabel(candidate.status)}</StatusBadge><strong>{candidate.scope}</strong><span>{formatDateTime(candidate.created_at)}</span></header>
    <ul className="admin-candidate-proposal">{Object.entries(candidate.proposal).map(([key, value]) => <li key={key}><span>{key}</span><strong>{String(value)}</strong></li>)}</ul>
    {pending && <div className="admin-inline-form">
      <input onChange={(event) => setReason(event.target.value)} placeholder="승인/반려 사유" value={reason} />
      <Button disabled={!reason.trim() || decide.isPending} onClick={() => submit(true)} tone="primary">승인</Button>
      <Button disabled={!reason.trim() || decide.isPending} onClick={() => submit(false)} tone="danger">반려</Button>
    </div>}
    {decide.isError && <p className="form-error">처리하지 못했습니다. 다시 시도해 주세요.</p>}
  </article>
}

function PolicyCandidatesPanel() {
  const candidates = usePolicyCandidates()
  return <SurfaceCard title="정책 후보">
    <p className="admin-panel-note">운영자가 AI 조치 검토에서 &ldquo;실행 교정 기록&rdquo;을 남기면 여기에 정책 후보로 쌓입니다.</p>
    {candidates.isLoading && <p className="admin-empty">불러오는 중입니다.</p>}
    {candidates.isError && <p className="form-error">정책 후보를 불러오지 못했습니다.</p>}
    {candidates.data != null && candidates.data.items.length === 0 && <p className="admin-empty">등록된 정책 후보가 없습니다.</p>}
    <div className="admin-list">{candidates.data?.items.map((candidate) => <PolicyCandidateRow candidate={candidate} key={candidate.candidate_id} />)}</div>
  </SurfaceCard>
}

function PolicyPanel() {
  return <div className="admin-operations-panel">
    <AutomationPolicyPanel />
    <PolicyCandidatesPanel />
  </div>
}

export function AdminPage({ onModeChanged, refreshRevision }: Props) {
  const [tab, setTab] = useState<AdminTab>('시뮬레이션')
  const [datasets, setDatasets] = useState<readonly ReplayDataset[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setError(null)
    try {
      setDatasets(await replayApi.listDatasets())
    } catch (caught: unknown) {
      setError(errorMessage(caught))
    }
  }

  useEffect(() => { void load() }, [refreshRevision])

  return <div className="page-stack admin-page">
    <div className="activity-tabs" role="tablist">{TABS.map((item) => <button aria-selected={tab === item} className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)} role="tab" type="button">{item}</button>)}</div>
    {tab === '시뮬레이션' && <SimulationPanel datasets={datasets} error={error} onModeChanged={onModeChanged} onRetry={() => void load()} />}
    {tab === '운영 지표' && <OperationsPanel />}
    {tab === '정책 관리' && <PolicyPanel />}
  </div>
}
