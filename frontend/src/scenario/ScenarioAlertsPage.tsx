import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../console/icons'
import { useOperations } from '../console/OperationsContext'
import { operationsDateTime } from '../console/operationsTime'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { useFinalTestPackages } from '../final-test/hooks'
import { ScenarioSensorEvidenceChart } from './ScenarioSensorEvidenceChart'
import type { ScenarioAlert, ScenarioTimelineAlert, SensorPoint } from './types'
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

function sensorEvidence(alert: ScenarioAlert, points: readonly SensorPoint[]): readonly [string, string, string] {
  const latest = points.at(-1)
  if (alert.substationId === 1) {
    const value = latest?.supply ?? 70.5
    return [`${value.toFixed(1)} °C`, '75~85 °C', `${(value - 76.4).toFixed(1)} °C`]
  }
  if (alert.affectedMetric === 'flow') {
    const value = latest?.flow ?? 86.0
    return [`${value.toFixed(1)} m³/h`, '100~130 m³/h', `${(value - 118.0).toFixed(1)} m³/h`]
  }
  if (alert.affectedMetric === 'supply') {
    const value = latest?.supply ?? 89.5
    return [`${value.toFixed(1)} °C`, '90.0 °C 이상 유지', `${(value - 94.0).toFixed(1)} °C`]
  }
  const value = latest?.returnTemperature ?? 34.1
  return [`${value.toFixed(1)} °C`, '40~50 °C', `${(value - 42.2).toFixed(1)} °C`]
}

function metricLabel(alert: ScenarioAlert): string {
  if (alert.affectedMetric === 'flow') return '유량'
  if (alert.affectedMetric === 'supply') return '공급온도'
  return '환수온도'
}

export function ScenarioAlertsPage({ initialAlertId, onConsumeInitialAlert, onOpenAiAction }: Props) {
  const scenario = useScenario()
  const operations = useOperations()
  const selectAsset = operations.selectAsset
  const { alertHistory, alerts, selectAlert, sensor, state } = scenario
  const [detailId, setDetailId] = useState<string | null>(null)
  const [scope, setScope] = useState<AlertScope>('active')
  const [search, setSearch] = useState('')
  const [priority, setPriority] = useState<'all' | ScenarioAlert['priority']>('all')
  const [analysisErrors, setAnalysisErrors] = useState<Readonly<Record<string, string>>>({})
  const demoPackages = useFinalTestPackages()
  const allAlerts = useMemo(() => [...alerts, ...alertHistory], [alertHistory, alerts])
  const source = scope === 'active' ? alerts : alertHistory
  const rows = useMemo(() => source.filter((alert) => {
    if (priority !== 'all' && alert.priority !== priority) return false
    return `${alert.title} ${alert.facility} ${alert.summary}`.toLowerCase().includes(search.toLowerCase())
  }), [priority, search, source])
  const selected = detailId ? allAlerts.find((alert) => alert.id === detailId) ?? null : null
  const selectedPoints = selected?.status === 'resolved'
    ? state.alertSensorSnapshots[selected.id] ?? sensor.state.points
    : sensor.state.points

  useEffect(() => {
    if (initialAlertId == null) return
    const initial = allAlerts.find((alert) => alert.id === initialAlertId)
    if (!initial) return
    selectAlert(initial.id)
    selectAsset(initial.substationId)
    setDetailId(initial.id)
    setScope(initial.status === 'active' ? 'active' : 'history')
    onConsumeInitialAlert()
  }, [allAlerts, initialAlertId, onConsumeInitialAlert, selectAlert, selectAsset])

  const lastSelectedStatusRef = useRef<Readonly<Record<string, ScenarioTimelineAlert['status']>>>({})
  useEffect(() => {
    if (selected == null) return
    const wasActive = lastSelectedStatusRef.current[selected.id] === 'active'
    lastSelectedStatusRef.current = { ...lastSelectedStatusRef.current, [selected.id]: selected.status }
    if (wasActive && selected.status !== 'active') setScope('history')
  }, [selected])

  const openDetail = (alert: ScenarioTimelineAlert) => {
    selectAlert(alert.id)
    selectAsset(alert.substationId)
    setDetailId(alert.id)
  }
  const openFinalTestPackage = (alert: ScenarioTimelineAlert) => {
    const demoPackage = demoPackages.data?.items.find((item) => item.alert_id === alert.id)
    if (!demoPackage) {
      setAnalysisErrors((current) => ({
        ...current,
        [alert.id]: demoPackages.isError ? '시연 DB를 불러오지 못했습니다. 다시 시도해 주세요.' : '시연 자료를 준비하는 중입니다.',
      }))
      if (demoPackages.isError) void demoPackages.refetch()
      return
    }
    setAnalysisErrors((current) => {
      const { [alert.id]: _removed, ...rest } = current
      return rest
    })
    onOpenAiAction(demoPackage.demo_id)
  }
  return <div className="page-stack alert-page scenario-alert-page">
    <div className={`alerts-workspace ${selected ? 'has-detail' : ''}`.trim()}>
      <SurfaceCard className="alerts-list-card" title="알림 이력">
        <div className="alerts-filter-bar">
          <label><span>표시 범위</span><select onChange={(event) => setScope(event.target.value === 'history' ? 'history' : 'active')} value={scope}><option value="active">활성 알림</option><option value="history">과거 알림</option></select></label>
          <label><span>우선순위</span><select onChange={(event) => setPriority(event.target.value === 'urgent' || event.target.value === 'high' ? event.target.value : 'all')} value={priority}><option value="all">전체</option><option value="urgent">긴급</option><option value="high">경고</option></select></label>
          <label className="filter-search"><span>알림 검색</span><input onChange={(event) => setSearch(event.target.value)} placeholder="설비명, 알림 내용 검색" value={search} /></label>
          <strong>{rows.length}건</strong>
        </div>
        {rows.length === 0 ? <div className="alerts-empty"><StatusBadge tone={scope === 'active' ? 'success' : 'neutral'}>{scope === 'active' ? '정상' : '이력 없음'}</StatusBadge><strong>{scope === 'active' ? '활성 알림이 없습니다.' : '조건에 맞는 과거 알림이 없습니다.'}</strong></div> : <div className="alerts-table-scroll"><table className="alerts-table"><thead><tr><th>상태</th><th>알림 내용</th><th>설비 / 위치</th><th>발생 시간</th><th>해소 시각</th><th aria-label="알림 작업" /></tr></thead><tbody>{rows.map((alert) => <tr className={selected?.id === alert.id ? 'selected' : ''} key={alert.id} onClick={() => openDetail(alert)}><td><span className={`alerts-severity-icon ${alert.priority}`}><Icon name={alert.priority === 'urgent' ? 'alert' : 'warning'} /></span><StatusBadge tone={alert.status === 'resolved' ? 'success' : priorityTone(alert)}>{alert.status === 'resolved' ? '조치 완료' : alert.priority === 'urgent' ? '긴급' : '경고'}</StatusBadge></td><td><strong>{alert.title}</strong></td><td><strong>기계실 {alert.substationId}</strong><small>{alert.facility}</small></td><td>{operationsDateTime(alert.detectedAt)}</td><td>{alert.status === 'resolved' ? operationsDateTime(alert.resolvedAt) : '-'}</td><td><button className="alerts-row-action" onClick={(event) => { event.stopPropagation(); openDetail(alert) }} type="button">상세</button></td></tr>)}</tbody></table></div>}
      </SurfaceCard>
      {selected && <SurfaceCard action={<button aria-label="상세 정보 닫기" className="scenario-detail-close" onClick={() => setDetailId(null)} type="button"><Icon name="x" /></button>} className="alerts-detail-card" title="상세 정보">
        <div className="scenario-detail-compact">
          <div className="scenario-detail-title"><StatusBadge tone={selected.status === 'resolved' ? 'success' : priorityTone(selected)}>{selected.status === 'resolved' ? '조치 완료' : selected.priority}</StatusBadge><strong>{selected.title}</strong><span>{selected.facility}</span></div>
          <div className="scenario-sensor-facts"><div><span>이상 센서</span><strong>{metricLabel(selected)}</strong></div><div><span>현재값</span><strong>{sensorEvidence(selected, selectedPoints)[0]}</strong></div><div><span>비교 기준</span><strong>{sensorEvidence(selected, selectedPoints)[1]}</strong></div><div><span>변화량</span><strong className="critical-text">{sensorEvidence(selected, selectedPoints)[2]}</strong></div></div>
          <ScenarioSensorEvidenceChart alert={selected} points={selectedPoints} />
          <section className="scenario-model-result"><h3>머신러닝 결과</h3><div><span>이상 점수</span><strong>{Math.round(selected.modelResult.anomalyScore * 100)}%</strong></div><div><span>위험 점수</span><strong>{Math.round(selected.modelResult.riskScore * 100)}%</strong></div><div><span>우선순위</span><strong>{selected.modelResult.priorityScore.toFixed(0)}점</strong></div><div><span>대응 긴급도</span><strong>{Math.round(selected.modelResult.leadtimeUrgencyScore * 100)}%</strong></div><p>{selected.modelResult.rationale}</p></section>
          <section className="scenario-reasoning-card"><h3>판단 근거</h3><p>{selected.summary}</p><ol className="scenario-reasoning"><li><strong>이상 감지</strong><span>{selected.evidence[0]}로 정상 범위 이탈이 확인되었습니다.</span></li><li><strong>모델 판단</strong><span>{selected.modelResult.rationale}</span></li><li><strong>현장 영향</strong><span>{selected.affectedMetric === 'flow' ? '열교환 성능 저하와 누수 확산 가능성을 확인해야 합니다.' : selected.affectedMetric === 'supply' ? '공급온도 설정과 열원·순환 계통의 운전 안정성에 영향을 줄 수 있습니다.' : '난방 순환 효율 저하와 세대 난방 불균형으로 확산될 수 있습니다.'}</span></li></ol>{analysisErrors[selected.id] && <p className="scenario-analysis-error" role="alert">{analysisErrors[selected.id]}</p>}<div className="scenario-detail-actions">{selected.status === 'active' && <Button disabled={demoPackages.isLoading || sensor.state.status === 'offline'} icon="activity" onClick={() => openFinalTestPackage(selected)} tone="primary">{demoPackages.isLoading ? '시연 자료 불러오는 중' : analysisErrors[selected.id] ? '시연 자료 다시 불러오기' : 'AI 조치 열기'}</Button>}</div></section>
        </div>
      </SurfaceCard>}
    </div>
  </div>
}
