import type { Tone } from './ui'

export interface MockAlertDetail {
  readonly reason: string
  readonly recommendation: string
  readonly events: readonly { readonly time: string; readonly text: string; readonly tone: Tone }[]
}

export const sensorTrend = [0.34, 0.33, 0.34, 0.32, 0.35, 0.31, 0.3, 0.29, 0.26, 0.22, 0.19, 0.15, 0.1, 0.13, 0.07] as const

export const alertDetail: MockAlertDetail = {
  reason: '차압이 평소 대비 빠르게 감소하고 보충수 유량이 증가하는 패턴이 감지되었습니다. 2차측 배관 또는 열교환기 연결부 누수 가능성이 높습니다.',
  recommendation: '현장 누수 점검을 실시하고, 의심 구간 차단 후 압력 유지 테스트를 진행하세요.',
  events: [
    { time: '09:18', text: '누수 위험 감지 (차압 0.12 bar)', tone: 'critical' },
    { time: '09:11', text: '차압 급감 시작 (평균 대비 -0.15 bar)', tone: 'warning' },
    { time: '09:05', text: '보충수 유량 증가 감지 (1.2 m³/h)', tone: 'warning' },
    { time: '08:58', text: '평소 패턴 이탈 감지', tone: 'primary' },
  ],
}

/* reportRows/workColumns(옛 보고서·칸반 목업)는 AI 활동 개편에서 제거 —
 * 실행/작업지시서/보고서는 이제 실계약(agent-runs/work-orders/agent-reports)만 사용한다. */

export const users = [
  ['원운영', '운영센터 관리자', '서울에너지공사', '서울 전 권역', '활성'],
  ['이모니', '모니터링 담당자', '서울에너지공사', '서울 강남구', '활성'],
  ['김현장', '현장 점검 담당자', '서울에너지공사', '서울 서남권', '활성'],
  ['박정비', '외부 정비업체', '테크케어(주)', '서울 전 권역', '활성'],
  ['최리드', '운영센터 관리자', '서울에너지공사', '서울 동북권', '휴가'],
] as const

export const settingsHistory = ['2026.07.11 14:32 · 운영자 · 정책 업데이트', '2026.07.09 09:15 · 김설비 · 알림 채널 변경', '2026.07.05 16:40 · 이관제 · 임계값 조정'] as const
