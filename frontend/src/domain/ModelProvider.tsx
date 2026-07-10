/**
 * 지도 관제 모델 provider.
 *
 * 실백엔드 alert(GET /api/alerts, priority_level)와 card_id→substation_id 매핑으로
 * 단지별 tier(긴급/주의/정상)를 만들어 도메인 파생 함수(overall/counts/machineStatus/
 * summaryCounts)를 공급한다. 조인 키: complexes.ts id === 백엔드 substation_id.
 *   - urgent alert 있으면 긴급, high alert만 있으면 주의, 없으면 정상.
 * 백엔드가 없거나(mock/미기동) 데이터가 아직 없으면 데모 tier로 degrade한다.
 * 계약·백엔드 무변경 — 프론트가 계약 응답을 소비해 tier를 파생할 뿐이다.
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useAlerts, useCardSubstationMap } from '../api/hooks'
import { USE_MOCK } from '../api/config'
import type { AlertSummary } from '../api/contracts'
import { createModel, demoTierById, type DomainModel } from './model'
import type { Tier } from './status'

interface ModelContextValue extends DomainModel {
  /** tier 출처: 'model' = 백엔드 우선순위, 'demo' = 관리비 단가 대리지표 */
  source: 'model' | 'demo'
}

const ModelContext = createContext<ModelContextValue | null>(null)

/** alert + card→substation 매핑 → substation(=단지 id)별 tier */
function tierByIdFromAlerts(
  alerts: AlertSummary[],
  cardSubstation: Map<string, number>,
): Map<number, Tier> {
  const map = new Map<number, Tier>()
  for (const alert of alerts) {
    const substationId = cardSubstation.get(alert.card_id)
    if (substationId == null) continue
    const tier: Tier = alert.priority_level === 'urgent' ? 'urgent' : 'caution'
    const current = map.get(substationId)
    if (current === 'urgent') continue // 이미 최고 등급
    if (tier === 'urgent' || current == null) map.set(substationId, tier)
  }
  return map
}

export function ModelProvider({ children }: { children: ReactNode }) {
  const alerts = useAlerts({ status: 'open' })
  const cards = useCardSubstationMap()

  const value = useMemo<ModelContextValue>(() => {
    const backendTiers =
      !USE_MOCK && alerts.data && cards.data
        ? tierByIdFromAlerts(alerts.data, cards.data)
        : null
    const useBackend = backendTiers != null && backendTiers.size > 0
    const model = createModel(useBackend ? backendTiers : demoTierById)
    return { ...model, source: useBackend ? 'model' : 'demo' }
  }, [alerts.data, cards.data])

  return <ModelContext.Provider value={value}>{children}</ModelContext.Provider>
}

export function useModel(): ModelContextValue {
  const value = useContext(ModelContext)
  if (value == null) throw new Error('useModel must be used within ModelProvider')
  return value
}
