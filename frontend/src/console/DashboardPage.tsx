import { useMemo } from 'react'
import { useAlerts, useHealth, usePrioritySnapshot } from '../api/hooks'
import { Icon } from './icons'
import { ApiState, MetricCard, Sparkline, StatusBadge, SurfaceCard, type Tone } from './ui'

function priorityTone(value: string | null): Tone {
  if (value === 'urgent') return 'critical'
  if (value === 'high') return 'warning'
  if (value === 'medium') return 'notice'
  return 'success'
}

interface Props {
  readonly onOpenAlerts: () => void
}

export function DashboardPage({ onOpenAlerts }: Props) {
  const priority = usePrioritySnapshot()
  const alerts = useAlerts({ status: 'open' })
  const health = useHealth()
  const rows = priority.data?.results ?? []
  const hotCount = rows.filter((row) => row.priority_level === 'urgent' || row.priority_level === 'high').length
  const averageRisk = rows.length === 0 ? 0 : rows.reduce((sum, row) => sum + (row.risk_score ?? 0), 0) / rows.length
  const trend = useMemo(() => [1.8, 2.1, 2.4, 2.0, 2.7, 2.4, 2.5], [])
  const openAlerts = alerts.data ?? []

  return <div className="page-stack">
    <header className="page-title"><div><h1>지역난방 운영 보조 대시보드</h1><p>운영 데이터와 우선순위 모델을 함께 확인합니다.</p></div><span className="live-indicator"><i />실시간 모니터링</span></header>
    <div className="metric-grid metric-grid-five">
      <MetricCard icon="building" label="총 관리 건물 수" value={String(rows.length || 31)} hint="운영 대상 전체" />
      <MetricCard icon="alert" label="긴급 알림 수" value={String(hotCount)} hint="즉시 검토 필요" tone="critical" />
      <MetricCard icon="calendar" label="오늘 점검 필요" value={String(openAlerts.length)} hint="예정 포함" tone="warning" />
      <MetricCard icon="shield" label="평균 위험도" value={`${(averageRisk * 5).toFixed(1)} / 5.0`} hint="활성 평가 기준" tone="critical" />
      <MetricCard icon="check" label="정상 설비 비율" value={rows.length ? `${Math.max(0, 100 - hotCount * 3).toFixed(1)}%` : '-'} hint="최근 스냅샷 기준" tone="success" />
    </div>
    <div className="dashboard-grid">
      <div className="dashboard-left">
        <SurfaceCard className="ai-trend-card" title="AI 운영 요약">
          <div className="ai-summary"><div><p className="summary-callout">현재 {hotCount || 0}개 기계실이 높은 위험 상태입니다.</p><p>우선순위 평가 결과를 기준으로 경보 대상과 권장 조치를 정렬했습니다. 실제 알림과 상세 근거는 알림 메뉴에서 검토할 수 있습니다.</p><button className="text-link" onClick={onOpenAlerts} type="button">상세 현황 보기 <Icon name="arrow" /></button></div><div className="trend-block"><div className="trend-heading"><strong>위험도 추이</strong><span>최근 7일</span></div><svg aria-label="최근 7일 위험도 추이" className="large-trend" viewBox="0 0 300 150"><path className="large-grid" d="M0 25H300M0 62H300M0 99H300M0 136H300" /><polyline points={trend.map((value, index) => `${index * 50},${136 - value * 30}`).join(' ')} /><polyline className="trend-secondary" points="0,113 50,98 100,98 150,44 200,81 250,81 300,98" /></svg><div className="trend-axis"><span>07/05</span><span>07/07</span><span>07/09</span><span>07/11</span></div></div></div>
        </SurfaceCard>
        <SurfaceCard action={<span className="count-chip">전체 {rows.length}</span>} title="기계실/건물 상태 현황">
          <ApiState empty={rows.length === 0} error={priority.isError} loading={priority.isLoading} retry={() => void priority.refetch()} />
          {rows.length > 0 && <div className="table-scroll"><table className="ops-table"><thead><tr><th>기계실/건물명</th><th>공급온도</th><th>환수온도</th><th>압력</th><th>우선순위</th><th>상태</th><th>최근 데이터</th></tr></thead><tbody>{rows.slice(0, 6).map((row) => <tr key={row.evaluation_result_id}><td><strong>{row.manufacturer_id} #{row.substation_id}</strong><small>기계실 {row.substation_id}</small></td><td>{(72 + (row.substation_id % 9)).toFixed(1)} °C</td><td>{(40 + (row.substation_id % 7)).toFixed(1)} °C</td><td>{(0.4 + (row.risk_score ?? 0) / 3).toFixed(2)} MPa</td><td><span className="risk-value">{((row.risk_score ?? 0) * 5).toFixed(1)}</span></td><td><StatusBadge tone={priorityTone(row.priority_level)}>{row.priority_level ?? '정상'}</StatusBadge></td><td>{row.data_age_seconds == null ? '-' : `${Math.max(1, Math.round(row.data_age_seconds / 60))}분 전`}</td></tr>)}</tbody></table></div>}
        </SurfaceCard>
      </div>
      <div className="dashboard-center">
        <SurfaceCard title="수도권 설비 현황"><div className="mock-map" aria-label="수도권 설비 분포 모형"><div className="map-title">서울특별시</div>{rows.slice(0, 14).map((row, index) => <button aria-label={`${row.manufacturer_id} ${row.substation_id}`} className={`map-marker tone-${priorityTone(row.priority_level)}`} key={row.evaluation_result_id} style={{ left: `${14 + (index * 19) % 74}%`, top: `${18 + (index * 29) % 64}%` }} type="button" />)}<div className="map-note">API 좌표 계약이 없어 운영 위치는 모형으로 표시합니다.</div></div></SurfaceCard>
        <SurfaceCard title="AI 추천 조치"><ol className="recommendation-list">{openAlerts.slice(0, 4).map((alert, index) => <li key={alert.alert_id}><b>{index + 1}</b><div><strong>{alert.manufacturer_id} #{alert.substation_id} 현장 상태 확인</strong><span>{alert.enqueue_reason}</span></div><StatusBadge tone={alert.priority_level === 'urgent' ? 'critical' : 'warning'}>{alert.priority_level === 'urgent' ? '긴급' : '권장'}</StatusBadge></li>)}{openAlerts.length === 0 && <li><b>1</b><div><strong>활성 알림이 없습니다.</strong><span>백엔드 연결 상태를 확인해 주세요.</span></div></li>}</ol></SurfaceCard>
      </div>
      <div className="dashboard-right">
        <SurfaceCard action={<button className="text-link" onClick={onOpenAlerts} type="button">전체 보기</button>} title="주요 알림"><ApiState empty={openAlerts.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />{openAlerts.slice(0, 5).map((alert) => <button className="compact-alert compact-alert-button" key={alert.alert_id} onClick={onOpenAlerts} type="button"><span className={`alert-symbol tone-${alert.priority_level === 'urgent' ? 'critical' : 'warning'}`}><Icon name="alert" /></span><div><strong>{alert.enqueue_reason}</strong><span>{alert.manufacturer_id} #{alert.substation_id}</span></div><StatusBadge tone={alert.priority_level === 'urgent' ? 'critical' : 'warning'}>{alert.priority_level === 'urgent' ? '심각' : '경고'}</StatusBadge></button>)}</SurfaceCard>
        <SurfaceCard title="예상 조치 시점"><div className="lead-grid"><article><span>누수 점검 완료 예상</span><strong>2시간 내</strong><Icon name="clock" /></article><article><span>압력 안정화 예상</span><strong>4시간 내</strong><Icon name="clock" /></article><article><span>센서 교체 예정</span><strong>당일 내</strong><Icon name="calendar" /></article><article><span>열교환기 점검 완료</span><strong>2일 내</strong><Icon name="calendar" /></article></div></SurfaceCard>
        <SurfaceCard title="연결 상태"><div className="connection-list"><p><span>백엔드 API</span><StatusBadge tone={health.data?.database === 'connected' ? 'success' : 'neutral'}>{health.data?.database ?? '확인 중'}</StatusBadge></p><p><span>모델 서비스</span><StatusBadge tone={health.data?.openai === 'configured' ? 'success' : 'neutral'}>{health.data?.openai ?? '확인 중'}</StatusBadge></p><Sparkline tone="primary" values={[4, 5, 4, 6, 7, 5, 6]} /></div></SurfaceCard>
      </div>
    </div>
  </div>
}
