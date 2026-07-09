/** 상태(tier) 정의 — heating_agent.html의 STATUS 이식. */

export type Tier = 'urgent' | 'caution' | 'normal'

export const STATUS: Record<Tier, { ko: string; color: string; sev: number }> = {
  urgent: { ko: '긴급', color: '#ff1744', sev: 3 },
  caution: { ko: '주의', color: '#ffc400', sev: 2 },
  normal: { ko: '정상', color: '#00e676', sev: 1 },
}

export const sev = (t: Tier): number => STATUS[t].sev
