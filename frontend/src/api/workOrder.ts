/**
 * 작업 지시서(LLM OpsAgentOutput) 생성.
 *
 * 계약: OpsAgentOutput{summary, action_plan, caution} (contracts.ts).
 * 지금은 mock 우선 — 단지/설비 상태로 결정론적 지시서를 합성한다.
 * 백엔드 준비 시 VITE_USE_MOCK=false 로 두면 실 LLM 경로로 전환한다(아래 TODO).
 *
 * 실백엔드 경로(추후): GET /cards?search=<substation_id> → card_id(UUID)
 *   → POST /simulate/{card_id} (즉석) 또는 alert 기반 POST /api/agent-runs.
 *   (프론트 단지 id 1~31은 백엔드 card UUID와 별개라 /cards 검색으로 다리를 놓아야 함)
 */

import type { Complex } from '../data/complexes'
import type { OpsAgentOutput } from './contracts'
import { MACHINES, machineMonitored } from '../domain/machines'
import { machineStatus, overall } from '../domain/model'
import { STATUS } from '../domain/status'
import { USE_MOCK } from './config'

export type WorkOrderMode = 'mock' | 'llm' | 'fallback'

export interface WorkOrderResult {
  output: OpsAgentOutput
  mode: WorkOrderMode
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export async function generateWorkOrder(complex: Complex): Promise<WorkOrderResult> {
  if (USE_MOCK) {
    await delay(900) // 생성 체감용
    return { output: buildMockOpsOutput(complex), mode: 'mock' }
  }
  // TODO(실백엔드): /cards?search=substation_id 로 card_id 조회 후
  //   POST /simulate/{card_id} 또는 POST /api/agent-runs 로 교체.
  throw new Error('실백엔드 작업지시서 경로가 아직 배선되지 않았습니다. VITE_USE_MOCK=true로 두세요.')
}

const MACHINE_ACTION: Record<string, string> = {
  hex: '판형 열교환기 1·2차 온도차·차압 확인, 스케일/막힘 여부 점검',
  pump1: '1차 순환펌프 토출압·진동·베어링 온도 점검, 필요 시 예비펌프 절체',
  pump2: '2차 순환펌프 유량·전류 확인, 캐비테이션/공기 혼입 점검',
  exp: '팽창탱크 계통 압력·질소 봉압·수위 확인',
  makeup: '보충수 펌프 보충 빈도·누수 여부 점검',
  prv: '감압밸브 2차측·급탕 공급압 설정치 확인',
  ctrl: '통합 제어반 외기 연동·알람·인터록 상태 확인',
}

/** 단지/설비 상태로 결정론적 OpsAgentOutput 합성. mock agent-run에서도 재사용. */
export function buildMockOpsOutput(c: Complex): OpsAgentOutput {
  const tier = overall(c.id)
  const st = machineStatus(c.id)
  const flagged = MACHINES.filter((m) => (st[m.key] ?? 'normal') !== 'normal').sort(
    (a, b) => STATUS[st[b.key]].sev - STATUS[st[a.key]].sev,
  )
  const noSensor = MACHINES.filter((m) => !machineMonitored(c, m))

  if (tier === 'normal' || flagged.length === 0) {
    return {
      summary: `${c.id}. ${c.name} — 총관리비 단가 ${c.unit.toLocaleString()}원/㎡ 기준 현재 정상 운영 중입니다. 즉시 조치가 필요한 설비는 없습니다.`,
      action_plan: '1) 정기 순회 점검 유지\n2) 외기 연동 제어·알람 이력 확인\n3) 다음 점검 주기까지 추세 모니터링',
      caution: '· 상태는 총관리비 단가(열수요 대리 지표) 기반 데모값입니다(실제 고장 아님). 실 LLM 연동 시 DB 근거로 대체됩니다.',
    }
  }

  const worst = flagged[0]
  const steps = flagged.slice(0, 3).map((m, i) => `${i + 1}) [${STATUS[st[m.key]].ko}] ${MACHINE_ACTION[m.key]}`)
  steps.push(`${steps.length + 1}) 조치 후 ${tier === 'urgent' ? '2시간' : '당일'} 내 재평가`)

  return {
    summary:
      `${c.id}. ${c.name} — 총관리비 단가 ${c.unit.toLocaleString()}원/㎡ 기준 ${STATUS[tier].ko} 우선순위입니다. ` +
      `우선 점검 대상은 ${flagged.map((m) => m.name).join(', ')}이며, 최우선은 ${worst.name}입니다.`,
    action_plan: steps.join('\n'),
    caution:
      (noSensor.length
        ? `· ${noSensor.map((m) => m.name).join(', ')}는 해당 PreDist 센서 미탑재로 원격 감시가 불가하니 현장 확인이 필요합니다. `
        : '· 감시 설비 전 항목 센서 확보. ') +
      '상태는 총관리비 단가 기반 데모값이며, 실 LLM 연동 시 DB 근거로 대체됩니다.',
  }
}
