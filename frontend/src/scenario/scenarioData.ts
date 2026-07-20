import type { PriorityEvaluationResult } from '../api/contracts'
import type { EvaluationCategory, ScenarioAlert, ScenarioTimelineAlert, SensorPoint, WorkOrderSection, WorkOrderVersion } from './types'

export const ACTIVE_SCENARIO_ID = 'return-temperature-2020-01-13'
export const SCENARIO_START_AT = '2020-01-13T14:50:00+09:00'
export const SCENARIO_INCIDENT_AT = '2020-01-13T15:10:00+09:00'

export const SCENARIO_ALERTS: readonly ScenarioAlert[] = [
  {
    id: 'scenario-alert-pump-28',
    title: '환수온도 급락 및 난방 순환펌프 이상',
    facility: '기계실 28 · 난방 순환펌프',
    substationId: 28,
    priority: 'urgent',
    affectedMetric: 'returnTemperature',
    leadTimeHours: 4.9,
    temperatureDelta: -8.06,
    summary: '환수온도가 정상 범위를 이탈했고 순환펌프 효율 저하 신호가 동시에 감지되었습니다.',
    evidence: ['환수온도 42.17°C → 34.11°C', '예상 출동 리드타임 4.9시간', '순환계통 압력·유량 동반 변동'],
    detectedAt: SCENARIO_INCIDENT_AT,
  },
  {
    id: 'scenario-alert-leak-31',
    title: '열교환기 외부 누수 의심',
    facility: '기계실 31 · 판형 열교환기',
    substationId: 31,
    priority: 'urgent',
    affectedMetric: 'flow',
    leadTimeHours: 9.8,
    temperatureDelta: -12,
    summary: '열교환기 2차측 유량 변동이 누수 패턴과 유사해 긴급 현장 점검이 필요합니다.',
    evidence: ['유량 118.0m³/h → 86.0m³/h', '예상 출동 리드타임 9.8시간', '열교환기 외부 누수 점검 필요'],
    detectedAt: SCENARIO_INCIDENT_AT,
  },
  {
    id: 'scenario-alert-tank-29',
    title: '급탕 축열조 성능 저하',
    facility: '기계실 29 · 급탕 축열조',
    substationId: 29,
    priority: 'high',
    affectedMetric: 'supply',
    leadTimeHours: 18,
    temperatureDelta: 8.2,
    summary: '급탕 축열조의 공급온도 제어가 불안정해 계획 점검과 운전 조건 확인이 필요합니다.',
    evidence: ['공급온도 76.4°C → 84.6°C', '예상 출동 리드타임 18시간', 'urgent 조치 후 순차 점검'],
    detectedAt: SCENARIO_INCIDENT_AT,
  },
]

function roundedLeadTime(hours: number): number {
  return Math.round(hours * 10) / 10
}

function alertWithElapsedTime(alert: ScenarioAlert, simulatedAt: string, resolvedAt: string | null): ScenarioTimelineAlert {
  const elapsedHours = Math.max(0, (Date.parse(simulatedAt) - Date.parse(alert.detectedAt)) / 3_600_000)
  const leadTimeHours = roundedLeadTime(Math.max(0, alert.leadTimeHours - elapsedHours))
  const expiredAt = new Date(Date.parse(alert.detectedAt) + alert.leadTimeHours * 3_600_000).toISOString()
  const status = resolvedAt != null ? 'resolved' : leadTimeHours === 0 ? 'expired' : 'active'
  const evidence = alert.evidence.map((item, index) => index === 1 ? `예상 출동 리드타임 ${leadTimeHours}시간` : item)
  return { ...alert, leadTimeHours, evidence, status, resolvedAt: status === 'active' ? null : resolvedAt ?? expiredAt }
}

export function scenarioAlertsAt(simulatedAt: string, resolvedAlertTimes: Readonly<Record<string, string>> = {}): { readonly active: readonly ScenarioTimelineAlert[]; readonly history: readonly ScenarioTimelineAlert[] } {
  const simulatedTime = Date.parse(simulatedAt)
  const timeline = SCENARIO_ALERTS
    .filter((alert) => Date.parse(alert.detectedAt) <= simulatedTime)
    .map((alert) => alertWithElapsedTime(alert, simulatedAt, resolvedAlertTimes[alert.id] ?? null))
  return {
    active: timeline.filter((alert) => alert.status === 'active'),
    history: timeline.filter((alert) => alert.status !== 'active'),
  }
}

const normalSeed = [
  [76.1, 41.5, 116], [76.8, 42.2, 122], [75.9, 41.6, 117], [75.2, 43.1, 112],
  [76.6, 41.7, 120], [76.1, 41.5, 118], [76.5, 42.6, 121], [75.8, 41.4, 117],
  [75.7, 42.0, 113], [76.6, 42.5, 118], [75.0, 41.6, 116], [75.5, 40.8, 119], [76.3, 41.9, 120],
] as const

const faultProfiles: Readonly<Record<number, readonly (readonly [number, number, number])[]>> = {
  28: [[75.1, 34.1, 119], [75.4, 36.7, 117], [75.8, 33.6, 124], [74.9, 35.2, 111]],
  31: [[75.8, 41.5, 86.0], [75.5, 40.9, 92.0], [76.1, 41.2, 83.0], [75.6, 40.6, 89.0]],
  29: [[84.6, 42.0, 118], [86.1, 41.8, 117], [82.9, 42.2, 120], [85.2, 41.6, 119]],
}

export function initialSensorPoints(mode: 'normal' | 'fault', substationId: number, endAt?: string): readonly SensorPoint[] {
  const end = new Date(endAt ?? (mode === 'fault' ? SCENARIO_START_AT : new Date().toISOString()))
  const offset = substationId % 3
  return normalSeed.map(([supply, returnTemperature, flow], index) => ({
    at: new Date(end.getTime() - (normalSeed.length - 1 - index) * 600_000).toISOString(),
    supply: supply + offset * 0.1,
    returnTemperature: returnTemperature + offset * 0.1,
    flow: flow + offset,
    quality: 'validated',
    sequence: index,
  }))
}

export function fallbackSensorPoint(mode: 'normal' | 'fault', substationId: number, incidentActive: boolean, sequence: number, previousAt: string): SensorPoint {
  const normalCycle = normalSeed[sequence % normalSeed.length] ?? normalSeed[0]
  const profile = faultProfiles[substationId]
  const selected = mode === 'fault' && incidentActive && profile
    ? profile[sequence % profile.length] ?? profile[0]
    : normalCycle
  return {
    at: new Date(new Date(previousAt).getTime() + 600_000).toISOString(),
    supply: selected[0],
    returnTemperature: selected[1],
    flow: selected[2],
    quality: mode === 'fault' && incidentActive && profile ? 'scenario-validated' : 'validated',
    sequence,
  }
}

export function scenarioPriorityRows(alerts: readonly ScenarioAlert[]): readonly PriorityEvaluationResult[] {
  return alerts.map((alert, index) => ({
  evaluation_result_id: `scenario-result-${alert.substationId}`,
  evaluation_run_id: 'scenario-evaluation-20200113',
  manufacturer_id: 'scenario-replay',
  substation_id: alert.substationId,
  source_window_id: `scenario-window-${alert.substationId}`,
  source_window_start: '2020-01-13T14:00:00+09:00',
  source_window_end: alert.detectedAt,
  source_card_id: alert.id,
  source_priority_decision_id: `scenario-priority-${alert.substationId}`,
  priority_score: alert.priority === 'urgent' ? 94 - index * 4 : 72,
  priority_rank: index + 1,
  rank_included: true,
  priority_level: alert.priority,
  risk_score: alert.priority === 'urgent' ? 0.94 - index * 0.04 : 0.72,
  anomaly_score: alert.priority === 'urgent' ? 0.91 - index * 0.05 : 0.68,
  anomaly_label: true,
  leadtime_bucket: alert.leadTimeHours <= 12 ? 'within_12h' : 'within_24h',
  leadtime_urgency_score: alert.leadTimeHours <= 12 ? 0.95 : 0.66,
  leadtime_hours: alert.leadTimeHours,
  freshness_status: 'fresh',
  data_age_seconds: 0,
  model_components: { scenario: true, priority: alert.priority },
  created_at: alert.detectedAt,
  }))
}

export const SCENARIO_PRIORITY_ROWS = scenarioPriorityRows(SCENARIO_ALERTS)

function deadlineFor(alert: ScenarioAlert): string {
  const deadline = new Date(new Date(alert.detectedAt).getTime() + alert.leadTimeHours * 3_600_000)
  return deadline.toLocaleString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function workOrderSections(alert: ScenarioAlert, version: 1 | 2 | 3, changeSummary: string): readonly WorkOrderSection[] {
  const revised = version === 1 ? '초안 기준' : `v${version} 검토 반영: ${changeSummary}`
  return [
    { title: '사고 요약 및 출동 기준', items: [`${alert.priority} 우선순위 · ${alert.leadTimeHours}시간 이내 출동`, `대상: ${alert.facility}`, `출동 시한: ${deadlineFor(alert)} 이전`] },
    { title: '위험성 및 근거', items: [alert.summary, ...alert.evidence] },
    { title: '출동 전 안전 확인', items: ['현장 책임자와 작업 범위를 상호 확인하고 LOTO 적용 여부를 기록합니다.', '보호구, 절연 공구, 휴대용 온도계 및 유량 측정기를 준비합니다.'] },
    { title: '점검·차단·복구 절차', items: ['현재 운전값을 기록한 뒤 우회 운전 가능 여부를 확인합니다.', `${alert.affectedMetric === 'flow' ? '열교환기 2차측 누수 흔적과 유량계를 우선 점검합니다.' : alert.affectedMetric === 'supply' ? '축열조 제어밸브와 공급온도 제어값을 우선 점검합니다.' : '순환펌프 전원, 인버터, 환수 배관 밸브를 순서대로 점검합니다.'}`, '현장 책임자 승인 후 필요한 설비만 격리하고, 복구 후 안정화 값을 10분 이상 확인합니다.'] },
    { title: '기록·완료·인계', items: ['조치 전후 온도·유량·압력과 작업 시각을 기록합니다.', '정상 범위 복귀, 경보 해소, 운영자 인계를 모두 확인한 뒤 작업을 종료합니다.', revised] },
  ]
}

export function workOrderVersion(alert: ScenarioAlert, version: 1 | 2 | 3, changeSummary: string): WorkOrderVersion {
  const sections = workOrderSections(alert, version, changeSummary)
  const title = `${alert.facility} ${alert.affectedMetric === 'returnTemperature' ? '환수온도' : alert.affectedMetric === 'flow' ? '유량' : '공급온도'} 이상 작업지시서 v${version}`
  return {
    version,
    createdAt: new Date().toISOString(),
    title,
    changeSummary,
    instructions: sections.flatMap((section) => section.items),
    sections,
    content: [
      title,
      '',
      ...sections.flatMap((section) => [section.title, ...section.items.map((item, index) => `${index + 1}. ${item}`), '']),
    ].join('\n').trim(),
    sourceRunId: null,
    revisionInstruction: version === 1 ? null : changeSummary,
    baseVersion: version === 1 ? null : (version - 1) as 1 | 2,
  }
}

export const IMPROVEMENT_LABELS: Record<EvaluationCategory, string> = {
  model: '예측 모델 재학습 후보',
  'external-data': '외부 데이터 재가공 후보',
  rag: 'RAG 문서 최신화 후보',
  'work-order': '작업지시서 작성 정책 개선 후보',
}
