import { useEffect, useRef, useState } from 'react'
import { usePrioritySnapshot } from '../api/hooks'
import type { PriorityEvaluationResult } from '../api/contracts'
import { complexById } from '../domain/model'
import { complexes } from '../data/complexes'
import MapView from '../map/MapView'
import { scenarioPriorityRows } from '../scenario/scenarioData'
import { useScenario } from '../scenario/useScenario'
import type { ResolvedTheme } from './useThemePreference'
import { Icon } from './icons'
import SensorFlowCard from './SensorFlowCard'
import { useOperations } from './OperationsContext'
import { HomeMetric, StatusBadge, SurfaceCard } from './ui'

type DashboardPriorityBucket = 'urgent' | 'high' | 'medium' | 'low'

function dashboardPriorityBucket(result: PriorityEvaluationResult | undefined, defaultBucket: DashboardPriorityBucket): DashboardPriorityBucket {
  if (!result) return defaultBucket
  if (result.freshness_status !== 'fresh') return 'medium'
  const level = result.priority_level?.toLowerCase()
  if (level === 'urgent') return 'urgent'
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  return 'low'
}

interface Props {
  readonly onOpenAlerts: (alertId?: string) => void
  readonly theme: ResolvedTheme
}

export function DashboardPage({ onOpenAlerts, theme }: Props) {
  const scenario = useScenario()
  const operations = useOperations()
  const priority = usePrioritySnapshot()
  const mapWrapRef = useRef<HTMLDivElement>(null)
  const [selectedGraphSubstationId, setSelectedGraphSubstationId] = useState<number | null>(null)
  const [visibleIncidentAlertIds, setVisibleIncidentAlertIds] = useState<readonly string[]>([])

  const faultMode = scenario.state.mode === 'fault'
  const incidentActive = faultMode && scenario.state.incidentState === 'incident-active'
  // 정상 모드에서는 모든 설비를 정상(low)으로 표시한다(데모 기준). 고장 모드만 실제 우선순위를 반영한다.
  const rows = faultMode ? (incidentActive ? scenarioPriorityRows(scenario.alerts) : []) : []
  const resultBySubstationId = new Map(rows.map((row) => [row.substation_id, row]))
  const defaultBucket: DashboardPriorityBucket = 'low'
  const dashboardBuckets = faultMode
    ? complexes.map((complex) => dashboardPriorityBucket(resultBySubstationId.get(complex.id), defaultBucket))
    : complexes.map(() => 'low' as DashboardPriorityBucket)
  const urgent = dashboardBuckets.filter((bucket) => bucket === 'urgent').length
  const high = dashboardBuckets.filter((bucket) => bucket === 'high').length
  const medium = dashboardBuckets.filter((bucket) => bucket === 'medium').length
  const normal = dashboardBuckets.filter((bucket) => bucket === 'low').length
  const buildingCount = complexes.length
  const incidentAlerts = [...scenario.alerts]
    .sort((left, right) => right.modelResult.priorityScore - left.modelResult.priorityScore || left.id.localeCompare(right.id))
  const incidentAlertKey = incidentAlerts.map((alert) => alert.id).join('|')
  const visibleIncidentAlerts = incidentAlerts.filter((alert) => visibleIncidentAlertIds.includes(alert.id) && !scenario.state.dismissedIncidentAlertIds.includes(alert.id))

  const openFullMap = () => {
    void mapWrapRef.current?.requestFullscreen?.()
  }
  const selectMapComplex = (substationId: number) => {
    const selected = selectedGraphSubstationId !== substationId
    setSelectedGraphSubstationId(selected ? substationId : null)
    if (!selected) return
    operations.selectAsset(substationId)
    scenario.selectSubstation(substationId)
    const matchedAlert = scenario.alerts.find((alert) => alert.substationId === substationId)
    if (matchedAlert) scenario.selectAlert(matchedAlert.id)
  }
  const clearMapSelection = () => {
    setSelectedGraphSubstationId(null)
  }
  useEffect(() => {
    if (!faultMode || !incidentActive || !incidentAlertKey) {
      setVisibleIncidentAlertIds([])
      return undefined
    }
    const ids = incidentAlertKey.split('|')
    setVisibleIncidentAlertIds(ids.slice(0, 1))
    const timers = ids.slice(1).map((id, index) => window.setTimeout(() => {
      setVisibleIncidentAlertIds((current) => current.includes(id) ? current : [...current, id])
    }, (index + 1) * 1_000))
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [faultMode, incidentActive, incidentAlertKey])

  const dismissIncidentToast = (alertId: string) => {
    scenario.dismissIncidentAlert(alertId)
    setVisibleIncidentAlertIds((current) => current.filter((id) => id !== alertId))
  }

  return <div className="page-stack dashboard-home">
    <div className="metric-grid metric-grid-five">
      <HomeMetric icon="building" label="전체 건물" tone="primary" value={String(buildingCount)} />
      <HomeMetric icon="alert" label="긴급" tone="critical" value={String(urgent)} />
      <HomeMetric icon="warning" label="주의" tone="warning" value={String(high)} />
      <HomeMetric icon="info" label="관찰" tone="notice" value={String(medium)} />
      <HomeMetric icon="shield" label="정상" tone="success" value={String(normal)} />
    </div>

    <div className="home-grid">
      <div className="home-left">
        <SurfaceCard
        action={<div className="map-legend"><span><i className="lg danger" />긴급</span><span><i className="lg warn" />주의</span><span><i className="lg notice" />관찰</span><span><i className="lg ok" />정상</span></div>}
        className="map-card"
        title="MAP"
      >
        <div aria-label="설비 위치 지도" className="map-live" ref={mapWrapRef}>
          <MapView error={faultMode ? false : priority.isError} loading={faultMode ? false : priority.isLoading} missingStatus="low" onClearSelection={clearMapSelection} onSelectComplex={selectMapComplex} results={rows} theme={theme} />
          <button className="map-expand" onClick={openFullMap} type="button"><Icon name="expand" />전체 지도 보기</button>
        </div>
        </SurfaceCard>

        <SurfaceCard action={<button className="text-link" onClick={() => onOpenAlerts()} type="button">자세히 보기</button>} className="home-alerts" title="주요 알림">
        {(!faultMode || !incidentActive) && <div className="home-alert-empty"><Icon name="shield" /><div><strong>현재 주요 알림 없음</strong><span>모든 설비를 정상 모니터링 중입니다.</span></div></div>}
        {faultMode && incidentActive ? incidentAlerts.map((alert) => (
          <button aria-pressed={selectedGraphSubstationId === alert.substationId} className={`home-alert-row ${selectedGraphSubstationId === alert.substationId ? 'selected' : ''}`.trim()} key={alert.id} onClick={() => { setSelectedGraphSubstationId(alert.substationId); scenario.selectAlert(alert.id); scenario.selectSubstation(alert.substationId); operations.selectAsset(alert.substationId) }} type="button">
            <span className={`alert-symbol tone-${alert.priority === 'urgent' ? 'critical' : 'warning'}`}><Icon name={alert.priority === 'urgent' ? 'alert' : 'warning'} /></span>
            <div><strong>{complexById.get(alert.substationId)?.name ?? `기계실 ${alert.substationId}`}</strong><small>기계실 {alert.substationId} · {alert.title}</small></div>
            <div className="home-alert-side"><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority}</StatusBadge></div>
          </button>
        )) : null}
        </SurfaceCard>
      </div>
      <SensorFlowCard substationId={selectedGraphSubstationId} />
    </div>
    {faultMode && incidentActive && visibleIncidentAlerts.length > 0 && <div aria-live="polite" className="scenario-incident-toasts">
      {visibleIncidentAlerts.map((alert) => {
        const rank = incidentAlerts.findIndex((candidate) => candidate.id === alert.id) + 1
        const complex = complexById.get(alert.substationId)
        const tone = alert.priority === 'urgent' ? 'critical' : 'warning'
        return <aside aria-label={`우선순위 ${rank} 경보`} className="scenario-incident-toast" key={alert.id} role="status">
          <header><div><StatusBadge tone={tone}>우선순위 {rank} · {alert.priority}</StatusBadge><strong>{alert.title}</strong></div><button aria-label={`우선순위 ${rank} 경보 닫기`} onClick={() => dismissIncidentToast(alert.id)} type="button"><Icon name="x" /></button></header>
          <div className="scenario-incident-location"><span>{complex?.village ?? '세종시'} · {complex?.name ?? `기계실 ${alert.substationId}`}</span><strong>{alert.facility}</strong></div>
          <footer><div><button onClick={() => dismissIncidentToast(alert.id)} type="button">나중에 보기</button><button onClick={() => { scenario.selectAlert(alert.id); operations.selectAsset(alert.substationId); dismissIncidentToast(alert.id); onOpenAlerts(alert.id) }} type="button">알림 상세 열기 <Icon name="arrow" /></button></div></footer>
        </aside>
      })}
    </div>}
  </div>
}
