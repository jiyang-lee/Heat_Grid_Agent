import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import type { ScenarioAlert, ScenarioReportStatus, WorkOrderVersion } from './types'

type AlertProgress = {
  readonly alert: ScenarioAlert
  readonly reportStatus: ScenarioReportStatus
  readonly workOrders: readonly WorkOrderVersion[]
}

export function ScenarioAiOverview({ alerts, onSelect, reportStatus, workOrders }: { readonly alerts: readonly ScenarioAlert[]; readonly onSelect: (id: string) => void; readonly reportStatus: ScenarioReportStatus; readonly workOrders: readonly WorkOrderVersion[] }) {
  const progress: readonly AlertProgress[] = alerts.map((alert) => ({ alert, reportStatus, workOrders }))
  return <div className="scenario-ai-overview"><header><div><h2>조치 계획 목록</h2><p>활성 경보를 선택해 출동 판단, 작업지시서와 보고서 진행 상태를 확인하세요.</p></div><StatusBadge tone="critical">활성 {alerts.length}건</StatusBadge></header><div className="scenario-ai-overview-grid">{progress.map(({ alert, reportStatus: currentReport, workOrders: currentOrders }) => <SurfaceCard key={alert.id} title={alert.priority === 'urgent' ? '긴급 조치' : '우선 조치'}><div className="scenario-ai-overview-card"><div><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority}</StatusBadge><h3>{alert.title}</h3><p>{alert.facility} · {alert.leadTimeHours}시간 이내 출동</p></div><dl><div><dt>이상 센서</dt><dd>{alert.affectedMetric === 'returnTemperature' ? '환수온도' : alert.affectedMetric === 'flow' ? '유량' : '공급온도'}</dd></div><div><dt>문서 상태</dt><dd>{currentReport === 'issued' ? '보고서 발행 완료' : currentOrders.length > 0 ? `작업지시서 v${currentOrders.length}` : '작업지시서 대기'}</dd></div></dl><Button icon="arrow" onClick={() => onSelect(alert.id)} tone="primary">조치 계획 열기</Button></div></SurfaceCard>)}</div></div>
}
