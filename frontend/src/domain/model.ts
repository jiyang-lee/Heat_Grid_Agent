/**
 * 파생 모델 — heating_agent.html의 assignTier/overall/counts 이식.
 *
 * 실제 고장 데이터가 없어, README가 '열수요 대리 지표'로 제시한 총관리비 단가(원/㎡)를
 * 내림차순 정렬해 상위 6 = 긴급, 다음 9 = 주의, 나머지 = 정상으로 결정론적 배정한다.
 * 백엔드 alert/risk가 들어오면 tierById/stById 계산만 교체한다.
 */

import { complexes, type Complex } from '../data/complexes'
import type { Tier } from './status'
import { MACHINES, machineMonitored } from './machines'

export type MachineStatus = Record<string, Tier>

export const complexById: Map<number, Complex> = new Map(complexes.map((c) => [c.id, c]))

/** tier: unit 내림차순 상위6 urgent / 다음9 caution / 나머지 normal */
const tierById: Map<number, Tier> = (() => {
  const m = new Map<number, Tier>()
  const sorted = [...complexes].sort((a, b) => b.unit - a.unit)
  sorted.forEach((c, i) => m.set(c.id, i < 6 ? 'urgent' : i < 15 ? 'caution' : 'normal'))
  return m
})()

/** 단지별 설비 상태: 종합상태(tier)를 감시 가능한 대표 설비에 배정 */
const stById: Map<number, MachineStatus> = (() => {
  const map = new Map<number, MachineStatus>()
  for (const b of complexes) {
    const st: MachineStatus = {}
    MACHINES.forEach((m) => (st[m.key] = 'normal'))
    const tier = tierById.get(b.id) ?? 'normal'
    if (tier !== 'normal') {
      const cand = MACHINES.filter((m) => machineMonitored(b, m)).map((m) => m.key)
      const f1 = cand[b.id % cand.length]
      st[f1] = tier
      const f2 = cand[(b.id * 3 + 2) % cand.length]
      if (f2 !== f1) st[f2] = tier === 'urgent' ? 'caution' : 'normal'
    }
    map.set(b.id, st)
  }
  return map
})()

export const overall = (id: number): Tier => tierById.get(id) ?? 'normal'

export const machineStatus = (id: number): MachineStatus => stById.get(id) ?? {}

/** 단지 내 설비 상태별 개수 */
export function counts(id: number): Record<Tier, number> {
  const c: Record<Tier, number> = { urgent: 0, caution: 0, normal: 0 }
  for (const s of Object.values(machineStatus(id))) c[s]++
  return c
}

/** 헤더 요약: 단지 종합상태(tier) 기준 집계 */
export function summaryCounts(): Record<Tier, number> {
  const c: Record<Tier, number> = { urgent: 0, caution: 0, normal: 0 }
  for (const b of complexes) c[overall(b.id)]++
  return c
}
