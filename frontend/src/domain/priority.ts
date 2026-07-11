import type { PriorityEvaluationResult } from '../api/contracts'

export type PriorityDisplayStatus = 'urgent' | 'high' | 'medium' | 'low' | 'stale' | 'missing'

export function priorityDisplayStatus(result: PriorityEvaluationResult | undefined): PriorityDisplayStatus {
  if (!result || result.freshness_status === 'missing') return 'missing'
  if (result.freshness_status === 'stale') return 'stale'
  const level = result.priority_level?.toLowerCase()
  if (level === 'urgent') return 'urgent'
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  return 'low'
}

export const PRIORITY_STATUS_LABEL: Record<PriorityDisplayStatus, string> = {
  urgent: '긴급',
  high: '높음',
  medium: '중간',
  low: '낮음',
  stale: '지연',
  missing: '데이터 없음',
}

export function formatMetric(value: number | null, digits = 1): string {
  return value == null ? '-' : value.toFixed(digits)
}
