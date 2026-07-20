import { useEffect, useRef, useState } from 'react'
import { useAlerts, usePrioritySnapshot } from '../api/hooks'
import type { AlertSummary, PriorityEvaluationResult } from '../api/contracts'
import { complexById } from '../domain/model'
import { complexes } from '../data/complexes'
import MapView from '../map/MapView'
import { scenarioPriorityRows } from '../scenario/scenarioData'
import { useScenario } from '../scenario/useScenario'
import type { ResolvedTheme } from './useThemePreference'
import { Icon, type IconName } from './icons'
import SensorFlowCard from './SensorFlowCard'
import { useOperations } from './OperationsContext'
import { ApiState, HomeMetric, StatusBadge, SurfaceCard, type Tone } from './ui'

type AlertDisplayTone = Extract<Tone, 'critical' | 'warning' | 'primary'>
type DashboardPriorityBucket = 'urgent' | 'high' | 'medium' | 'low'

/**
 * 알림 표시 톤. 계약 priority_level(urgent|high)에는 '안내' 단계가 없어
 * 점검 예정성 알림만 안내(파랑)로 분류하는 표시 규칙이다(계약 변경 없음).
 */
function alertDisplayTone(alert: AlertSummary): AlertDisplayTone {
  if (alert.priority_level === 'urgent') return 'critical'
  if (alert.enqueue_reason.includes('점검 예정')) return 'primary'
  return 'warning'
}

const ALERT_TONE_LABEL: Record<AlertDisplayTone, string> = { critical: '긴급', warning: '경고', primary: '안내' }
const ALERT_TONE_ICON: Record<AlertDisplayTone, IconName> = { critical: 'alert', warning: 'warning', primary: 'info' }

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
  const alerts = useAlerts({ status: 'open' })
  const mapWrapRef = useRef<HTMLDivElement>(null)
  const [selectedGraphSubstationId, setSelectedGraphSubstationId] = useState<number | null>(null)
  const [visibleIncidentAlertIds, setVisibleIncidentAlertIds] = useState<readonly string[]>([])

  const faultMode = scenario.state.mode === 'fault'
  const incidentActive = faultMode && scenario.state.incidentState === 'incident-active'
  const apiRows = priority.data?.results ?? []
  const rows = faultMode ? (incidentActive ? scenarioPriorityRows(scenario.alerts) : []) : apiRows
  const resultBySubstationId = new Map(rows.map((row) => [row.substation_id, row]))
  const defaultBucket: DashboardPriorityBucket = faultMode ? 'low' : 'medium'
  const dashboardBuckets = complexes.map((complex) => dashboardPriorityBucket(resultBySubstationId.get(complex.id), defaultBucket))
  const urgent = dashboardBuckets.filter((bucket) => bucket === 'urgent').length
  const high = dashboardBuckets.filter((bucket) => bucket === 'high').length
  const medium = dashboardBuckets.filter((bucket) => bucket === 'medium').length
  const normal = dashboardBuckets.filter((bucket) => bucket === 'low').length
  const buildingCount = complexes.length
  const openAlerts = alerts.data ?? []
  const incidentAlerts = [...scenario.alerts].sort((left, right) => {
    const priorityOrder = (left.priority === 'urgent' ? 0 : 1) - (right.priority === 'urgent' ? 0 : 1)
    return priorityOrder || left.detectedAt.localeCompare(right.detectedAt)
  })
  const incidentAlertKey = incidentAlerts.map((alert) => alert.id).join('|')
  const visibleIncidentAlerts = incidentAlerts.filter((alert) => visibleIncidentAlertIds.includes(alert.id) && !scenario.state.dismissedIncidentAlertIds.includes(alert.id))

  const shownAlerts = openAlerts.slice(0, 5)

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
          <MapView error={faultMode ? false : priority.isError} loading={faultMode ? false : priority.isLoading} missingStatus={faultMode ? 'low' : 'missing'} onClearSelection={clearMapSelection} onSelectComplex={selectMapComplex} results={rows} theme={theme} />
          <button className="map-expand" onClick={openFullMap} type="button"><Icon name="expand" />전체 지도 보기</button>
        </div>
        </SurfaceCard>

        <SurfaceCard action={<button className="text-link" onClick={() => onOpenAlerts()} type="button">자세히 보기</button>} className="home-alerts" title="주요 알림">
        {!faultMode && <ApiState empty={openAlerts.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />}
        {faultMode && !incidentActive && <div className="home-alert-empty"><Icon name="shield" /><div><strong>현재 주요 알림 없음</strong><span>모든 설비를 정상 모니터링 중입니다.</span></div></div>}
        {faultMode && incidentActive ? scenario.alerts.map((alert) => (
          <button aria-pressed={selectedGraphSubstationId === alert.substationId} className={`home-alert-row ${selectedGraphSubstationId === alert.substationId ? 'selected' : ''}`.trim()} key={alert.id} onClick={() => { setSelectedGraphSubstationId(alert.substationId); scenario.selectAlert(alert.id); scenario.selectSubstation(alert.substationId); operations.selectAsset(alert.substationId) }} type="button">
            <span className={`alert-symbol tone-${alert.priority === 'urgent' ? 'critical' : 'warning'}`}><Icon name={alert.priority === 'urgent' ? 'alert' : 'warning'} /></span>
            <div><strong>{complexById.get(alert.substationId)?.name ?? `기계실 ${alert.substationId}`}</strong><small>기계실 {alert.substationId} · {alert.title}</small></div>
            <div className="home-alert-side"><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority}</StatusBadge></div>
          </button>
        )) : !faultMode && (() => {
          return shownAlerts.map((alert: AlertSummary) => {
            const tone = alertDisplayTone(alert)
            const complexName = alert.substation_id != null ? complexById.get(alert.substation_id)?.name : undefined
            const selected = alert.substation_id != null && selectedGraphSubstationId === alert.substation_id
            return (
              <button aria-pressed={selected} className={`home-alert-row ${selected ? 'selected' : ''}`.trim()} key={alert.alert_id} onClick={() => { if (alert.substation_id != null) { setSelectedGraphSubstationId(alert.substation_id); operations.selectAsset(alert.substation_id); scenario.selectSubstation(alert.substation_id) } }} type="button">
                <span className={`alert-symbol tone-${tone}`}><Icon name={ALERT_TONE_ICON[tone]} /></span>
                <div><strong>{complexName ?? alert.manufacturer_id ?? '알 수 없는 건물'}</strong><small>기계실 {alert.substation_id ?? '-'} · {alert.enqueue_reason}</small></div>
                <div className="home-alert-side"><StatusBadge tone={tone}>{ALERT_TONE_LABEL[tone]}</StatusBadge><span className="ack-deadline">anomaly 기반</span></div>
              </button>
            )
          })
        })()}
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
