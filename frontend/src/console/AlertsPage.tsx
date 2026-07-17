import { useMemo, useState } from 'react'
import type { AlertSummary, PriorityLevel } from '../api/contracts'
import { useAlerts, useCreateAgentRun, useResolveAlert } from '../api/hooks'
import { complexNameOf } from '../domain/model'
import { AgentAnalysisProgress } from './AgentAnalysisProgress'
import { useAgentAnalysis } from './agentAnalysisProgressState'
import { Icon } from './icons'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from './ui'

interface Props {
  readonly onRunCreated: (runId: string) => void
}

type AlertScope = 'active' | 'history'

function alertTone(alert: AlertSummary): Tone {
  return alert.priority_level === 'urgent' ? 'critical' : 'warning'
}

function dateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('ko-KR') : '-'
}

function statusLabel(alert: AlertSummary): string {
  if (alert.status === 'resolved') return '종결'
  if (alert.status === 'acked') return '확인됨'
  return alert.priority_level === 'urgent' ? '긴급' : '경고'
}

export function AlertsPage({ onRunCreated }: Props) {
  const [search, setSearch] = useState('')
  const [priority, setPriority] = useState<PriorityLevel | 'all'>('all')
  const [scope, setScope] = useState<AlertScope>('active')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [createdRunId, setCreatedRunId] = useState<string | null>(null)
  const analysis = useAgentAnalysis(createdRunId)
  const alerts = useAlerts({ status: 'all' })
  const resolve = useResolveAlert()
  const createRun = useCreateAgentRun()
  const allRows = useMemo(() => alerts.data ?? [], [alerts.data])
  const rows = useMemo(() => allRows.filter((alert) => {
    if (scope === 'active' ? alert.status === 'resolved' : alert.status !== 'resolved') return false
    if (priority !== 'all' && alert.priority_level !== priority) return false
    const text = `${complexNameOf(alert.substation_id, alert.manufacturer_id)} ${alert.manufacturer_id} ${alert.substation_id} ${alert.enqueue_reason}`
    return text.toLowerCase().includes(search.toLowerCase())
  }), [allRows, priority, scope, search])
  const selected = selectedId ? allRows.find((alert) => alert.alert_id === selectedId) ?? null : null

  const resolveAlert = (alert: AlertSummary) => {
    if (!window.confirm(`'${alert.enqueue_reason}' 알림을 종결할까요?`)) return
    resolve.mutate({ alertId: alert.alert_id, ackedBy: 'ops-manager' }, { onSuccess: () => setScope('history') })
  }
  const startAgentRun = () => {
    if (!selected) return
    createRun.reset()
    createRun.mutate({ alertId: selected.alert_id, requestedBy: 'ops-manager', reason: '운영 콘솔에서 AI 조치 생성을 요청했습니다.' }, { onSuccess: (run) => setCreatedRunId(run.run_id) })
  }
  const openAiAction = () => {
    if (createdRunId == null || analysis.status !== 'completed') return
    const runId = createdRunId
    setCreatedRunId(null)
    onRunCreated(runId)
  }

  return <div className="page-stack alert-page">
    <div className={`alerts-workspace ${selected ? 'has-detail' : ''}`.trim()}>
      <SurfaceCard className="alerts-list-card" title="알림 이력">
        <div className="alerts-filter-bar">
          <label><span>표시 범위</span><select onChange={(event) => setScope(event.target.value === 'history' ? 'history' : 'active')} value={scope}><option value="active">활성 알림</option><option value="history">과거 알림</option></select></label>
          <label><span>우선순위</span><select onChange={(event) => setPriority(event.target.value as PriorityLevel | 'all')} value={priority}><option value="all">전체</option><option value="urgent">긴급</option><option value="high">경고</option></select></label>
          <label className="filter-search"><span>알림 검색</span><input onChange={(event) => setSearch(event.target.value)} placeholder="건물명, 설비명, 알림 내용 검색" value={search} /></label>
          <strong>{rows.length}건</strong>
        </div>
        <ApiState empty={false} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />
        {!alerts.isLoading && !alerts.isError && rows.length === 0 ? <div className="alerts-empty"><StatusBadge tone={scope === 'active' ? 'success' : 'neutral'}>{scope === 'active' ? '정상' : '이력 없음'}</StatusBadge><strong>{scope === 'active' ? '활성 알림이 없습니다.' : '조건에 맞는 과거 알림이 없습니다.'}</strong></div> : rows.length > 0 && <div className="alerts-table-scroll"><table className="alerts-table"><thead><tr><th>상태</th><th>알림 내용</th><th>설비 / 위치</th><th>발생 시간</th><th>조치 시간</th><th aria-label="알림 작업" /></tr></thead><tbody>{rows.map((alert) => <tr className={selected?.alert_id === alert.alert_id ? 'selected' : ''} key={alert.alert_id} onClick={() => { setSelectedId(alert.alert_id); setCreatedRunId(null) }}><td><span className={`alerts-severity-icon ${alert.priority_level}`}><Icon name={alert.priority_level === 'urgent' ? 'alert' : 'warning'} /></span><StatusBadge tone={alert.status === 'resolved' ? 'success' : alertTone(alert)}>{statusLabel(alert)}</StatusBadge></td><td><strong>{alert.enqueue_reason}</strong></td><td><strong>{complexNameOf(alert.substation_id, alert.manufacturer_id)}</strong><small>기계실 {alert.substation_id ?? '-'}</small></td><td>{dateTime(alert.created_at)}</td><td>{dateTime(alert.acked_at)}</td><td><button className="alerts-row-action" onClick={(event) => { event.stopPropagation(); setSelectedId(alert.alert_id); setCreatedRunId(null) }} type="button">상세</button></td></tr>)}</tbody></table></div>}
      </SurfaceCard>
      {selected && <SurfaceCard action={<button aria-label="상세 정보 닫기" className="scenario-detail-close" onClick={() => { setSelectedId(null); setCreatedRunId(null) }} type="button"><Icon name="x" /></button>} className="alerts-detail-card" title="상세 정보">
        <div className="detail-body alerts-detail-body">
          <div className="detail-title"><StatusBadge tone={selected.status === 'resolved' ? 'success' : alertTone(selected)}>{statusLabel(selected)}</StatusBadge><h2>{selected.enqueue_reason}</h2><p>{complexNameOf(selected.substation_id, selected.manufacturer_id)} · 기계실 {selected.substation_id ?? '-'}</p></div>
          <section><h3>알림 판단 정보</h3><div className="alert-detail-facts"><div><span>우선순위</span><strong>{selected.priority_level}</strong></div><div><span>점수</span><strong>{selected.priority_score?.toFixed(1) ?? '-'}</strong></div><div><span>순위</span><strong>{selected.priority_rank ?? '-'}</strong></div><div><span>데이터 상태</span><strong>{selected.freshness_status ?? '-'}</strong></div><div><span>발생 시간</span><strong>{dateTime(selected.created_at)}</strong></div><div><span>기준 시각</span><strong>{dateTime(selected.as_of_time)}</strong></div></div></section>
          <section><h3>연결 정보</h3><p>카드 ID: {selected.card_id}</p><p>평가 실행 ID: {selected.evaluation_run_id ?? '-'}</p></section>
          {(createRun.isError || analysis.status === 'failed') && <p className="form-error">{analysis.error ?? 'AI 실행을 시작하지 못했습니다. 백엔드 연결 상태를 확인해 주세요.'}</p>}
          <div className="detail-actions">{analysis.status !== 'completed' && selected.status !== 'resolved' && <Button disabled={createRun.isPending || analysis.status === 'running'} icon="activity" onClick={startAgentRun} tone="primary">{createRun.isPending || analysis.status === 'running' ? 'AI 분석 진행 중' : 'AI 조치 분석'}</Button>}{selected.status !== 'resolved' && <Button disabled={resolve.isPending} onClick={() => resolveAlert(selected)} tone="danger">종결</Button>}</div>
        </div>
      </SurfaceCard>}
    </div>
    {(createRun.isPending || analysis.status === 'running') && <AgentAnalysisProgress phase={analysis.phase} />}
    {createdRunId && analysis.status === 'completed' && <button className="scenario-ai-shortcut" onClick={openAiAction} type="button">AI 조치 바로가기 <Icon name="arrow" /></button>}
  </div>
}
