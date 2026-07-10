/**
 * 알림(card_id) → 건물명 해석기.
 *
 * 배경: 운영 콘솔 알림은 실백엔드 계약 `GET /api/alerts`를 소비하는데, `AlertSummary`에는
 * 건물명이 없다(card_id UUID만 있음). 그래서 계약 밖 읽기전용 `GET /cards`로 card_id →
 * substation_id를 얻고, 프론트 로컬 단지 데이터(complexes.ts, id === substation_id)로
 * 건물명을 붙인다. 계약·백엔드는 무변경이며, /cards가 없거나 실패하면(mock/백엔드 미기동)
 * null을 돌려 호출부가 enqueue_reason 등으로 degrade한다.
 */

import { useCardSubstationMap } from '../api/hooks'
import { complexes } from '../data/complexes'

const NAME_BY_SUBSTATION = new Map<number, string>(complexes.map((c) => [c.id, c.name]))

export function useBuildingNameResolver(): (cardId: string) => string | null {
  const cards = useCardSubstationMap()

  return (cardId: string) => {
    const substationId = cards.data?.get(cardId)
    if (substationId == null) return null
    return NAME_BY_SUBSTATION.get(substationId) ?? null
  }
}
