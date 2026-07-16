import { useEffect, useMemo, useState } from 'react'
import { Icon } from '../console/icons'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { ScenarioSensorEvidenceChart } from './ScenarioSensorEvidenceChart'
import type { ScenarioAlert } from './types'
import { useScenario } from './useScenario'

interface Props {
  readonly onOpenAiAction: () => void
  readonly initialAlertId: string | null
}

function priorityTone(alert: ScenarioAlert): 'critical' | 'warning' {
  return alert.priority === 'urgent' ? 'critical' : 'warning'
}

function sensorEvidence(alert: ScenarioAlert): readonly [string, string, string] {
  if (alert.affectedMetric === 'flow') return ['86.0 m³/h', '100~130 m³/h', '-32.0 m³/h']
  if (alert.affectedMetric === 'supply') return ['84.6 °C', '75~85 °C', '+8.2 °C']
  return ['34.1 °C', '40~50 °C', '-8.1 °C']
}

type PriorityFilter = 'all' | ScenarioAlert['priority']
type MetricFilter = 'all' | ScenarioAlert['affectedMetric']
type LeadTimeFilter = 'all' | 'urgent-window' | 'today'

function priorityFilterFrom(value: string): PriorityFilter {
  return value === 'urgent' || value === 'high' ? value : 'all'
}

function metricFilterFrom(value: string): MetricFilter {
  return value === 'returnTemperature' || value === 'supply' || value === 'flow' ? value : 'all'
}

function leadTimeFilterFrom(value: string): LeadTimeFilter {
  return value === 'urgent-window' || value === 'today' ? value : 'all'
}

export function ScenarioAlertsPage({ initialAlertId, onOpenAiAction }: Props) {
  const { alertHistory, alerts, completeAnalysis, dismissAnalysisToast, selectAlert, sensor, startAnalysis, state } = useScenario()
  const [detailId, setDetailId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('all')
  const [metricFilter, setMetricFilter] = useState<MetricFilter>('all')
  const [leadTimeFilter, setLeadTimeFilter] = useState<LeadTimeFilter>('all')
  const incidentActive = state.incidentState === 'incident-active'
  const rows = useMemo(() => incidentActive ? alerts.filter((alert) => {
    const searchMatched = `${alert.title} ${alert.facility} ${alert.summary}`.toLowerCase().includes(search.toLowerCase())
    const priorityMatched = priorityFilter === 'all' || alert.priority === priorityFilter
    const metricMatched = metricFilter === 'all' || alert.affectedMetric === metricFilter
    const leadTimeMatched = leadTimeFilter === 'all' || (leadTimeFilter === 'urgent-window' ? alert.leadTimeHours < 12 : alert.leadTimeHours < 24)
    return searchMatched && priorityMatched && metricMatched && leadTimeMatched
  }) : [], [alerts, incidentActive, leadTimeFilter, metricFilter, priorityFilter, search])
  const selected = rows.find((alert) => alert.id === detailId) ?? null

  useEffect(() => {
    if (state.analysisState !== 'running') return undefined
    const timer = window.setTimeout(completeAnalysis, 1_200)
    return () => window.clearTimeout(timer)
  }, [completeAnalysis, state.analysisState])

  useEffect(() => {
    if (!incidentActive || initialAlertId == null || !alerts.some((alert) => alert.id === initialAlertId)) return
    selectAlert(initialAlertId)
    setDetailId(initialAlertId)
  }, [alerts, incidentActive, initialAlertId, selectAlert])

  const openDetail = (alert: ScenarioAlert) => {
    selectAlert(alert.id)
    setDetailId(alert.id)
  }
  const moveToAiAction = () => {
    dismissAnalysisToast()
    onOpenAiAction()
  }

  return <div className="page-stack alert-page scenario-alert-page">
    <div className={`scenario-alert-workspace ${selected ? 'has-detail' : ''}`.trim()}>
      <SurfaceCard className="scenario-alert-list" title="활성 알림">
        <div className="filter-bar scenario-filter">
          <label className="filter-search"><span>알림 검색</span><input onChange={(event) => setSearch(event.target.value)} placeholder="설비명, 알림 내용 검색" value={search} /></label>
          <label><span>우선순위</span><select aria-label="우선순위 필터" onChange={(event) => setPriorityFilter(priorityFilterFrom(event.target.value))} value={priorityFilter}><option value="all">전체</option><option value="urgent">urgent</option><option value="high">high</option></select></label>
          <label><span>이상 센서</span><select aria-label="이상 센서 필터" onChange={(event) => setMetricFilter(metricFilterFrom(event.target.value))} value={metricFilter}><option value="all">전체 센서</option><option value="returnTemperature">환수온도</option><option value="supply">공급온도</option><option value="flow">유량</option></select></label>
          <label><span>출동 기한</span><select aria-label="출동 기한 필터" onChange={(event) => setLeadTimeFilter(leadTimeFilterFrom(event.target.value))} value={leadTimeFilter}><option value="all">전체</option><option value="urgent-window">12시간 이내</option><option value="today">24시간 이내</option></select></label>
          <span className="scenario-filter-count">{incidentActive ? `${rows.length}건 표시` : '정상 수신 중'}</span>
        </div>
        {!incidentActive && <div className="scenario-list-empty"><StatusBadge tone="success">정상</StatusBadge><strong>운영 알림이 없습니다.</strong><span>고장 시나리오 감지를 대기하고 있습니다.</span></div>}
        {incidentActive && <div className="scenario-alert-rows">{rows.map((alert, index) => <button aria-pressed={detailId === alert.id} className={detailId === alert.id ? 'selected' : ''} key={alert.id} onClick={() => openDetail(alert)} type="button"><span className="scenario-alert-rank">{index + 1}</span><div><strong>{alert.title}</strong><span>{alert.facility} · {alert.leadTimeHours}시간 이내 출동</span></div><StatusBadge tone={priorityTone(alert)}>{alert.priority}</StatusBadge></button>)}</div>}
        {incidentActive && alertHistory.length > 0 && <section className="scenario-alert-history"><h3>알림 이력</h3><div className="scenario-alert-rows">{alertHistory.map((alert) => <div className="scenario-alert-history-row" key={alert.id}><div><strong>{alert.title}</strong><span>{alert.facility} · 출동 기한 종료</span></div><StatusBadge tone="success">종결</StatusBadge></div>)}</div></section>}
      </SurfaceCard>
      {selected && <SurfaceCard className="scenario-alert-detail" title="상세 정보" action={<button aria-label="상세 정보 닫기" className="scenario-detail-close" onClick={() => setDetailId(null)} type="button"><Icon name="x" /></button>}>
        <div className="scenario-detail-compact">
          <div className="scenario-detail-title"><StatusBadge tone={priorityTone(selected)}>{selected.priority}</StatusBadge><strong>{selected.title}</strong><span>{selected.facility} · 출동 제한 {selected.leadTimeHours}시간</span></div>
          <div className="scenario-sensor-facts"><div><span>현재값</span><strong>{sensorEvidence(selected)[0]}</strong></div><div><span>정상 범위</span><strong>{sensorEvidence(selected)[1]}</strong></div><div><span>변화량</span><strong className="critical-text">{sensorEvidence(selected)[2]}</strong></div></div>
          <ScenarioSensorEvidenceChart alert={selected} points={sensor.state.points} />
          <section><h3>판단 근거</h3><p>{selected.summary}</p><ol className="scenario-reasoning"><li><strong>이상 감지</strong><span>{selected.evidence[0]}로 정상 범위 이탈이 확인되었습니다.</span></li><li><strong>모델 판단</strong><span>이상 점수와 센서 품질 검증을 통과한 데이터가 동일 시점의 설비 패턴과 일치합니다.</span></li><li><strong>현장 영향</strong><span>{selected.affectedMetric === 'flow' ? '열교환 성능 저하와 누수 확산 가능성을 확인해야 합니다.' : selected.affectedMetric === 'supply' ? '급탕 공급 안정성과 제어밸브 동작에 영향을 줄 수 있습니다.' : '난방 순환 효율 저하와 세대 난방 불균형으로 확산될 수 있습니다.'}</span></li><li><strong>출동 우선순위</strong><span>{selected.leadTimeHours}시간 이내 출동 조건이므로 {selected.priority} 대응으로 분류합니다.</span></li></ol></section>
          <div className="scenario-detail-actions"><Button disabled={state.analysisState === 'running' || state.analysisState === 'complete'} icon="activity" onClick={startAnalysis} tone="primary">{state.analysisState === 'running' ? 'AI 분석 진행 중' : state.analysisState === 'complete' ? 'AI 조치 활성화됨' : 'AI 조치 분석'}</Button><Button>담당자 지정</Button></div>
        </div>
      </SurfaceCard>}
    </div>
    {state.analysisToastVisible && <aside aria-live="polite" className="scenario-action-toast" role="status"><div><StatusBadge tone="success">AI 조치 활성화</StatusBadge><strong>AI 조치가 활성화되었습니다.</strong><span>AI 조치 페이지로 이동하시겠습니까?</span></div><div><Button icon="arrow" onClick={moveToAiAction} tone="primary">AI 조치 페이지 이동</Button><Button onClick={dismissAnalysisToast}>나중에</Button></div></aside>}
  </div>
}
