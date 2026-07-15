import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import type { ScenarioAlert, ScenarioReportStatus, WorkOrderVersion } from './types'

interface Props {
  readonly alert: ScenarioAlert
  readonly order: WorkOrderVersion | undefined
  readonly reportStatus: ScenarioReportStatus
  readonly onCreateOrder: () => void
}

export function ScenarioActionPlan({ alert, order, reportStatus, onCreateOrder }: Props) {
  const tone = alert.priority === 'urgent' ? 'critical' : 'warning'
  return <div className="scenario-action-grid">
    <SurfaceCard title="AI 권장 조치"><div className="scenario-action-hero"><span className={`scenario-grade ${alert.priority}`}>{alert.priority}</span><div><span>위험등급</span><h2>{alert.leadTimeHours <= 12 ? '12시간 이내 출동이 필요한 고장입니다' : '계획 점검이 필요한 고장입니다'}</h2><p>{alert.summary}</p></div></div><ol className="scenario-action-steps"><li className="active"><b>1</b><div><strong>작업지시서 발행</strong><span>출동 범위와 안전 절차를 확인합니다.</span></div></li><li className={order ? 'active' : ''}><b>2</b><div><strong>운영자 검토·수정</strong><span>자연어 챗봇으로 근거와 절차를 교정합니다.</span></div></li><li className={reportStatus === 'issued' ? 'active' : ''}><b>3</b><div><strong>보고서 발행</strong><span>승인된 작업 결과를 시나리오 문서로 정리합니다.</span></div></li></ol><div className="scenario-plan-actions"><Button disabled={order != null} icon="document" onClick={onCreateOrder} tone="primary">{order ? '작업지시서 생성 완료' : '작업지시서 생성'}</Button></div></SurfaceCard>
    <SurfaceCard title="판단 근거"><div className="scenario-plan-evidence"><StatusBadge tone={tone}>{alert.priority}</StatusBadge><ul><li><span>예상 리드타임</span><strong>{alert.leadTimeHours}시간</strong></li><li><span>이상 센서</span><strong>{alert.affectedMetric === 'returnTemperature' ? '환수온도' : alert.affectedMetric === 'flow' ? '유량' : '공급온도'}</strong></li><li><span>감지 시각</span><strong>2020.01.13 15:00</strong></li><li><span>조치 우선순위</span><strong>1 / 3</strong></li></ul></div></SurfaceCard>
  </div>
}
