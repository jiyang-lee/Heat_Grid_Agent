import { useEffect, useMemo, useState } from 'react'
import { agentRunsApi, scenarioAlertsApi } from '../api/client'
import { Icon } from '../console/icons'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { ScenarioSensorEvidenceChart } from './ScenarioSensorEvidenceChart'
import type { ScenarioAlert, ScenarioTimelineAlert } from './types'
import { useScenario } from './useScenario'

interface Props {
  readonly initialAlertId: string | null
  readonly onConsumeInitialAlert: () => void
  readonly onOpenAiAction: (runId: string) => void
}

type AlertScope = 'active' | 'history'

function priorityTone(alert: ScenarioAlert): 'critical' | 'warning' {
  return alert.priority === 'urgent' ? 'critical' : 'warning'
}

function sensorEvidence(alert: ScenarioAlert): readonly [string, string, string] {
  if (alert.affectedMetric === 'flow') return ['86.0 m³/h', '100~130 m³/h', '-32.0 m³/h']
  if (alert.affectedMetric === 'supply') return ['84.6 °C', '75~85 °C', '+8.2 °C']
  return ['34.1 °C', '40~50 °C', '-8.1 °C']
}

function dateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('ko-KR') : '-'
}

function metricLabel(alert: ScenarioAlert): string {
  if (alert.affectedMetric === 'flow') return '유량'
  if (alert.affectedMetric === 'supply') return '공급온도'
  return '환수온도'
}

export function ScenarioAlertsPage({ initialAlertId, onConsumeInitialAlert, onOpenAiAction }: Props) {
  const scenario = useScenario()
  const { alertHistory, alerts, completeAnalysis, dismissAnalysisToast, failAnalysis, resolveAlert, selectAlert, sensor, startAnalysis, state } = scenario
  const [detailId, setDetailId] = useState<string | null>(null)
  const [scope, setScope] = useState<AlertScope>('active')
  const [search, setSearch] = useState('')
  const [priority, setPriority] = useState<'all' | ScenarioAlert['priority']>('all')
  const [createdRunId, setCreatedRunId] = useState<string | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const allAlerts = useMemo(() => [...alerts, ...alertHistory], [alertHistory, alerts])
  const source = scope === 'active' ? alerts : alertHistory
  const rows = useMemo(() => source.filter((alert) => {
    if (priority !== 'all' && alert.priority !== priority) return false
    return `${alert.title} ${alert.facility} ${alert.summary}`.toLowerCase().includes(search.toLowerCase())
  }), [priority, search, source])
  const selected = detailId ? allAlerts.find((alert) => alert.id === detailId) ?? null : null

  useEffect(() => {
    if (initialAlertId == null) return
    const initial = allAlerts.find((alert) => alert.id === initialAlertId)
    if (!initial) return
    selectAlert(initial.id)
    setDetailId(initial.id)
    setScope(initial.status === 'active' ? 'active' : 'history')
    onConsumeInitialAlert()
  }, [allAlerts, initialAlertId, onConsumeInitialAlert, selectAlert])

  useEffect(() => {
    if (selected != null && selected.status !== 'active') setScope('history')
  }, [selected])

  const openDetail = (alert: ScenarioTimelineAlert) => {
    selectAlert(alert.id)
    setDetailId(alert.id)
  }
  const confirmResolve = (alert: ScenarioTimelineAlert) => {
    if (!window.confirm(`'${alert.title}' 알림을 종결할까요?`)) return
    resolveAlert(alert.id)
    setScope('history')
  }
  const moveToAiAction = () => {
    if (state.analysisAlertId != null) selectAlert(state.analysisAlertId)
    if (createdRunId == null) return
    dismissAnalysisToast()
    onOpenAiAction(createdRunId)
  }
  const runAnalysis = async (alert: ScenarioTimelineAlert) => {
    setAnalysisError(null)
    setCreatedRunId(null)
    startAnalysis(alert.id)
    try {
      const persisted = await scenarioAlertsApi.create({
        scenario_alert_id: alert.id,
        substation_id: alert.substationId,
        priority_level: alert.priority,
        reason: `${alert.title} · ${alert.summary}`,
      })
      const run = await agentRunsApi.create({
        alert_id: persisted.alert_id,
        requested_by: 'operator',
        reason: '고장 시나리오 알림에서 AI 조치 분석 실행',
      })
      setCreatedRunId(run.run_id)
      completeAnalysis()
    } catch (error: unknown) {
      failAnalysis()
      setAnalysisError(error instanceof Error ? error.message : 'AI 조치 실행을 시작하지 못했습니다.')
    }
  }
  const analyzed = selected != null && state.analyzedAlertIds.includes(selected.id)
  const analysisRunning = selected != null && state.analysisState === 'running' && state.analysisAlertId === selected.id

  return <div className="page-stack alert-page scenario-alert-page">
    <div className={`alerts-workspace ${selected ? 'has-detail' : ''}`.trim()}>
      <SurfaceCard className="alerts-list-card" title="알림 이력">
        <div className="alerts-filter-bar">
          <label><span>표시 범위</span><select onChange={(event) => setScope(event.target.value === 'history' ? 'history' : 'active')} value={scope}><option value="active">활성 알림</option><option value="history">과거 알림</option></select></label>
          <label><span>우선순위</span><select onChange={(event) => setPriority(event.target.value === 'urgent' || event.target.value === 'high' ? event.target.value : 'all')} value={priority}><option value="all">전체</option><option value="urgent">긴급</option><option value="high">경고</option></select></label>
          <label className="filter-search"><span>알림 검색</span><input onChange={(event) => setSearch(event.target.value)} placeholder="설비명, 알림 내용 검색" value={search} /></label>
          <strong>{rows.length}건</strong>
        </div>
        {rows.length === 0 ? <div className="alerts-empty"><StatusBadge tone={scope === 'active' ? 'success' : 'neutral'}>{scope === 'active' ? '정상' : '이력 없음'}</StatusBadge><strong>{scope === 'active' ? '활성 알림이 없습니다.' : '조건에 맞는 과거 알림이 없습니다.'}</strong></div> : <div className="alerts-table-scroll"><table className="alerts-table"><thead><tr><th>상태</th><th>알림 내용</th><th>설비 / 위치</th><th>발생 시간</th><th>조치 시간</th><th aria-label="알림 작업" /></tr></thead><tbody>{rows.map((alert) => <tr className={selected?.id === alert.id ? 'selected' : ''} key={alert.id} onClick={() => openDetail(alert)}><td><span className={`alerts-severity-icon ${alert.priority}`}><Icon name={alert.priority === 'urgent' ? 'alert' : 'warning'} /></span><StatusBadge tone={alert.status === 'resolved' ? 'success' : priorityTone(alert)}>{alert.status === 'resolved' ? '종결' : alert.status === 'expired' ? '기한 경과' : alert.priority === 'urgent' ? '긴급' : '경고'}</StatusBadge></td><td><strong>{alert.title}</strong></td><td><strong>기계실 {alert.substationId}</strong><small>{alert.facility}</small></td><td>{dateTime(alert.detectedAt)}</td><td>{alert.status === 'resolved' ? dateTime(alert.resolvedAt) : '-'}</td><td><button className="alerts-row-action" onClick={(event) => { event.stopPropagation(); openDetail(alert) }} type="button">상세</button></td></tr>)}</tbody></table></div>}
      </SurfaceCard>
      {selected && <SurfaceCard action={<button aria-label="상세 정보 닫기" className="scenario-detail-close" onClick={() => setDetailId(null)} type="button"><Icon name="x" /></button>} className="alerts-detail-card" title="상세 정보">
        <div className="scenario-detail-compact">
          <div className="scenario-detail-title"><StatusBadge tone={selected.status === 'resolved' ? 'success' : priorityTone(selected)}>{selected.status === 'resolved' ? '종결' : selected.status === 'expired' ? '기한 경과' : selected.priority}</StatusBadge><strong>{selected.title}</strong><span>{selected.facility} · 고장 예상 시간 {selected.leadTimeHours}시간</span></div>
          <div className="scenario-sensor-facts"><div><span>이상 센서</span><strong>{metricLabel(selected)}</strong></div><div><span>현재값</span><strong>{sensorEvidence(selected)[0]}</strong></div><div><span>정상 범위</span><strong>{sensorEvidence(selected)[1]}</strong></div><div><span>변화량</span><strong className="critical-text">{sensorEvidence(selected)[2]}</strong></div></div>
          <ScenarioSensorEvidenceChart alert={selected} points={sensor.state.points} />
          <section><h3>판단 근거</h3><p>{selected.summary}</p><ol className="scenario-reasoning"><li><strong>이상 감지</strong><span>{selected.evidence[0]}로 정상 범위 이탈이 확인되었습니다.</span></li><li><strong>모델 판단</strong><span>이상 점수와 센서 품질 검증을 통과한 데이터가 동일 시점의 설비 패턴과 일치합니다.</span></li><li><strong>현장 영향</strong><span>{selected.affectedMetric === 'flow' ? '열교환 성능 저하와 누수 확산 가능성을 확인해야 합니다.' : selected.affectedMetric === 'supply' ? '급탕 공급 안정성과 제어밸브 동작에 영향을 줄 수 있습니다.' : '난방 순환 효율 저하와 세대 난방 불균형으로 확산될 수 있습니다.'}</span></li></ol></section>
          {analysisError && <p className="scenario-analysis-error" role="alert">{analysisError}</p>}
          <div className="scenario-detail-actions">{!analyzed && selected.status !== 'resolved' && <Button disabled={analysisRunning} icon="activity" onClick={() => void runAnalysis(selected)} tone="primary">{analysisRunning ? 'AI 분석 진행 중' : 'AI 조치 분석'}</Button>}{selected.status !== 'resolved' && <Button onClick={() => confirmResolve(selected)} tone="danger">종결</Button>}</div>
        </div>
      </SurfaceCard>}
    </div>
    {state.analysisToastVisible && <button className="scenario-ai-shortcut" onClick={moveToAiAction} type="button">AI 조치 바로가기 <Icon name="arrow" /></button>}
  </div>
}
