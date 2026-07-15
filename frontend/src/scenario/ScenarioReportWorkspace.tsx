import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import type { ScenarioAlert, WorkOrderVersion } from './types'

interface Props {
  readonly alert: ScenarioAlert
  readonly order: WorkOrderVersion | undefined
  readonly report: { readonly status: 'idle' | 'draft' | 'issued'; readonly createdAt: string | null; readonly issuedAt: string | null }
  readonly onCreateDraft: () => void
  readonly onIssue: () => void
}

function reportText(alert: ScenarioAlert, order: WorkOrderVersion): string {
  return [
    '# 2020.01.13 지역난방 사고 조치 보고서', '',
    '## 1. 사고 개요',
    `- 대상 설비: ${alert.facility} (기계실 ${alert.substationId})`,
    `- 사고 유형: ${alert.title}`,
    `- 우선순위: ${alert.priority.toUpperCase()} · 출동 제한 ${alert.leadTimeHours.toFixed(1)}시간`,
    `- 기준 작업지시서: v${order.version} (${order.changeNote})`, '',
    '## 2. 사고 타임라인',
    '- 14:30 정상 범위 이탈 전조를 확인하고 해당 기계실 센서 흐름을 집중 모니터링했습니다.',
    '- 15:00 센서 이상과 동시다발 경보 3건을 감지해 우선순위 산정을 시작했습니다.',
    '- 15:03 AI 조치 분석을 완료하고 현장 출동·안전 점검 순서를 작업지시서에 반영했습니다.', '',
    '## 3. 센서 근거 및 위험 판단', ...alert.evidence.map((item) => `- ${item}`),
    '- 정상 범위 이탈 지속 시간, 동반 지표의 변화, 설비별 열공급 영향도를 함께 비교했습니다.',
    `- ${alert.priority.toUpperCase()} 우선순위로 판단하여 작업지시서의 출동 제한시간 안에 조치하도록 배정했습니다.`, '',
    '## 4. 조치 결과 및 현장 확인',
    '- 작업 전 LOTO, 압력·누수·펌프 상태 확인 및 보호구 착용 절차를 수행합니다.',
    '- 차단·점검·복구 후 10분 단위의 공급온도, 환수온도, 유량을 기록해 정상 범위 복귀를 확인합니다.',
    '- 완료 기준과 인계 항목은 채택된 작업지시서의 점검·복구 절차를 따릅니다.', '',
    '## 5. 검토 및 발행 이력',
    `- 운영자 채택: 작업지시서 v${order.version}`,
    '- 발행 상태: 시나리오 문서 · 백엔드 전송 및 DB 저장 없음',
  ].join('\n')
}

export function ScenarioReportWorkspace({ alert, order, report, onCreateDraft, onIssue }: Props) {
  const download = () => {
    if (!order) return
    const blob = new Blob([reportText(alert, order)], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `heatgrid-report-20200113-${alert.substationId}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (!order) return <SurfaceCard title="사고 조치 보고서"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 채택 대기</StatusBadge><p>생성된 작업지시서 중 하나를 최종 채택하면 해당 버전을 기준으로 전문 보고서 초안을 만들 수 있습니다.</p></div></SurfaceCard>

  return <div className="scenario-report-layout"><SurfaceCard title="사고 조치 보고서"><div className="scenario-report-document"><header><div><StatusBadge tone={report.status === 'issued' ? 'success' : report.status === 'draft' ? 'primary' : 'neutral'}>{report.status === 'issued' ? '발행 완료' : report.status === 'draft' ? '초안' : '미생성'}</StatusBadge><h2>2020.01.13 지역난방 사고 조치 보고서</h2></div><span>시나리오 문서</span></header>{report.status !== 'idle' && <div className="scenario-report-preview"><section><h3>1. 사고 개요</h3><p>{alert.facility} · 기계실 {alert.substationId} · {alert.priority.toUpperCase()} · 출동 제한 {alert.leadTimeHours.toFixed(1)}시간</p></section><section><h3>2. 사고 타임라인</h3><ul><li>14:30 정상 범위 이탈 전조 감지 및 집중 모니터링 전환</li><li>15:00 {alert.title}와 동시다발 경보 3건 감지</li><li>15:03 AI 조치 분석 완료, 현장 출동·안전 점검 순서 반영</li></ul></section><section><h3>3. 센서 근거 및 위험 판단</h3><ul>{alert.evidence.map((item) => <li key={item}>{item}</li>)}<li>이탈 지속 시간, 동반 지표, 열공급 영향도를 종합해 우선순위를 산정했습니다.</li></ul></section><section><h3>4. 조치 결과 및 인계</h3><p>작업지시서 v{order.version}의 안전 조치, 설비별 점검·차단·복구 절차와 완료 기준을 적용합니다. 10분 단위 측정값과 현장 조치 이력을 인계 항목으로 기록합니다.</p></section><footer>최종 채택 작업지시서 v{order.version} · {report.status === 'issued' ? `발행 완료 ${report.issuedAt ? new Date(report.issuedAt).toLocaleString('ko-KR') : ''}` : '운영자 검토 대기'} · 백엔드 전송 없음</footer></div>}<div className="scenario-report-actions"><Button disabled={report.status !== 'idle'} icon="document" onClick={onCreateDraft} tone="primary">보고서 초안 생성</Button><Button disabled={report.status !== 'draft'} onClick={onIssue} tone="primary">보고서 발행</Button><Button disabled={report.status !== 'issued'} icon="download" onClick={download}>문서 다운로드</Button></div></div></SurfaceCard></div>
}
