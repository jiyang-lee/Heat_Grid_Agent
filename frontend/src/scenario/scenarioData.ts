import type { PriorityEvaluationResult } from '../api/contracts'
import type { EvaluationCategory, ScenarioAlert, ScenarioTimelineAlert, SensorPoint, WorkOrderSection, WorkOrderVersion } from './types'

/** scenario_manifest.csv의 검증된 고장 프로필을 같은 시점에 배치한 동시다발 고장 사례 */
export const ACTIVE_SCENARIO_ID = 'simultaneous-fault-2023-03-12-substations-1-10-30'
export const ACTIVE_SCENARIO_DATASET_VERSION = 'predist-synthetic-replay-v3'
export const SCENARIO_START_AT = '2023-03-12T10:00:00+09:00'
export const SCENARIO_INCIDENT_AT = '2023-03-12T12:00:00+09:00'

export const SCENARIO_ALERTS: readonly ScenarioAlert[] = [
  {
    id: 'scenario-alert-prefault-drift-1',
    title: '공급온도 저하 및 순환 유량 급변',
    facility: '기계실 1 · 공급·순환 계통',
    substationId: 1,
    priority: 'urgent',
    affectedMetric: 'supply',
    leadTimeHours: 6,
    temperatureDelta: -5.9,
    summary: '공급온도가 정상 범위 아래로 빠르게 저하했습니다. 동시다발 경보 중 최우선으로 열원과 공급·순환 계통의 안전 조건을 점검해야 합니다.',
    evidence: ['공급온도 76.4°C → 70.5°C', '대응 목표 6시간', '동시다발 고장 시나리오 · 우선 대응 대상'],
    detectedAt: SCENARIO_INCIDENT_AT,
    modelResult: {
      modelVersion: 'scenario-ml-result.v1',
      anomalyScore: 0.96,
      riskScore: 0.94,
      priorityScore: 96,
      leadtimeUrgencyScore: 0.98,
      rationale: '공급온도 하락폭과 6시간 이내 대응 필요도가 동시에 임계값을 초과했습니다.',
    },
  },
  {
    id: 'scenario-alert-flow-drop-10',
    title: '순환 유량 급감 및 펌프 부하 이상',
    facility: '기계실 10 · 순환펌프·열교환 계통',
    substationId: 10,
    priority: 'urgent',
    affectedMetric: 'flow',
    leadTimeHours: 8,
    temperatureDelta: -40,
    summary: '순환 유량이 기준 범위 아래로 급감해 열공급 불균형 가능성이 확인됐습니다. 기계실 1, 30과 같은 시점에 발생한 동시다발 고장 경보입니다.',
    evidence: ['순환 유량 118 m³/h → 86 m³/h', '대응 목표 8시간', '순환펌프·밸브 상태 동시 점검 필요'],
    detectedAt: SCENARIO_INCIDENT_AT,
    modelResult: {
      modelVersion: 'scenario-ml-result.v1',
      anomalyScore: 0.92,
      riskScore: 0.9,
      priorityScore: 91,
      leadtimeUrgencyScore: 0.93,
      rationale: '순환 유량이 정상 하한을 이탈했고 펌프 부하 이상 가능성이 높게 계산됐습니다.',
    },
  },
  {
    id: 'scenario-alert-return-drop-30',
    title: '환수온도 저하 및 열교환 효율 이상',
    facility: '기계실 30 · 환수·열교환 계통',
    substationId: 30,
    priority: 'high',
    affectedMetric: 'returnTemperature',
    leadTimeHours: 12,
    temperatureDelta: -8.1,
    summary: '환수온도 저하가 지속돼 열교환 효율 저하 가능성이 확인됐습니다. 다른 두 기계실 경보와 동시에 대응 우선순위를 판단해야 합니다.',
    evidence: ['환수온도 42.2°C → 34.1°C', '대응 목표 12시간', '열교환기·환수 배관 점검 필요'],
    detectedAt: SCENARIO_INCIDENT_AT,
    modelResult: {
      modelVersion: 'scenario-ml-result.v1',
      anomalyScore: 0.84,
      riskScore: 0.79,
      priorityScore: 83,
      leadtimeUrgencyScore: 0.81,
      rationale: '환수온도 저하가 지속돼 열교환 효율 저하와 난방 불균형 위험이 계산됐습니다.',
    },
  },
]

function roundedLeadTime(hours: number): number {
  return Math.round(hours * 10) / 10
}

function alertWithElapsedTime(alert: ScenarioAlert, simulatedAt: string, resolvedAt: string | null): ScenarioTimelineAlert {
  const elapsedHours = Math.max(0, (Date.parse(simulatedAt) - Date.parse(alert.detectedAt)) / 3_600_000)
  const leadTimeHours = roundedLeadTime(Math.max(0, alert.leadTimeHours - elapsedHours))
  const status = resolvedAt != null ? 'resolved' : 'active'
  const evidence = alert.evidence.map((item, index) => index === 1 ? `대응 목표 잔여 ${leadTimeHours}시간` : item)
  return { ...alert, leadTimeHours, evidence, status, resolvedAt }
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
  1: [[76.4, 42.2, 119.0], [75.6, 42.1, 118.0], [74.6, 42.0, 117.0], [73.5, 41.9, 116.0], [72.1, 41.8, 115.0], [70.5, 41.7, 114.0]],
  10: [[76.8, 42.4, 118.0], [76.4, 42.0, 112.0], [75.9, 41.6, 104.0], [75.5, 41.1, 97.0], [75.0, 40.6, 91.0], [74.6, 40.2, 86.0]],
  30: [[76.9, 42.2, 121.0], [76.5, 40.9, 122.0], [76.0, 39.4, 124.0], [75.5, 37.6, 125.0], [75.1, 35.7, 127.0], [74.7, 34.1, 128.0]],
}

function roundSensorValue(value: number): number {
  return Math.round(value * 10) / 10
}

/**
 * Keeps the fault evolving after its initial onset profile. Each substation
 * uses a different failure signature instead of freezing at the final value.
 */
function faultPointAt(substationId: number, faultSequence: number): readonly [number, number, number] | undefined {
  const profile = faultProfiles[substationId]
  if (profile == null) return undefined

  const index = Math.max(0, faultSequence)
  if (index < profile.length) return profile[index]

  const elapsed = index - (profile.length - 1)
  if (substationId === 1) {
    // Supply-temperature control drift: gradual heat loss with a small
    // control-loop oscillation while the circulation flow stays available.
    return [
      roundSensorValue(Math.max(67.2, 70.5 - Math.min(3.3, elapsed * 0.08) + Math.sin(elapsed * 0.88) * 0.55)),
      roundSensorValue(41.7 - Math.min(0.9, elapsed * 0.02) + Math.sin(elapsed * 0.56) * 0.18),
      roundSensorValue(114.0 - Math.min(4.5, elapsed * 0.05) + Math.cos(elapsed * 0.76) * 1.4),
    ]
  }
  if (substationId === 10) {
    // Pump degradation: unstable, gradually falling flow followed by a
    // smaller decline in supply and return temperature.
    return [
      roundSensorValue(Math.max(71.8, 74.6 - Math.min(2.8, elapsed * 0.025) + Math.sin(elapsed * 0.57) * 0.35)),
      roundSensorValue(Math.max(37.0, 40.2 - Math.min(2.2, elapsed * 0.035) + Math.cos(elapsed * 0.8) * 0.3)),
      roundSensorValue(Math.max(72.0, 86.0 - Math.min(8.0, elapsed * 0.12) + Math.sin(elapsed * 1.17) * 4.2 + Math.sin(elapsed * 0.37) * 1.7)),
    ]
  }

  // Heat-exchange efficiency loss: return temperature keeps falling while
  // the controller raises flow to compensate, with a realistic fluctuation.
  return [
    roundSensorValue(Math.max(71.5, 74.7 - Math.min(2.2, elapsed * 0.025) + Math.cos(elapsed * 0.48) * 0.3)),
    roundSensorValue(Math.max(30.0, 34.1 - Math.min(3.2, elapsed * 0.06) + Math.sin(elapsed * 0.74) * 0.85)),
    roundSensorValue(128.0 + Math.min(7.0, elapsed * 0.08) + Math.sin(elapsed * 0.64) * 1.8),
  ]
}

export function hasFaultScenarioProfile(substationId: number): boolean {
  return faultProfiles[substationId] != null
}

export function initialSensorPoints(mode: 'normal' | 'fault', substationId: number, endAt?: string): readonly SensorPoint[] {
  const end = new Date(endAt ?? (mode === 'fault' ? SCENARIO_START_AT : new Date().toISOString()))
  const offset = substationId % 3
  // Start with a normal baseline. The fault profile is applied only after the
  // incident so the chart shows the before/after transition truthfully.
  const seed = normalSeed
  return seed.map(([supply, returnTemperature, flow], index) => ({
    at: new Date(end.getTime() - (seed.length - 1 - index) * 600_000).toISOString(),
    supply: supply + offset * 0.1,
    returnTemperature: returnTemperature + offset * 0.1,
    flow: flow + offset,
    quality: 'validated',
    sequence: index,
  }))
}

export function fallbackSensorPoint(mode: 'normal' | 'fault', substationId: number, incidentActive: boolean, sequence: number, previousAt: string, faultSequence = sequence): SensorPoint {
  const normalCycle = normalSeed[sequence % normalSeed.length] ?? normalSeed[0]
  const faultPoint = faultPointAt(substationId, faultSequence)
  const selected = mode === 'fault' && incidentActive && faultPoint != null
    ? faultPoint
    : normalCycle
  return {
    at: new Date(new Date(previousAt).getTime() + 600_000).toISOString(),
    supply: selected[0],
    returnTemperature: selected[1],
    flow: selected[2],
    quality: mode === 'fault' && incidentActive && faultPoint != null ? 'scenario-validated' : 'validated',
    sequence,
  }
}

export function scenarioPriorityRows(alerts: readonly ScenarioAlert[]): readonly PriorityEvaluationResult[] {
  return [...alerts]
    .sort((left, right) => right.modelResult.priorityScore - left.modelResult.priorityScore || left.id.localeCompare(right.id))
    .map((alert, index) => ({
  evaluation_result_id: `scenario-result-${alert.substationId}`,
  evaluation_run_id: 'scenario-evaluation-20230312',
  manufacturer_id: 'scenario-replay',
  substation_id: alert.substationId,
  source_window_id: `scenario-window-${alert.substationId}`,
  source_window_start: SCENARIO_START_AT,
  source_window_end: alert.detectedAt,
  source_card_id: alert.id,
  source_priority_decision_id: `scenario-priority-${alert.substationId}`,
  priority_score: alert.modelResult.priorityScore,
  priority_rank: index + 1,
  rank_included: true,
  priority_level: alert.priority,
  risk_score: alert.modelResult.riskScore,
  anomaly_score: alert.modelResult.anomalyScore,
  anomaly_label: true,
  leadtime_bucket: alert.leadTimeHours <= 12 ? 'within_12h' : 'within_24h',
  leadtime_urgency_score: alert.modelResult.leadtimeUrgencyScore,
  leadtime_hours: alert.leadTimeHours,
  freshness_status: 'fresh',
  data_age_seconds: 0,
  model_components: {
    scenario: true,
    model_version: alert.modelResult.modelVersion,
    anomaly_score: alert.modelResult.anomalyScore,
    risk_score: alert.modelResult.riskScore,
    priority_score: alert.modelResult.priorityScore,
    leadtime_urgency_score: alert.modelResult.leadtimeUrgencyScore,
  },
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
  const mlResult = alert.modelResult
  return [
    { title: '머신러닝 결과', items: [`이상 점수 ${Math.round(mlResult.anomalyScore * 100)}% · 위험 점수 ${Math.round(mlResult.riskScore * 100)}%`, `우선순위 점수 ${mlResult.priorityScore.toFixed(0)}점 · 대응 긴급도 ${Math.round(mlResult.leadtimeUrgencyScore * 100)}%`, mlResult.rationale] },
    { title: '사고 요약 및 대응 기준', items: [`${alert.priority} 우선순위 · 대응 목표 ${alert.leadTimeHours}시간`, `대상: ${alert.facility}`, `대응 목표 시각: ${deadlineFor(alert)} 이전`] },
    { title: '위험성 및 근거', items: [alert.summary, ...alert.evidence] },
    { title: '출동 전 안전 확인', items: ['현장 책임자와 작업 범위를 상호 확인하고 LOTO 적용 여부를 기록합니다.', '보호구, 절연 공구, 휴대용 온도계 및 유량 측정기를 준비합니다.'] },
    { title: '점검·차단·복구 절차', items: ['현재 운전값을 기록한 뒤 우회 운전 가능 여부를 확인합니다.', `${alert.affectedMetric === 'flow' ? '열교환기 2차측 누수 흔적과 유량계를 우선 점검합니다.' : alert.affectedMetric === 'supply' ? '공급온도 설정값, 열원·순환 계통과 유량 계측 상태를 우선 점검합니다.' : '순환펌프 전원, 인버터, 환수 배관 밸브를 순서대로 점검합니다.'}`, '현장 책임자 승인 후 필요한 설비만 격리하고, 복구 후 안정화 값을 10분 이상 확인합니다.'] },
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
