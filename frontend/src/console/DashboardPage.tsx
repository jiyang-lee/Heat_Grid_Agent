import { useRef, type ReactNode } from 'react'
import { useAlerts, usePrioritySnapshot, useReviewTasks } from '../api/hooks'
import { complexById } from '../domain/model'
import MapView from '../map/MapView'
import type { ConsolePage } from './AppShell'
import { Icon, type IconName } from './icons'
import SensorFlowCard from './SensorFlowCard'
import { ApiState, StatusBadge, SurfaceCard } from './ui'

/** 알림 발생 시각의 상대 표기("n분 전"). 기한(SLA) 계약이 없어 발생 경과로 대체한다. */
function relativeTime(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return '방금 전'
  if (minutes < 60) return `${minutes}분 전`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}시간 전`
  return `${Math.round(hours / 24)}일 전`
}

interface HomeMetricProps {
  readonly icon: IconName
  readonly tone: string
  readonly label: string
  readonly value: string
  readonly unit: string
  readonly children: ReactNode
}

function HomeMetric({ icon, tone, label, value, unit, children }: HomeMetricProps) {
  return <article className="metric-card home-metric"><header><span className={`metric-icon tone-${tone}`}><Icon name={icon} /></span><p>{label}</p></header><strong>{value}<em>{unit}</em></strong><footer>{children}</footer></article>
}

interface Props {
  readonly onNavigate: (page: ConsolePage) => void
}

export function DashboardPage({ onNavigate }: Props) {
  const priority = usePrioritySnapshot()
  const alerts = useAlerts({ status: 'open' })
  const reviews = useReviewTasks('pending')
  const mapWrapRef = useRef<HTMLDivElement>(null)

  const rows = priority.data?.results ?? []
  // 위험=urgent, 주의=high (fresh 기준), 정상=나머지(지연·누락 포함).
  const urgent = rows.filter((row) => row.freshness_status === 'fresh' && row.priority_level === 'urgent').length
  const high = rows.filter((row) => row.freshness_status === 'fresh' && row.priority_level === 'high').length
  const normal = Math.max(0, rows.length - urgent - high)
  const openAlerts = alerts.data ?? []
  const pendingDocs = reviews.data?.length ?? 0

  const openFullMap = () => {
    void mapWrapRef.current?.requestFullscreen?.()
  }

  return <div className="page-stack">
    <header className="page-title"><div><h1>홈</h1><p>현재 시스템 요약과 주요 현황을 한눈에 확인하세요.</p></div></header>

    <div className="metric-grid metric-grid-five">
      <HomeMetric icon="building" label="전체 관리 건물 수" tone="primary" unit="개소" value={String(rows.length)}>
        <span className="dot-stat ok">정상 <b>{normal}</b></span>
        <span className="dot-stat warn">주의 <b>{high}</b></span>
        <span className="dot-stat danger">위험 <b>{urgent}</b></span>
      </HomeMetric>
      <HomeMetric icon="alert" label="긴급" tone="critical" unit="개소" value={String(urgent)}>즉시 확인 필요</HomeMetric>
      <HomeMetric icon="warning" label="주의" tone="warning" unit="개소" value={String(high)}>우선 점검 권장</HomeMetric>
      <HomeMetric icon="wrench" label="조치 필요" tone="primary" unit="건" value={String(openAlerts.length)}>열린 알림 기준</HomeMetric>
      <HomeMetric icon="document" label="대기 서류" tone="violet" unit="건" value={String(pendingDocs)}>운영자 검토 필요</HomeMetric>
    </div>

    <div className="home-grid">
      <SurfaceCard
        action={<div className="map-legend"><span><i className="lg ok" />정상</span><span><i className="lg warn" />주의</span><span><i className="lg danger" />위험</span><span><i className="lg stale" />지연</span></div>}
        className="map-card"
        title="설비 위치 지도"
      >
        <div aria-label="설비 위치 지도" className="map-live" ref={mapWrapRef}>
          <MapView error={priority.isError} loading={priority.isLoading} onSelectComplex={() => {}} results={rows} />
          <button className="map-expand" onClick={openFullMap} type="button"><Icon name="expand" />전체 지도 보기</button>
        </div>
      </SurfaceCard>

      <SurfaceCard action={<button className="text-link" onClick={() => onNavigate('alerts')} type="button">전체 보기</button>} className="home-alerts" title="주요 알림">
        <ApiState empty={openAlerts.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />
        {openAlerts.slice(0, 5).map((alert) => {
          const urgentAlert = alert.priority_level === 'urgent'
          const complexName = alert.substation_id != null ? complexById.get(alert.substation_id)?.name : undefined
          return (
            <div className="home-alert-row" key={alert.alert_id}>
              <span className={`alert-symbol tone-${urgentAlert ? 'critical' : 'warning'}`}><Icon name={urgentAlert ? 'alert' : 'warning'} /></span>
              <div><strong>{complexName ?? alert.manufacturer_id} (substation {alert.substation_id ?? '-'})</strong><small>{alert.enqueue_reason}</small></div>
              <div className="home-alert-side"><StatusBadge tone={urgentAlert ? 'critical' : 'warning'}>{urgentAlert ? '긴급' : '경고'}</StatusBadge><time>{relativeTime(alert.created_at)}</time></div>
            </div>
          )
        })}
      </SurfaceCard>
    </div>

    <SensorFlowCard />
  </div>
}
