/**
 * mock 백엔드 데이터 스토어 (계약 shape).
 *
 * 도메인 단지(긴급/주의)를 백엔드 계약의 alert로 변환해 in-memory 큐를 만든다.
 * ack/resolve·agent-run 생성으로 변한다. alert_id/card_id는 임의 문자열(백엔드는 UUID).
 * 실백엔드 전환 시 이 파일은 쓰이지 않는다(backend.ts가 real client로 스위치).
 */

import type {
  AgentRunArtifact,
  AgentRunResponse,
  AlertSummary,
  OpsAgentOutput,
  PriorityLevel,
  TokenUsage,
} from './contracts'
import { complexes, type Complex } from '../data/complexes'
import { complexById } from '../domain/model'

const priorityComplexes = complexes.filter((c) => c.id <= 15)
const MOCK_EVALUATION_RUN_ID = 'evaluation-mock-latest'
const BASE_MS = Date.parse('2026-07-09T09:00:00+09:00')

const iso = (offsetMin: number): string => new Date(BASE_MS - offsetMin * 60000).toISOString()

/**
 * 홈 시안 재현용 열린 알림 7건(조치 필요 7건).
 * substation 1은 긴급, 5는 점검 예정(홈에서 '안내' 톤으로 표시), 나머지는 경고.
 */
const ALERT_SEEDS: readonly { id: number; level: PriorityLevel; reason: string }[] = [
  { id: 1, level: 'urgent', reason: '공급온도 과다 (83.3°C)' },
  { id: 2, level: 'high', reason: '압력 상승 경향 (0.92 MPa)' },
  { id: 3, level: 'high', reason: '환수온도 이상 (52.1°C)' },
  { id: 4, level: 'high', reason: '유량 저하 (85.0 m³/h)' },
  { id: 5, level: 'high', reason: '밸브 점검 예정 (07:00)' },
  { id: 6, level: 'high', reason: '환수온도 편차 확대 감지' },
  { id: 7, level: 'high', reason: '야간 유량 변동 관찰 필요' },
]

interface Store {
  alerts: Map<string, AlertSummary>
  alertComplex: Map<string, number>
  runs: Map<string, AgentRunResponse>
  artifacts: Map<string, AgentRunArtifact[]>
  runSeq: number
}

function makeStore(): Store {
  const alerts = new Map<string, AlertSummary>()
  const alertComplex = new Map<string, number>()
  priorityComplexes
    .slice()
    .sort((a, b) => a.id - b.id)
    .forEach((c, i) => {
      const alertId = `alert-${String(c.id).padStart(3, '0')}`
      const cardId = `card-${String(c.id).padStart(3, '0')}`
      const level: PriorityLevel = c.id <= 6 ? 'urgent' : 'high'
      const score = Number((100 - c.id * 1.5).toFixed(3))
      alerts.set(alertId, {
        alert_id: alertId,
        card_id: cardId,
        evaluation_run_id: MOCK_EVALUATION_RUN_ID,
        as_of_time: new Date(BASE_MS).toISOString(),
        manufacturer_id: 'manufacturer 1',
        substation_id: c.id,
        priority_rank: c.id,
        freshness_status: 'fresh',
        priority_level: level,
        priority_score: score,
        status: 'open',
        enqueue_reason: `${c.name} (substation ${c.id}) ${level} priority card`,
        created_at: iso(i * 13),
        acked_at: null,
        acked_by: null,
      })
      alertComplex.set(alertId, c.id)
    })
    alertComplex.set(alertId, seed.id)
  })
  return { alerts, alertComplex, runs: new Map(), artifacts: new Map(), runSeq: 1 }
}

export const store: Store = makeStore()

export function complexForAlert(alertId: string): Complex | undefined {
  const cid = store.alertComplex.get(alertId)
  return cid != null ? complexById.get(cid) : undefined
}

/** OpsAgentOutput 텍스트 길이 기반 토큰/비용 산정 (백엔드 usage.py 단가 이식). */
export function buildTokenUsage(output: OpsAgentOutput): TokenUsage {
  const text = output.summary + output.action_plan + output.caution
  const outputTokens = Math.max(60, Math.round(text.length / 2))
  const inputTokens = 3800
  const cachedInputTokens = 0
  const totalTokens = inputTokens + outputTokens
  const inputCost = ((inputTokens - cachedInputTokens) * 0.75) / 1_000_000
  const cachedInputCost = (cachedInputTokens * 0.075) / 1_000_000
  const outputCost = (outputTokens * 4.5) / 1_000_000
  return {
    model_calls: 1,
    input_tokens: inputTokens,
    cached_input_tokens: cachedInputTokens,
    output_tokens: outputTokens,
    total_tokens: totalTokens,
    evidence_payload_chars: 8000 + text.length,
    cost_estimate: {
      model: 'gpt-5.4-mini',
      input_usd_per_1m: 0.75,
      cached_input_usd_per_1m: 0.075,
      output_usd_per_1m: 4.5,
      input_cost_usd: inputCost,
      cached_input_cost_usd: cachedInputCost,
      output_cost_usd: outputCost,
      total_cost_usd: inputCost + cachedInputCost + outputCost,
      pricing_source: 'mock · gpt-5.4-mini',
    },
    calls: [
      {
        input_tokens: inputTokens,
        cached_input_tokens: cachedInputTokens,
        output_tokens: outputTokens,
        total_tokens: totalTokens,
      },
    ],
  }
}
