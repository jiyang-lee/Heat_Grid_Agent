import { useRef, useState, type ReactNode } from 'react'
import { useAlerts, usePrioritySnapshot, useReviewTasks } from '../api/hooks'
import type { AlertSummary } from '../api/contracts'
import { complexById } from '../domain/model'
import MapView from '../map/MapView'
import { Icon, type IconName } from './icons'
import SensorFlowCard, { type SensorFacility } from './SensorFlowCard'
import { ApiState, StatusBadge, SurfaceCard, type Tone } from './ui'

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

interface HomeMetricProps {
  readonly icon: IconName
  readonly tone: string
  readonly label: string
  readonly value: string
  readonly unit: string
  /** 시안: 첫 카드만 좌측 정렬, 나머지는 중앙 정렬 */
  readonly centered?: boolean
  /** 시안: 단색 배경+흰 글리프(solid) vs 연한 배경(soft) */
  readonly iconStyle?: 'solid' | 'soft'
  readonly iconShape?: 'square' | 'circle'
  readonly children: ReactNode
}

function HomeMetric({ icon, tone, label, value, unit, centered = false, iconStyle = 'soft', iconShape = 'square', children }: HomeMetricProps) {
  const iconClass = `metric-icon tone-${tone}${iconStyle === 'solid' ? ' solid' : ''}${iconShape === 'circle' ? ' round' : ''}`
  return <article className={`metric-card home-metric${centered ? ' centered' : ''}`}><header><span className={iconClass}><Icon name={icon} /></span><p>{label}</p></header><strong>{value}<em>{unit}</em></strong><footer>{children}</footer></article>
}

interface Props {
  readonly onOpenAlerts: () => void
}

export function DashboardPage({ onOpenAlerts }: Props) {
  const priority = usePrioritySnapshot()
  const alerts = useAlerts({ status: 'open' })
  const reviews = useReviewTasks('pending')
  const mapWrapRef = useRef<HTMLDivElement>(null)
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null)

  const rows = priority.data?.results ?? []
  // 위험=urgent, 주의=high (fresh 기준), 정상=나머지(지연·누락 포함).
  const urgent = rows.filter((row) => row.freshness_status === 'fresh' && row.priority_level === 'urgent').length
  const high = rows.filter((row) => row.freshness_status === 'fresh' && row.priority_level === 'high').length
  const normal = Math.max(0, rows.length - urgent - high)
  const openAlerts = alerts.data ?? []
  const pendingDocs = reviews.data?.length ?? 0

  // 주요 알림 선택 → 센서 카드 컨텍스트. 미선택이면 카드가 전체(기계실 12) 기준을 보여준다.
  const shownAlerts = openAlerts.slice(0, 5)
  const selectedAlert = shownAlerts.find((alert) => alert.alert_id === selectedAlertId) ?? null
  const sensorFacility: SensorFacility | null = selectedAlert && selectedAlert.substation_id != null
    ? { id: selectedAlert.substation_id, name: complexById.get(selectedAlert.substation_id)?.name ?? selectedAlert.manufacturer_id ?? '미상 설비' }
    : null

  const openFullMap = () => {
    void mapWrapRef.current?.requestFullscreen?.()
  }

  return <div className="page-stack dashboard-home">
    <header className="page-title"><div><h1>홈</h1><p>현재 시스템 요약과 주요 현황을 한눈에 확인하세요.</p></div></header>

    <div className="metric-grid metric-grid-five">
      <HomeMetric icon="building" iconStyle="solid" label="전체 관리 건물 수" tone="primary" unit="개소" value={String(rows.length)}>
        <span className="dot-stat ok">정상 <b>{normal}</b></span>
        <span className="dot-stat warn">주의 <b>{high}</b></span>
        <span className="dot-stat danger">위험 <b>{urgent}</b></span>
      </HomeMetric>
      {/* 전일 대비 증감 계약이 없어 시안과 동일한 고정 문구로 표시한다(데모). */}
      <HomeMetric centered icon="alert" iconShape="circle" iconStyle="solid" label="긴급" tone="critical" unit="개소" value={String(urgent)}>전일 대비 <b className="metric-delta">▲ 1</b></HomeMetric>
      <HomeMetric centered icon="warning" iconShape="circle" iconStyle="solid" label="주의" tone="warning" unit="개소" value={String(high)}>전일 대비 <b className="metric-delta">▲ 1</b></HomeMetric>
      <HomeMetric centered icon="wrench" iconStyle="solid" label="조치 필요" tone="primary" unit="건" value={String(openAlerts.length)}>전일 대비 <b className="metric-delta">▲ 2</b></HomeMetric>
      <HomeMetric centered icon="document" label="대기 서류" tone="violet" unit="건" value={String(pendingDocs)}>운영자 검토 필요</HomeMetric>
    </div>

    <div className="home-grid">
      <SurfaceCard
        action={<div className="map-legend"><span><i className="lg ok" />정상</span><span><i className="lg warn" />주의</span><span><i className="lg danger" />위험</span></div>}
        className="map-card"
        title="설비 위치 지도"
      >
        <div aria-label="설비 위치 지도" className="map-live" ref={mapWrapRef}>
          <MapView error={priority.isError} loading={priority.isLoading} onSelectComplex={() => {}} results={rows} />
          <button className="map-expand" onClick={openFullMap} type="button"><Icon name="expand" />전체 지도 보기</button>
        </div>
      </SurfaceCard>

      <SurfaceCard action={<button className="text-link" onClick={onOpenAlerts} type="button">전체 보기</button>} className="home-alerts" title="주요 알림">
        <ApiState empty={openAlerts.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />
        {(() => {
          let warningIndex = -1
          return shownAlerts.map((alert) => {
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

    <SensorFlowCard facility={sensorFacility} />
  </div>
}
