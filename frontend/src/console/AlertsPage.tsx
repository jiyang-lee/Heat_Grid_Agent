import { useMemo, useState } from 'react'
import type { AlertSummary } from '../api/contracts'
import { useAckAlert, useAlerts, useCreateAgentRun, useResolveAlert } from '../api/hooks'
import { complexNameOf } from '../domain/model'
import { alertDetail, sensorTrend } from './mockViewData'
import { Button, ApiState, HomeMetric, Sparkline, StatusBadge, SurfaceCard, type Tone } from './ui'

function alertTone(alert: AlertSummary): Tone {
  return alert.priority_level === 'urgent' ? 'critical' : 'warning'
}

interface Props {
  readonly onRunCreated: (runId: string) => void
}

export function AlertsPage({ onRunCreated }: Props) {
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checked, setChecked] = useState<readonly string[]>([])
  const alerts = useAlerts({ status: 'all' })
  const ack = useAckAlert()
  const resolve = useResolveAlert()
  const createRun = useCreateAgentRun()
  const rows = useMemo(() => (alerts.data ?? []).filter((alert) => `${complexNameOf(alert.substation_id, alert.manufacturer_id)} ${alert.manufacturer_id} ${alert.substation_id} ${alert.enqueue_reason}`.toLowerCase().includes(search.toLowerCase())), [alerts.data, search])
  const selected = rows.find((alert) => alert.alert_id === selectedId) ?? rows[0] ?? null
  const toggleChecked = (id: string) => setChecked((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
  const acknowledge = () => { if (selected) ack.mutate({ alertId: selected.alert_id, ackedBy: 'ops-manager' }) }
  const closeAlert = () => { if (selected && window.confirm('선택한 알림을 종결할까요?')) resolve.mutate({ alertId: selected.alert_id, ackedBy: 'ops-manager' }) }
  const startAgentRun = () => {
    if (!selected) return
    createRun.mutate({ alertId: selected.alert_id, requestedBy: 'ops-manager', reason: '운영 콘솔에서 작업지시서 생성을 요청했습니다.' }, { onSuccess: (run) => onRunCreated(run.run_id) })
  }
  const metrics = { urgent: rows.filter((alert) => alert.priority_level === 'urgent').length, acknowledged: rows.filter((alert) => alert.status === 'acked').length, resolved: rows.filter((alert) => alert.status === 'resolved').length }

  return <div className="page-stack alert-page">
    <header className="page-title"><div><h1>알림</h1><p>우선순위 알림을 검토하고 조치 흐름을 관리합니다.</p></div></header>
    <div className="metric-grid metric-grid-five">
      <HomeMetric icon="alert" label="전체 알림" tone="primary" unit="건" value={String(rows.length)}>최근 24시간</HomeMetric>
      <HomeMetric icon="shield" label="심각" tone="critical" unit="건" value={String(metrics.urgent)}>즉시 조치 필요</HomeMetric>
      <HomeMetric icon="alert" label="경고" tone="warning" unit="건" value={String(Math.max(0, rows.length - metrics.urgent))}>조치 권장</HomeMetric>
      <HomeMetric icon="clock" label="확인됨" tone="primary" unit="건" value={String(metrics.acknowledged)}>담당자 배정 완료</HomeMetric>
      <HomeMetric icon="check" label="오늘 해결 완료" tone="success" unit="건" value={String(metrics.resolved)}>최근 24시간</HomeMetric>
    </div>
    <div className="alert-layout"><div className="alert-main"><SurfaceCard title="알림 목록"><div className="filter-bar"><label><span>기간</span><select defaultValue="week"><option value="week">최근 7일</option></select></label><label><span>심각도</span><select defaultValue="all"><option value="all">전체</option><option value="urgent">심각</option><option value="high">경고</option></select></label><label className="filter-search"><span>알림 검색</span><input onChange={(event) => setSearch(event.target.value)} placeholder="건물명, 알림 유형, 내용 검색" value={search} /></label></div><ApiState empty={rows.length === 0} error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />{rows.length > 0 && <div className="table-scroll"><table className="ops-table alert-table"><thead><tr><th><input aria-label="전체 알림 선택" checked={checked.length === rows.length} onChange={() => setChecked(checked.length === rows.length ? [] : rows.map((row) => row.alert_id))} type="checkbox" /></th><th>심각도</th><th>알림 유형</th><th>건물/기계실</th><th>발생 시간</th><th>상태</th><th>담당자</th></tr></thead><tbody>{rows.map((alert) => <tr className={selected?.alert_id === alert.alert_id ? 'selected-row' : ''} key={alert.alert_id} onClick={() => setSelectedId(alert.alert_id)}><td onClick={(event) => event.stopPropagation()}><input aria-label={`${alert.alert_id} 선택`} checked={checked.includes(alert.alert_id)} onChange={() => toggleChecked(alert.alert_id)} type="checkbox" /></td><td><StatusBadge tone={alertTone(alert)}>{alert.priority_level === 'urgent' ? '심각' : '경고'}</StatusBadge></td><td>{alert.enqueue_reason}</td><td><strong>{complexNameOf(alert.substation_id, alert.manufacturer_id)}</strong><small>기계실 {alert.substation_id}</small></td><td>{new Date(alert.created_at).toLocaleString('ko-KR')}</td><td><StatusBadge tone={alert.status === 'resolved' ? 'success' : alert.status === 'acked' ? 'primary' : 'neutral'}>{alert.status === 'resolved' ? '종결' : alert.status === 'acked' ? '확인됨' : '미확인'}</StatusBadge></td><td>{alert.acked_by ?? '-'}</td></tr>)}</tbody></table></div>}<footer className="table-footer"><span>1 - {rows.length} / {rows.length}</span><div><Button icon="download">내보내기</Button><Button disabled={checked.length === 0}>선택 항목 처리</Button></div></footer></SurfaceCard></div>
      <aside className="alert-detail-pane"><SurfaceCard action={<Button aria-label="상세 닫기" icon="x" />} title="선택된 알림 상세">{selected ? <div className="detail-body"><div className="detail-title"><StatusBadge tone={alertTone(selected)}>{selected.priority_level === 'urgent' ? '심각' : '경고'}</StatusBadge><span>알림 ID {selected.alert_id}</span><h2>{selected.enqueue_reason}</h2><p>{complexNameOf(selected.substation_id, selected.manufacturer_id)} 기계실 {selected.substation_id} · {new Date(selected.created_at).toLocaleString('ko-KR')}</p></div><section><h3>AI 원인 요약</h3><p>{alertDetail.reason}</p></section><section><h3>센서 추이</h3><div className="sensor-summary"><div><span>차압</span><strong>0.12 bar</strong><i className="down">-0.18</i></div><div><span>보충수 유량</span><strong>1.84 m³/h</strong><i className="up">+1.32</i></div><div><span>공급온도</span><strong>76.1 °C</strong><i className="up">+1.6</i></div><div><span>환수온도</span><strong>52.1 °C</strong><i className="down">-0.4</i></div></div><div className="sensor-chart-head"><span>차압 추이 (최근 6시간)</span><button onClick={() => setSearch(complexNameOf(selected.substation_id, selected.manufacturer_id))} type="button">이 설비 알림만 보기</button></div><Sparkline tone="critical" values={sensorTrend} /></section><section><h3>최근 이벤트</h3><ol className="event-timeline">{alertDetail.events.map((event) => <li key={event.time}><i className={`tone-${event.tone}`} /><time>{event.time}</time><span>{event.text}</span><StatusBadge tone={event.tone}>{event.tone === 'critical' ? '심각' : event.tone === 'warning' ? '경고' : '정보'}</StatusBadge></li>)}</ol></section><section><h3>권장 조치</h3><p>{alertDetail.recommendation}</p><button className="text-link" onClick={startAgentRun} type="button">AI 분석과 상세 조치 가이드 생성</button></section>{createRun.isError && <p className="form-error">AI 실행을 시작하지 못했습니다. 백엔드 연결 상태를 확인해 주세요.</p>}<div className="detail-actions"><Button disabled={ack.isPending || selected.status !== 'open'} onClick={acknowledge} tone="primary">확인</Button><Button disabled={createRun.isPending} icon="document" onClick={startAgentRun} tone="primary">{createRun.isPending ? 'AI 실행 시작 중' : '작업지시서 생성'}</Button><Button onClick={acknowledge}>담당자 지정</Button><Button disabled={resolve.isPending || selected.status === 'resolved'} onClick={closeAlert} tone="danger">종결</Button></div></div> : <ApiState empty error={alerts.isError} loading={alerts.isLoading} retry={() => void alerts.refetch()} />}</SurfaceCard></aside>
    </div>
  </div>
}
