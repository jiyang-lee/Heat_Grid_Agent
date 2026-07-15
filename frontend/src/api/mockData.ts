/**
 * mock ë°±ì—”???°ì´???¤í† ??(ê³„ì•½ shape).
 *
 * ?„ë©”???¨ì?(ê¸´ê¸‰/ì£¼ì˜)ë¥?ë°±ì—”??ê³„ì•½??alertë¡?ë³€?˜í•´ in-memory ?ë? ë§Œë“ ??
 * ack/resolveÂ·agent-run ?ì„±?¼ë¡œ ë³€?œë‹¤. alert_id/card_id???„ì˜ ë¬¸ì??ë°±ì—”?œëŠ” UUID).
 * ?¤ë°±?”ë“œ ?„í™˜ ?????Œì¼?€ ?°ì´ì§€ ?ŠëŠ”??backend.tsê°€ real clientë¡??¤ìœ„ì¹?.
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
 * ???œì•ˆ ?¬í˜„???´ë¦° ?Œë¦¼ 7ê±?ì¡°ì¹˜ ?„ìš” 7ê±?.
 * substation 1?€ ê¸´ê¸‰, 5???ê? ?ˆì •(?ˆì—??'?ˆë‚´' ?¤ìœ¼ë¡??œì‹œ), ?˜ë¨¸ì§€??ê²½ê³ .
 */
const ALERT_SEEDS: readonly { id: number; level: PriorityLevel; reason: string }[] = [
  { id: 1, level: 'urgent', reason: 'ê³µê¸‰?¨ë„ ê³¼ë‹¤ (83.3Â°C)' },
  { id: 2, level: 'high', reason: '?•ë ¥ ?ìŠ¹ ê²½í–¥ (0.92 MPa)' },
  { id: 3, level: 'high', reason: '?˜ìˆ˜?¨ë„ ?´ìƒ (52.1Â°C)' },
  { id: 4, level: 'high', reason: '? ëŸ‰ ?€??(85.0 mÂ³/h)' },
  { id: 5, level: 'high', reason: 'ë°¸ë¸Œ ?ê? ?ˆì • (07:00)' },
  { id: 6, level: 'high', reason: '?˜ìˆ˜?¨ë„ ?¸ì°¨ ?•ë? ê°ì?' },
  { id: 7, level: 'high', reason: '?¼ê°„ ? ëŸ‰ ë³€??ê´€ì°??„ìš”' },
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
  return { alerts, alertComplex, runs: new Map(), artifacts: new Map(), runSeq: 1 }
}

export const store: Store = makeStore()

export function complexForAlert(alertId: string): Complex | undefined {
  const cid = store.alertComplex.get(alertId)
  return cid != null ? complexById.get(cid) : undefined
}

/** OpsAgentOutput ?ìŠ¤??ê¸¸ì´ ê¸°ë°˜ ? í°/ë¹„ìš© ?°ì • (ë°±ì—”??usage.py ?¨ê? ?´ì‹). */
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
      pricing_source: 'mock Â· gpt-5.4-mini',
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
