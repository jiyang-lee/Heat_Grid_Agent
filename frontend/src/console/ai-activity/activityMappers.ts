/**
 * AI 활동 페이지 표시 규칙의 단일 정의처.
 *
 * - raw 백엔드 상태(run status / operator review status / stage name)를
 *   사용자 표시 문구·톤으로 변환하는 mapper를 한 곳에서 관리한다.
 * - 내부 9단계 stage(STAGE_ORDER)를 사용자 6단계로 투영한다.
 * - 의미가 불확실한 상태를 임의로 '승인 완료'로 올려붙이지 않는다
 *   (corrected는 '수정 요청'으로 표시하되 raw를 tooltip으로 보존).
 */

import type {
  AgentRunListItem,
  AgentRunStatus,
  OperatorReviewStatus,
  StageName,
} from '../../api/contracts'
import type { Tone } from '../ui'
import { complexNameOf } from '../../domain/model'

/* ===== 사용자 6단계 stepper ===== */

export const USER_STEPS = ['알림 감지', '데이터 수집', 'AI 판단', '보고서 생성', '작업지시서 초안', '완료'] as const

/** 내부 stage → 사용자 단계 index(0-based). */
const STAGE_TO_STEP: Record<StageName, number> = {
  ml_validation: 1,
  weather_context: 1,
  rag_retrieval: 1,
  rag_interpretation: 2,
  fault_analysis: 2,
  higher_model_reassessment: 2,
  parent_disposition: 2,
  report_draft: 3,
  report_fidelity: 3,
}

export interface StepperState {
  /** 0-based 현재 단계 index */
  readonly currentIndex: number
  /** 실패 시 실패한 단계에서 빨강으로 멈춘다 */
  readonly failed: boolean
  /** n / 6 단계 표기용(1-based) */
  readonly stepNumber: number
}

/**
 * run 상태 + stage 기록으로 사용자 단계를 계산한다.
 * iterations 개수 휴리스틱을 쓰지 않는다(지시서 §5).
 */
export function deriveStepper(input: {
  readonly status: AgentRunStatus
  readonly currentStage: StageName | null
  readonly hasResult: boolean
}): StepperState {
  if (input.status === 'completed') {
    return { currentIndex: 5, failed: false, stepNumber: 6 }
  }
  const stageStep = input.currentStage ? STAGE_TO_STEP[input.currentStage] : 0
  // result(작업지시서 초안 근거)가 이미 있으면 4단계까지 진행한 것으로 본다.
  const index = Math.max(stageStep, input.hasResult ? 4 : 0)
  return {
    currentIndex: index,
    failed: input.status === 'failed',
    stepNumber: index + 1,
  }
}

export const STAGE_LABELS: Record<StageName, string> = {
  ml_validation: '모델 검증',
  weather_context: '기상 맥락 수집',
  rag_retrieval: '내부 근거 검색',
  rag_interpretation: '근거 해석',
  fault_analysis: '고장 원인 분석',
  higher_model_reassessment: '상위 모델 재평가',
  parent_disposition: '판단 확정',
  report_draft: '보고서 초안',
  report_fidelity: '보고서 검증',
}

/* ===== 실행 활동 상태 ===== */

export type ExecutionStatusLabel = '대기' | '승인' | '문서 완료' | '오류'

export function executionStatus(item: Pick<AgentRunListItem, 'status' | 'operator_review_status'>): ExecutionStatusLabel {
  if (item.status === 'failed') return '오류'
  if (item.operator_review_status === 'approved') return '승인'
  if (item.status === 'completed') return '문서 완료'
  return '대기'
}

export function executionStatusTone(label: ExecutionStatusLabel): Tone {
  if (label === '오류') return 'critical'
  if (label === '승인') return 'success'
  if (label === '문서 완료') return 'primary'
  return 'neutral'
}

/** 실행 활동 처리 상태 필터 옵션 → 서버 쿼리 값 매핑 */
export const EXECUTION_STATUS_FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'waiting', label: '대기' },
  { value: 'approved', label: '승인' },
  { value: 'document_complete', label: '문서 완료' },
] as const

export type ExecutionStatusFilter = (typeof EXECUTION_STATUS_FILTERS)[number]['value']

/* ===== 작업지시서/보고서 상태 ===== */

/**
 * 검토 상태 4값(docs/report/04) → 사용자 3상태 projection.
 * corrected(교정 저장)는 승인과 동등하지 않으므로 '수정 요청'으로 표시하고 raw를 보존한다.
 */
export function workOrderStatusLabel(status: OperatorReviewStatus): '승인 대기' | '수정 요청' | '승인 완료' {
  if (status === 'approved') return '승인 완료'
  if (status === 'pending') return '승인 대기'
  return '수정 요청'
}

export function reportStatusLabel(status: OperatorReviewStatus): '검토 대기' | '수정 요청' | '승인 완료' {
  if (status === 'approved') return '승인 완료'
  if (status === 'pending') return '검토 대기'
  return '수정 요청'
}

export function reviewStatusTone(status: OperatorReviewStatus): Tone {
  if (status === 'approved') return 'success'
  if (status === 'pending') return 'notice'
  return 'warning'
}

export const RAW_REVIEW_STATUS_LABELS: Record<OperatorReviewStatus, string> = {
  pending: '결정 없음(pending)',
  approved: '승인 저장됨(approved)',
  corrected: '교정 저장됨(corrected)',
  keep_human_review: '사람 검토 유지(keep_human_review)',
}

/** 작업지시서/보고서 탭 처리 상태 필터 → 서버 operator_review_status 매핑 */
export const REVIEW_STATUS_FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'pending', label: '대기' },
  { value: 'keep_human_review', label: '수정 요청' },
  { value: 'approved', label: '승인 완료' },
] as const

export type ReviewStatusFilter = (typeof REVIEW_STATUS_FILTERS)[number]['value']

/* ===== 우선순위/설비/보고서명/시간 ===== */

export function priorityLabel(priority: string | null): string {
  if (priority === 'urgent') return '심각'
  if (priority === 'high') return '경고'
  return priority ?? '-'
}

export function priorityTone(priority: string | null): Tone {
  return priority === 'urgent' ? 'critical' : 'warning'
}

export function facilityName(substationId: number | null, manufacturerId: string | null): string {
  return complexNameOf(substationId, manufacturerId)
}

export const REPORT_KIND_LABELS: Record<string, string> = {
  anomaly_report: '이상 분석 보고서',
  daily_report: '일일 운영 보고서',
}

export function reportTitle(kind: string, name: string): string {
  const label = REPORT_KIND_LABELS[kind]
  return label ? label : name
}

/** ko-KR 시각 표시. invalid/null 안전. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return '-'
  return at.toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })
}

/* ===== 기간 필터 ===== */

export const PERIOD_FILTERS = [
  { value: '24h', label: '최근 24시간', hours: 24 },
  { value: '7d', label: '최근 7일', hours: 24 * 7 },
  { value: '30d', label: '최근 30일', hours: 24 * 30 },
  { value: 'all', label: '전체 기간', hours: null },
] as const

export type PeriodFilter = (typeof PERIOD_FILTERS)[number]['value']

export function periodToCreatedFrom(period: PeriodFilter): string | undefined {
  const hours = PERIOD_FILTERS.find((item) => item.value === period)?.hours
  if (hours == null) return undefined
  return new Date(Date.now() - hours * 3_600_000).toISOString()
}
