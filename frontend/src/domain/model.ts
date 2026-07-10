/**
 * 파생 모델 — heating_agent.html의 assignTier/overall/counts 이식.
 *
 * tier(긴급/주의/정상) 소스는 두 가지다:
 *   - 데모(demoTierById): 실 고장 데이터가 없을 때 총관리비 단가(원/㎡, '열수요 대리 지표')
 *     내림차순 상위 6 = 긴급, 다음 9 = 주의, 나머지 = 정상으로 결정론적 배정.
 *   - 모델(백엔드): 실백엔드 alert/priority_score 기반 tierById (ModelProvider가 주입).
 *
 * createModel(tierById)로 tier 소스만 갈아끼우면 overall/machineStatus/counts/summaryCounts가
 * 그대로 따라온다. 모듈 최상위 export(overall 등)는 데모 기본값이며, React 트리에서는
 * ModelProvider/useModel로 백엔드 tier가 주입된 버전을 쓴다.
 */

import { complexes, type Complex } from '../data/complexes'
import type { Tier } from './status'
import { MACHINES, machineMonitored } from './machines'

export type MachineStatus = Record<string, Tier>

export const complexById: Map<number, Complex> = new Map(complexes.map((c) => [c.id, c]))

/** 데모 tier: unit(총관리비 단가) 내림차순 상위6 urgent / 다음9 caution / 나머지 normal */
export const demoTierById: Map<number, Tier> = (() => {
  const m = new Map<number, Tier>()
  const sorted = [...complexes].sort((a, b) => b.unit - a.unit)
  sorted.forEach((c, i) => m.set(c.id, i < 6 ? 'urgent' : i < 15 ? 'caution' : 'normal'))
  return m
})()

export interface DomainModel {
  /** 단지 종합상태 */
  overall: (id: number) => Tier
  /** 단지별 설비 상태 맵 */
  machineStatus: (id: number) => MachineStatus
  /** 단지 내 설비 상태별 개수 */
  counts: (id: number) => Record<Tier, number>
  /** 헤더 요약: 단지 종합상태 기준 집계 */
  summaryCounts: () => Record<Tier, number>
}

/** tier 소스(tierById)로 파생 함수 묶음을 만든다. tierById에 없는 id는 normal. */
export function createModel(tierById: Map<number, Tier>): DomainModel {
  const overall = (id: number): Tier => tierById.get(id) ?? 'normal'

  // 단지별 설비 상태: 종합상태(tier)를 감시 가능한 대표 설비에 배정
  const stById: Map<number, MachineStatus> = (() => {
    const map = new Map<number, MachineStatus>()
    for (const b of complexes) {
      const st: MachineStatus = {}
      MACHINES.forEach((m) => (st[m.key] = 'normal'))
      const tier = overall(b.id)
      if (tier !== 'normal') {
        const cand = MACHINES.filter((m) => machineMonitored(b, m)).map((m) => m.key)
        if (cand.length > 0) {
          const f1 = cand[b.id % cand.length]
          st[f1] = tier
          const f2 = cand[(b.id * 3 + 2) % cand.length]
          if (f2 !== f1) st[f2] = tier === 'urgent' ? 'caution' : 'normal'
        }
      }
      map.set(b.id, st)
    }
    return map
  })()

  const machineStatus = (id: number): MachineStatus => stById.get(id) ?? {}

  const counts = (id: number): Record<Tier, number> => {
    const c: Record<Tier, number> = { urgent: 0, caution: 0, normal: 0 }
    for (const s of Object.values(machineStatus(id))) c[s]++
    return c
  }

  const summaryCounts = (): Record<Tier, number> => {
    const c: Record<Tier, number> = { urgent: 0, caution: 0, normal: 0 }
    for (const b of complexes) c[overall(b.id)]++
    return c
  }

  return { overall, machineStatus, counts, summaryCounts }
}

// 데모 기본 인스턴스 — 모듈 최상위 import(footprints/mock 등)용. React 트리는 useModel 사용.
const demoModel = createModel(demoTierById)
export const overall = demoModel.overall
export const machineStatus = demoModel.machineStatus
export const counts = demoModel.counts
export const summaryCounts = demoModel.summaryCounts
