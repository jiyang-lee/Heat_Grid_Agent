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

export const reportRows = [
  ['누수 점검 보고서 - 강남 열원센터', '강남 열원센터', '누수 점검', '2026-07-11 09:15', '높음', '승인 대기'],
  ['압력 이상 분석 보고서 - 서초 온수1', '서초 온수1기계실', '압력 이상 분석', '2026-07-11 08:42', '높음', '승인 대기'],
  ['열교환기 성능 점검 보고서 - 양재', '양재 열교환기실', '열교환기 성능', '2026-07-11 07:58', '중간', '승인 완료'],
  ['센서 이상 진단 보고서 - 방배', '방배 기계실', '센서 이상 진단', '2026-07-11 06:34', '중간', '승인 완료'],
] as const

export const workColumns = [
  { title: '대기', items: ['강남 열원센터 누수 보수', '서초 온수1 압력 조정', '방배 배관 보온 보강'] },
  { title: '승인 완료', items: ['양재 열교환기 세척', '잠실 센서 교체', '송파 밸브 점검'] },
  { title: '현장 진행', items: ['강남 누수 보수 작업', '서초 압력 조정 작업', '방배 보온 보강 작업'] },
  { title: '완료 보고', items: ['양재 열교환기 세척', '잠실 센서 교체', '송파 밸브 점검'] },
] as const

export const users = [
  ['원운영', '운영센터 관리자', '서울에너지공사', '서울 전 권역', '활성'],
  ['이모니', '모니터링 담당자', '서울에너지공사', '서울 강남구', '활성'],
  ['김현장', '현장 점검 담당자', '서울에너지공사', '서울 서남권', '활성'],
  ['박정비', '외부 정비업체', '테크케어(주)', '서울 전 권역', '활성'],
  ['최리드', '운영센터 관리자', '서울에너지공사', '서울 동북권', '휴가'],
] as const

export const settingsHistory = ['2026.07.11 14:32 · 운영자 · 정책 업데이트', '2026.07.09 09:15 · 김설비 · 알림 채널 변경', '2026.07.05 16:40 · 이관제 · 임계값 조정'] as const
