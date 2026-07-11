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
