import { useRef, useState } from 'react'
import { useAlerts, usePrioritySnapshot } from '../api/hooks'
import type { AlertSummary, PriorityEvaluationResult } from '../api/contracts'
import { complexById } from '../domain/model'
import MapView from '../map/MapView'
import { SCENARIO_PRIORITY_ROWS } from '../scenario/scenarioData'
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

  const faultMode = scenario.state.mode === 'fault'
  const incidentActive = faultMode && scenario.state.incidentState === 'incident-active'
  const apiRows = priority.data?.results ?? []
  const rows = faultMode ? (incidentActive ? SCENARIO_PRIORITY_ROWS : []) : apiRows
  const urgent = rows.filter((row: PriorityEvaluationResult) => row.freshness_status === 'fresh' && row.priority_level === 'urgent').length
  const high = rows.filter((row: PriorityEvaluationResult) => row.freshness_status === 'fresh' && row.priority_level === 'high').length
  const buildingCount = faultMode ? 31 : rows.length
  const normal = Math.max(0, buildingCount - urgent - high)
  const openAlerts = alerts.data ?? []
  const alertCount = faultMode ? (incidentActive ? scenario.alerts.length : 0) : openAlerts.length
  const scenarioAlert = scenario.alerts.find((alert) => alert.id === scenario.state.selectedAlertId) ?? scenario.alerts[0]
  const priorityAlert = scenario.alerts[0]

  const shownAlerts = openAlerts.slice(0, 5)
  const selectedAlert = shownAlerts.find((alert: AlertSummary) => alert.alert_id === selectedAlertId) ?? null

  const openFullMap = () => {
    void mapWrapRef.current?.requestFullscreen?.()
  }
  const selectMapComplex = (substationId: number) => {
    const matchedAlert = scenario.alerts.find((alert) => alert.substationId === substationId)
    if (matchedAlert) scenario.selectAlert(matchedAlert.id)
  }
  const popupComplex = priorityAlert ? complexById.get(priorityAlert.substationId) : null

  return <div className="page-stack dashboard-home">
    <div className="metric-grid metric-grid-four">
      <HomeMetric icon="building" label="전체 관리 건물 수" tone="primary" unit="개소" value={String(buildingCount)}>
        <span className="dot-stat ok">정상 <b>{normal}</b></span>
        <span className="dot-stat warn">주의 <b>{high}</b></span>
        <span className="dot-stat danger">위험 <b>{urgent}</b></span>
      </HomeMetric>
      <HomeMetric icon="alert" label="긴급" tone="critical" unit="개소" value={String(urgent)}>전일 대비 <b className="metric-delta">▲ 1</b></HomeMetric>
      <HomeMetric icon="warning" label="주의" tone="warning" unit="개소" value={String(high)}>전일 대비 <b className="metric-delta">▲ 1</b></HomeMetric>
      <HomeMetric icon="wrench" label="조치 필요" tone="primary" unit="건" value={String(alertCount)}>전일 대비 <b className="metric-delta">▲ 2</b></HomeMetric>
    </div>

    <div className="home-grid">
      <SurfaceCard
        action={<div className="map-legend"><span><i className="lg ok" />정상</span><span><i className="lg warn" />주의</span><span><i className="lg danger" />위험</span></div>}
        className="map-card"
        title="설비 위치 지도"
      >
        <div aria-label="설비 위치 지도" className="map-live" ref={mapWrapRef}>
          <MapView error={faultMode ? false : priority.isError} loading={faultMode ? false : priority.isLoading} onSelectComplex={selectMapComplex} results={rows} theme={theme} />
          {incidentActive && scenarioAlert && <div className="scenario-map-alert"><StatusBadge tone={scenarioAlert.priority === 'urgent' ? 'critical' : 'warning'}>{scenarioAlert.priority}</StatusBadge><div><strong>{scenarioAlert.facility} 이상</strong><span>경보 3건 동시 감지 · 최단 리드타임 4.9시간</span></div></div>}
          <button className="map-expand" onClick={openFullMap} type="button"><Icon name="expand" />전체 지도 보기</button>
        </div>
      </SurfaceCard>

      <SurfaceCard action={<button className="text-link" onClick={() => onOpenAlerts()} type="button">자세히 보기</button>} className="home-alerts" title="주요 알림">
        {!faultMode && <ApiState empty={openAlerts.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />}
        {faultMode && !incidentActive && <div className="home-alert-empty"><Icon name="shield" /><div><strong>운영 알림 없음</strong><span>센서 흐름을 정상 수신 중입니다.</span></div></div>}
        {faultMode && incidentActive ? scenario.alerts.map((alert) => (
          <button aria-pressed={scenario.state.selectedAlertId === alert.id} className={`home-alert-row ${scenario.state.selectedAlertId === alert.id ? 'selected' : ''}`.trim()} key={alert.id} onClick={() => scenario.selectAlert(alert.id)} type="button">
            <span className={`alert-symbol tone-${alert.priority === 'urgent' ? 'critical' : 'warning'}`}><Icon name={alert.priority === 'urgent' ? 'alert' : 'warning'} /></span>
            <div><strong>{alert.facility}</strong><small>{alert.title}</small></div>
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
                <div><strong>{complexName ?? alert.manufacturer_id} (substation {alert.substation_id ?? '-'})</strong><small>{alert.enqueue_reason}</small></div>
                <div className="home-alert-side"><StatusBadge tone={tone}>{ALERT_TONE_LABEL[tone]}</StatusBadge><span className="ack-deadline">{ackDeadlineLabel(tone, warningIndex)}</span></div>
              </button>
            )
          })
        })()}
      </SurfaceCard>
    </div>

    <SensorFlowCard />
    {faultMode && incidentActive && priorityAlert && scenario.state.incidentPopupVisible && <aside aria-label="우선순위 경보" aria-modal="false" className="scenario-incident-popup" role="dialog">
      <header><div><StatusBadge tone="critical">우선순위 1 · urgent</StatusBadge><strong>출동 판단이 필요한 이상 징후</strong></div><button aria-label="경보 팝업 닫기" onClick={scenario.dismissIncidentPopup} type="button"><Icon name="x" /></button></header>
      <div className="scenario-incident-location"><span>{popupComplex?.village ?? '세종시'} · {popupComplex?.name ?? `기계실 ${priorityAlert.substationId}`}</span><strong>{priorityAlert.facility}</strong></div>
      <p>{priorityAlert.title}</p>
      <footer><span>출동 제한 <b>{priorityAlert.leadTimeHours}시간</b></span><button onClick={() => { scenario.selectAlert(priorityAlert.id); scenario.dismissIncidentPopup(); onOpenAlerts(priorityAlert.id) }} type="button">알림 바로가기 <Icon name="arrow" /></button></footer>
    </aside>}
  </div>
}
