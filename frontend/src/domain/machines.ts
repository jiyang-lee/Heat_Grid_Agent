/** 기계실 공통 설비 7종 + 배관 — heating_agent.html의 MACHINES/PIPES 이식. */

import type { Complex, SensorKey } from '../data/complexes'

/** 설비 종류 — 아이소메트릭 상단에 얹는 심볼/애니메이션 결정에 사용. */
export type MachineKind = 'pump' | 'hex' | 'tank' | 'valve' | 'panel'

export interface Machine {
  key: string
  name: string
  desc: string
  /** 설비 종류(이미지 플레이스홀더/그룹 구분) */
  kind: MachineKind
  /** 이미지 배치 앵커 — 스테이지 기준 백분율 중심(ax,ay)과 상대 크기(scale) */
  ax: number
  ay: number
  scale: number
  /** (구) 아이소메트릭 배치용 그리드 좌표/크기 — 현재 뷰에서는 미사용, 참고용 보존 */
  gx: number
  gy: number
  w: number
  d: number
  h: number
  /** 이 설비 감시를 뒷받침하는 PreDist 센서 그룹 키. null = 공통 설비(항상 감시). */
  sens: SensorKey[] | null
}

// ax/ay = 스테이지 기준 중심 백분율(.mtile은 translate(-50%,-50%)).
// 참조 배치(왼→오 공정 순): ①1차펌프 ②판형열교환기 ③2차펌프 ④팽창탱크 ⑤감압밸브 ⑥보충수펌프 ⑦제어반.
// 큰 설비(①②③④⑦)는 상단 한 줄, 소형 유닛(⑤감압밸브·⑥보충수)은 팽창탱크와 제어반 사이 전경(하단)에 배치.
export const MACHINES: Machine[] = [
  { key: 'exp', name: '팽창탱크', desc: '계통 압력 · 질소 · 수위', kind: 'tank', ax: 63, ay: 42, scale: 1.0, gx: 0.0, gy: 2.3, w: 1.1, d: 1.1, h: 52, sens: null },
  { key: 'hex', name: '판형 열교환기', desc: '1·2차 온도차 / 차압', kind: 'hex', ax: 30, ay: 49, scale: 1.15, gx: 0.0, gy: 0.0, w: 1.7, d: 1.2, h: 36, sens: ['heatMeter', 'supRet'] },
  { key: 'pump1', name: '1차 순환펌프', desc: '토출압 · 진동 · 베어링', kind: 'pump', ax: 13, ay: 49, scale: 0.92, gx: 2.6, gy: 0.0, w: 1.0, d: 1.0, h: 26, sens: ['supRet'] },
  { key: 'pump2', name: '2차 순환펌프', desc: '유량 · 전류 · 캐비테이션', kind: 'pump', ax: 46, ay: 49, scale: 0.92, gx: 2.6, gy: 2.0, w: 1.0, d: 1.0, h: 26, sens: ['space'] },
  { key: 'makeup', name: '보충수 펌프', desc: '보충 빈도 · 누수 · 경도', kind: 'pump', ax: 77, ay: 72, scale: 0.76, gx: 4.4, gy: 1.0, w: 0.9, d: 0.9, h: 22, sens: null },
  { key: 'prv', name: '감압밸브 유닛', desc: '2차측 / 급탕 공급압', kind: 'valve', ax: 60, ay: 73, scale: 0.72, gx: 2.6, gy: 3.8, w: 1.0, d: 0.9, h: 20, sens: ['dhw'] },
  { key: 'ctrl', name: '통합 제어반', desc: '외기 연동 · 알람 · 인터록', kind: 'panel', ax: 88, ay: 50, scale: 1.02, gx: 4.4, gy: 3.2, w: 1.2, d: 0.8, h: 44, sens: ['outdoor'] },
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
