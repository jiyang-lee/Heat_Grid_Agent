import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import type { ScenarioAlert, ScenarioReportStatus, WorkOrderVersion } from './types'

interface Props {
  readonly alerts: readonly ScenarioAlert[]
  readonly onSelect: (id: string) => void
  readonly reportStatus: ScenarioReportStatus
  readonly workOrders: readonly WorkOrderVersion[]
}

export function ScenarioAiOverview({ alerts, onSelect, reportStatus, workOrders }: Props) {
  const rankedAlerts = [...alerts].sort((left, right) => right.modelResult.priorityScore - left.modelResult.priorityScore || left.id.localeCompare(right.id))
  return <div className="scenario-ai-overview">
    <header><div><h2>계획된 목록</h2><p>활성 경보를 선택해 머신러닝 결과, 출동 판단, 작업지시서와 보고서 진행 상태를 확인하세요.</p></div><StatusBadge tone="critical">활성 {alerts.length}건</StatusBadge></header>
    <div className="scenario-ai-overview-grid">{rankedAlerts.map((alert) => <SurfaceCard key={alert.id} title={alert.priority === 'urgent' ? '긴급 조치' : '우선 조치'}>
      <div className="scenario-ai-overview-card">
        <div><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority}</StatusBadge><h3>{alert.title}</h3><p>{alert.facility} · {alert.leadTimeHours}시간 이내 출동</p></div>
        <dl>
          <div><dt>ML 우선순위</dt><dd>{alert.modelResult.priorityScore.toFixed(0)}점</dd></div>
          <div><dt>위험 점수</dt><dd>{Math.round(alert.modelResult.riskScore * 100)}%</dd></div>
          <div><dt>이상 센서</dt><dd>{alert.affectedMetric === 'returnTemperature' ? '환수온도' : alert.affectedMetric === 'flow' ? '유량' : '공급온도'}</dd></div>
          <div><dt>문서 상태</dt><dd>{reportStatus === 'completed' ? '보고서 완료' : workOrders.length > 0 ? `작업지시서 v${workOrders.length}` : '작업지시서 대기'}</dd></div>
        </dl>
        <Button icon="arrow" onClick={() => onSelect(alert.id)} tone="primary">계획으로 가기</Button>
      </div>
    </SurfaceCard>)}</div>
  </div>
}
