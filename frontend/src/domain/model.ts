/** 정적 단지/기계 메타데이터. 운영 Priority 상태는 백엔드 평가 API가 정본이다. */

import { complexes, type Complex } from '../data/complexes'
import type { Tier } from './status'
import { MACHINES } from './machines'

export type MachineStatus = Record<string, Tier>

export const complexById: Map<number, Complex> = new Map(complexes.map((c) => [c.id, c]))

/** 설비별 실시간 모델 출력은 아직 없으므로 기계실 상태를 임의로 만들지 않는다. */
const stById: Map<number, MachineStatus> = (() => {
  const map = new Map<number, MachineStatus>()
  for (const b of complexes) {
    const st: MachineStatus = {}
    MACHINES.forEach((m) => (st[m.key] = 'normal'))
    map.set(b.id, st)
  }
  return map
})()

export const overall = (_id: number): Tier => 'normal'

export const machineStatus = (id: number): MachineStatus => stById.get(id) ?? {}

/** 단지 내 설비 상태별 개수 */
export function counts(id: number): Record<Tier, number> {
  const c: Record<Tier, number> = { urgent: 0, caution: 0, normal: 0 }
  for (const s of Object.values(machineStatus(id))) c[s]++
  return c
}

/** 헤더 요약: 단지 종합상태(tier) 기준 집계 */
export function summaryCounts(): Record<Tier, number> {
  return { urgent: 0, caution: 0, normal: complexes.length }
}
