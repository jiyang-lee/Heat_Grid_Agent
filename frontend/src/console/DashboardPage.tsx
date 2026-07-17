import { useEffect, useRef, useState } from 'react'
import { useAlerts, usePrioritySnapshot } from '../api/hooks'
import type { AlertSummary, PriorityEvaluationResult } from '../api/contracts'
import { complexById } from '../domain/model'
import MapView from '../map/MapView'
import { scenarioPriorityRows } from '../scenario/scenarioData'
import { useScenario } from '../scenario/useScenario'
import type { ResolvedTheme } from './useThemePreference'
import { Icon, type IconName } from './icons'
import SensorFlowCard from './SensorFlowCard'
import { ApiState, HomeMetric, StatusBadge, SurfaceCard, type Tone } from './ui'

type AlertDisplayTone = Extract<Tone, 'critical' | 'warning' | 'primary'>

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

/** 확인 제한시간. SLA 계약이 없어 톤·노출 순서 기반 고정 규칙으로 표시한다(데모). */
const WARNING_SLA_MINUTES = [15, 20, 30] as const
function ackDeadlineLabel(tone: AlertDisplayTone, warningIndex: number): string {
  if (tone === 'critical') return '5분 내 확인'
  if (tone === 'primary') return '2시간 내 확인'
  return `${WARNING_SLA_MINUTES[Math.min(warningIndex, WARNING_SLA_MINUTES.length - 1)]}분 내 확인`
}

interface Props {
  readonly onOpenAlerts: (alertId?: string) => void
  readonly theme: ResolvedTheme
}

export function DashboardPage({ onOpenAlerts, theme }: Props) {
  const scenario = useScenario()
  const priority = usePrioritySnapshot()
  const alerts = useAlerts({ status: 'open' })
  const mapWrapRef = useRef<HTMLDivElement>(null)
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null)
  const [visibleIncidentAlertIds, setVisibleIncidentAlertIds] = useState<readonly string[]>([])

  const faultMode = scenario.state.mode === 'fault'
  const incidentActive = faultMode && scenario.state.incidentState === 'incident-active'
  const apiRows = priority.data?.results ?? []
  const rows = faultMode ? (incidentActive ? scenarioPriorityRows(scenario.alerts) : []) : apiRows
  const urgent = rows.filter((row: PriorityEvaluationResult) => row.freshness_status === 'fresh' && row.priority_level === 'urgent').length
  const high = rows.filter((row: PriorityEvaluationResult) => row.freshness_status === 'fresh' && row.priority_level === 'high').length
  const buildingCount = faultMode ? 31 : rows.length
  const normal = Math.max(0, buildingCount - urgent - high)
  const openAlerts = alerts.data ?? []
  const incidentAlerts = [...scenario.alerts].sort((left, right) => {
    const priorityOrder = (left.priority === 'urgent' ? 0 : 1) - (right.priority === 'urgent' ? 0 : 1)
    return priorityOrder || left.leadTimeHours - right.leadTimeHours
  })
  const incidentAlertKey = incidentAlerts.map((alert) => alert.id).join('|')
  const visibleIncidentAlerts = incidentAlerts.filter((alert) => visibleIncidentAlertIds.includes(alert.id) && !scenario.state.dismissedIncidentAlertIds.includes(alert.id))

  const shownAlerts = openAlerts.slice(0, 5)
  const selectedAlert = shownAlerts.find((alert: AlertSummary) => alert.alert_id === selectedAlertId) ?? null

  const openFullMap = () => {
    void mapWrapRef.current?.requestFullscreen?.()
  }
  const selectMapComplex = (substationId: number) => {
    const matchedAlert = scenario.alerts.find((alert) => alert.substationId === substationId)
    if (matchedAlert) scenario.selectAlert(matchedAlert.id)
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
      <HomeMetric icon="building" label="건물 수" tone="primary" value={String(buildingCount)} />
      <HomeMetric icon="alert" label="긴급" tone="critical" value={String(urgent)} />
      <HomeMetric icon="warning" label="주의" tone="warning" value={String(high)} />
      <HomeMetric icon="shield" label="정상" tone="success" value={String(normal)} />
      <HomeMetric icon="wrench" label="정기 점검" tone="primary" value="0" />
    </div>

    <div className="home-grid">
      <div className="home-left">
        <SurfaceCard
        action={<div className="map-legend"><span><i className="lg danger" />긴급</span><span><i className="lg warn" />주의</span><span><i className="lg ok" />정상</span></div>}
        className="map-card"
        title="MAP"
      >
        <div aria-label="설비 위치 지도" className="map-live" ref={mapWrapRef}>
          <MapView error={faultMode ? false : priority.isError} loading={faultMode ? false : priority.isLoading} onSelectComplex={selectMapComplex} results={rows} theme={theme} />
          <button className="map-expand" onClick={openFullMap} type="button"><Icon name="expand" />전체 지도 보기</button>
        </div>
        </SurfaceCard>

        <SurfaceCard action={<button className="text-link" onClick={() => onOpenAlerts()} type="button">자세히 보기</button>} className="home-alerts" title="주요 알림">
        {!faultMode && <ApiState empty={openAlerts.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />}
        {faultMode && !incidentActive && <div className="home-alert-empty"><Icon name="shield" /><div><strong>운영 알림 없음</strong><span>센서 흐름을 정상 수신 중입니다.</span></div></div>}
        {faultMode && incidentActive ? scenario.alerts.map((alert) => (
          <button aria-pressed={scenario.state.selectedAlertId === alert.id} className={`home-alert-row ${scenario.state.selectedAlertId === alert.id ? 'selected' : ''}`.trim()} key={alert.id} onClick={() => scenario.selectAlert(alert.id)} type="button">
            <span className={`alert-symbol tone-${alert.priority === 'urgent' ? 'critical' : 'warning'}`}><Icon name={alert.priority === 'urgent' ? 'alert' : 'warning'} /></span>
            <div><strong>{complexById.get(alert.substationId)?.name ?? `기계실 ${alert.substationId}`}</strong><small>기계실 {alert.substationId} · {alert.title}</small></div>
            <div className="home-alert-side"><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority}</StatusBadge><span className="ack-deadline">{alert.leadTimeHours}시간</span></div>
          </button>
        )) : !faultMode && (() => {
          let warningIndex = -1
          return shownAlerts.map((alert: AlertSummary) => {
            const tone = alertDisplayTone(alert)
            if (tone === 'warning') warningIndex += 1
            const complexName = alert.substation_id != null ? complexById.get(alert.substation_id)?.name : undefined
            const selected = selectedAlert?.alert_id === alert.alert_id
            return (
              <button aria-pressed={selected} className={`home-alert-row ${selected ? 'selected' : ''}`.trim()} key={alert.alert_id} onClick={() => setSelectedAlertId(alert.alert_id)} type="button">
                <span className={`alert-symbol tone-${tone}`}><Icon name={ALERT_TONE_ICON[tone]} /></span>
                <div><strong>{complexName ?? alert.manufacturer_id ?? '알 수 없는 건물'}</strong><small>기계실 {alert.substation_id ?? '-'} · {alert.enqueue_reason}</small></div>
                <div className="home-alert-side"><StatusBadge tone={tone}>{ALERT_TONE_LABEL[tone]}</StatusBadge><span className="ack-deadline">{ackDeadlineLabel(tone, warningIndex)}</span></div>
              </button>
            )
          })
        })()}
        </SurfaceCard>
      </div>
      <SensorFlowCard />
    </div>
    {faultMode && incidentActive && visibleIncidentAlerts.length > 0 && <div aria-live="polite" className="scenario-incident-toasts">
      {visibleIncidentAlerts.map((alert) => {
        const rank = incidentAlerts.findIndex((candidate) => candidate.id === alert.id) + 1
        const complex = complexById.get(alert.substationId)
        const tone = alert.priority === 'urgent' ? 'critical' : 'warning'
        return <aside aria-label={`우선순위 ${rank} 경보`} className="scenario-incident-toast" key={alert.id} role="status">
          <header><div><StatusBadge tone={tone}>우선순위 {rank} · {alert.priority}</StatusBadge><strong>{alert.title}</strong></div><button aria-label={`우선순위 ${rank} 경보 닫기`} onClick={() => dismissIncidentToast(alert.id)} type="button"><Icon name="x" /></button></header>
          <div className="scenario-incident-location"><span>{complex?.village ?? '세종시'} · {complex?.name ?? `기계실 ${alert.substationId}`}</span><strong>{alert.facility}</strong></div>
          <footer><span>고장 예상 시간 <b>{alert.leadTimeHours}시간</b></span><button onClick={() => { scenario.selectAlert(alert.id); dismissIncidentToast(alert.id); onOpenAlerts(alert.id) }} type="button">알림 바로가기 <Icon name="arrow" /></button></footer>
        </aside>
      })}
    </div>}
  </div>
}
