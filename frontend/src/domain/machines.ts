/** 기계실 공통 설비 7종 + 배관 — heating_agent.html의 MACHINES/PIPES 이식. */

import type { Complex, SensorKey } from '../data/complexes'

/** 설비 종류 — 아이소메트릭 상단에 얹는 심볼/애니메이션 결정에 사용. */
export type MachineKind = 'pump' | 'hex' | 'tank' | 'valve' | 'panel'

export interface Machine {
  key: string
  name: string
  desc: string
  /** 설비 종류(회전 임펠러/점멸 LED 등 심볼 선택) */
  kind: MachineKind
  /** 아이소메트릭 배치용 그리드 좌표/크기 (RoomSchematic에서 사용) */
  gx: number
  gy: number
  w: number
  d: number
  h: number
  /** 이 설비 감시를 뒷받침하는 PreDist 센서 그룹 키. null = 공통 설비(항상 감시). */
  sens: SensorKey[] | null
}

export const MACHINES: Machine[] = [
  { key: 'hex', name: '판형 열교환기', desc: '1·2차 온도차 / 차압', kind: 'hex', gx: 0.0, gy: 0.0, w: 1.7, d: 1.2, h: 36, sens: ['heatMeter', 'supRet'] },
  { key: 'pump1', name: '1차 순환펌프', desc: '토출압 · 진동 · 베어링', kind: 'pump', gx: 2.6, gy: 0.0, w: 1.0, d: 1.0, h: 26, sens: ['supRet'] },
  { key: 'pump2', name: '2차 순환펌프', desc: '유량 · 전류 · 캐비테이션', kind: 'pump', gx: 2.6, gy: 2.0, w: 1.0, d: 1.0, h: 26, sens: ['space'] },
  { key: 'exp', name: '팽창탱크', desc: '계통 압력 · 질소 · 수위', kind: 'tank', gx: 0.0, gy: 2.3, w: 1.1, d: 1.1, h: 52, sens: null },
  { key: 'makeup', name: '보충수 펌프', desc: '보충 빈도 · 누수 · 경도', kind: 'pump', gx: 4.4, gy: 1.0, w: 0.9, d: 0.9, h: 22, sens: null },
  { key: 'prv', name: '감압밸브 유닛', desc: '2차측 / 급탕 공급압', kind: 'valve', gx: 2.6, gy: 3.8, w: 1.0, d: 0.9, h: 20, sens: ['dhw'] },
  { key: 'ctrl', name: '통합 제어반', desc: '외기 연동 · 알람 · 인터록', kind: 'panel', gx: 4.4, gy: 3.2, w: 1.2, d: 0.8, h: 44, sens: ['outdoor'] },
]

/** 배관 연결(기계 key 쌍) */
export const PIPES: [string, string][] = [
  ['exp', 'hex'], ['hex', 'pump1'], ['hex', 'pump2'],
  ['pump2', 'prv'], ['makeup', 'pump2'], ['ctrl', 'pump2'], ['ctrl', 'hex'],
]

/** 설비의 센서 탑재 여부(감시 가능성) */
export function machineMonitored(b: Complex, m: Machine): boolean {
  if (!m.sens) return true // 공통 설비
  return m.sens.some((k) => b.sensors[k])
}
