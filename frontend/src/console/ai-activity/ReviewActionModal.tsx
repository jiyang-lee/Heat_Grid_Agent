/**
 * 운영자 검토 제출 모달 — POST /api/agent-runs/{run_id}/reviews 계약 전용.
 *
 * - disposition은 필수 계약 필드라 숨기지 않고 사용자가 직접 선택한다.
 * - reject/keep_human_review는 reason_category가 필수(빠지면 422).
 * - correct는 교정된 summary/action_plan/caution을 받아 빈 correction을 보내지 않는다.
 * - expected_review_version은 이력의 최신 review_version, idempotency_key는
 *   모달 열림 1회당 1개(재시도에도 동일 키 재사용).
 * - 검토 subject는 run 전체다 — 산출물별 독립 승인처럼 보이지 않게 안내 문구를 고정 표기.
 */

import { useMemo, useState } from 'react'
import type {
  OperatorReviewDecision,
  OperatorReviewDisposition,
  OpsAgentOutput,
  ReasonCategory,
} from '../../api/contracts'
import { ApiError } from '../../api/client'
import { useOperatorReviews, useSubmitOperatorReview } from '../../api/hooks'
import { Button } from '../ui'

const DECISION_TITLES: Record<OperatorReviewDecision, string> = {
  approve: '승인',
  reject: '반려',
  correct: '교정',
  keep_human_review: '사람 검토 유지',
}

const DISPOSITIONS: readonly { value: OperatorReviewDisposition; label: string }[] = [
  { value: 'normal_observation', label: '정상 관찰' },
  { value: 'inspection_recommended', label: '점검 권장' },
  { value: 'urgent_review', label: '긴급 검토' },
]

const REASON_CATEGORIES: readonly { value: ReasonCategory; label: string }[] = [
  { value: 'ml_prediction_issue', label: '모델 예측 문제' },
  { value: 'weather_context_issue', label: '기상 맥락 문제' },
  { value: 'rag_retrieval_issue', label: '내부 근거 검색 문제' },
  { value: 'rag_interpretation_issue', label: '근거 해석 문제' },
  { value: 'fault_analysis_issue', label: '고장 분석 문제' },
  { value: 'escalation_issue', label: '에스컬레이션 문제' },
  { value: 'report_draft_issue', label: '보고서 작성 문제' },
  { value: 'insufficient_evidence', label: '근거 불충분' },
  { value: 'operational_policy_issue', label: '운영 정책 문제' },
]

interface Props {
  readonly runId: string
  readonly decision: OperatorReviewDecision
  readonly currentOutput: OpsAgentOutput | null
  readonly onClose: () => void
}

export function ReviewActionModal({ runId, decision, currentOutput, onClose }: Props) {
  const history = useOperatorReviews(runId)
  const submit = useSubmitOperatorReview()
  const [reviewer, setReviewer] = useState('ops-manager')
  const [reason, setReason] = useState('')
  const [disposition, setDisposition] = useState<OperatorReviewDisposition>('normal_observation')
  const [reasonCategory, setReasonCategory] = useState<ReasonCategory>('insufficient_evidence')
  const [correctedSummary, setCorrectedSummary] = useState(currentOutput?.summary ?? '')
  const [correctedPlan, setCorrectedPlan] = useState(currentOutput?.action_plan ?? '')
  const [correctedCaution, setCorrectedCaution] = useState(currentOutput?.caution ?? '')
  // 모달 열림 1회당 고정 — 제출 재시도에도 같은 키를 보낸다(중복 저장 방지).
  const idempotencyKey = useMemo(() => `ui-${crypto.randomUUID()}`, [])

  const needsCategory = decision === 'reject' || decision === 'keep_human_review'
  const latestVersion = history.data?.items.reduce((max, item) => Math.max(max, item.review_version), 0) ?? 0
  const conflict = submit.error instanceof ApiError && submit.error.status === 409

  const canSubmit =
    reviewer.trim().length > 0 &&
    reason.trim().length > 0 &&
    !submit.isPending &&
    !history.isLoading &&
    (decision !== 'correct' || (correctedSummary.trim() && correctedPlan.trim() && correctedCaution.trim()))

  const handleSubmit = () => {
    submit.mutate(
      {
        runId,
        body: {
          expected_review_version: latestVersion,
          idempotency_key: idempotencyKey,
          decision,
          reviewer: reviewer.trim(),
          reason: reason.trim(),
          disposition,
          ...(needsCategory ? { reason_category: reasonCategory } : {}),
          ...(decision === 'correct'
            ? {
                correction: {
                  corrected_summary: correctedSummary.trim(),
                  corrected_action_plan: correctedPlan.trim(),
                  corrected_caution: correctedCaution.trim(),
                },
              }
            : {}),
        },
      },
      {
        onSuccess: onClose,
        onError: (error) => {
          // stale version 충돌이면 최신 이력을 다시 불러와 expected_review_version을 갱신한다.
          if (error instanceof ApiError && error.status === 409) void history.refetch()
        },
      },
    )
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        aria-label={`${DECISION_TITLES[decision]} 검토 제출`}
        aria-modal="true"
        className="invite-modal review-action-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header>
          <h2>{DECISION_TITLES[decision]}</h2>
          <Button aria-label="검토 창 닫기" icon="x" onClick={onClose} />
        </header>
        <p className="review-scope-note">이 결정은 실행 {runId.slice(0, 8)}…의 산출물 전체(작업지시서·보고서)에 적용됩니다.</p>
        <label>검토자<input onChange={(event) => setReviewer(event.target.value)} value={reviewer} /></label>
        <label>조치 구분(필수)
          <select onChange={(event) => setDisposition(event.target.value as OperatorReviewDisposition)} value={disposition}>
            {DISPOSITIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        {needsCategory && (
          <label>사유 분류(필수)
            <select onChange={(event) => setReasonCategory(event.target.value as ReasonCategory)} value={reasonCategory}>
              {REASON_CATEGORIES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        )}
        <label>사유(필수)
          <textarea onChange={(event) => setReason(event.target.value)} placeholder="결정 사유를 입력하세요" rows={3} value={reason} />
        </label>
        {decision === 'correct' && (
          <>
            <label>교정 요약<textarea onChange={(event) => setCorrectedSummary(event.target.value)} rows={2} value={correctedSummary} /></label>
            <label>교정 조치 계획<textarea onChange={(event) => setCorrectedPlan(event.target.value)} rows={3} value={correctedPlan} /></label>
            <label>교정 주의 사항<textarea onChange={(event) => setCorrectedCaution(event.target.value)} rows={2} value={correctedCaution} /></label>
          </>
        )}
        {conflict && <p className="form-error">다른 검토가 먼저 저장되어 버전이 충돌했습니다. 최신 이력을 반영했으니 내용 확인 후 다시 제출하세요.</p>}
        {submit.isError && !conflict && <p className="form-error">검토 저장에 실패했습니다. 입력값을 확인해 주세요.</p>}
        <footer>
          <Button onClick={onClose}>취소</Button>
          <Button disabled={!canSubmit} onClick={handleSubmit} tone="primary">
            {submit.isPending ? '저장 중' : `${DECISION_TITLES[decision]} 제출`}
          </Button>
        </footer>
      </div>
    </div>
  )
}
