import type { Complex } from '../data/complexes'
import type { OpsAgentOutput } from './contracts'
import { agentRunsApi, alertsApi, cardsApi, simulationsApi } from './client'

export type WorkOrderMode = 'llm' | 'fallback'

export interface WorkOrderResult {
  output: OpsAgentOutput
  mode: WorkOrderMode
}

export async function generateWorkOrder(complex: Complex): Promise<WorkOrderResult> {
  const [cards, alerts] = await Promise.all([
    cardsApi.list(),
    alertsApi.list({ status: 'open' }),
  ])
  const matchingCards = cards.filter(
    (card) => String(card.substation_id) === String(complex.id),
  )
  if (matchingCards.length === 0) {
    throw new Error(`${complex.name}에 연결된 실백엔드 카드가 없습니다.`)
  }

  const cardIds = new Set(matchingCards.map((card) => card.card_id))
  const alert = alerts
    .filter((item) => cardIds.has(item.card_id))
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))[0]

  if (alert) {
    const run = await agentRunsApi.create({ alert_id: alert.alert_id })
    if (run.status === 'failed' || !run.ops_output) {
      throw new Error(run.error || '작업 지시서 생성 결과를 받지 못했습니다.')
    }
    return { output: run.ops_output, mode: run.agent_mode === 'llm' ? 'llm' : 'fallback' }
  }

  const simulation = await simulationsApi.run(matchingCards[0].card_id)
  return {
    output: simulation.ops_output,
    mode: simulation.agent_mode === 'llm' ? 'llm' : 'fallback',
  }
}
