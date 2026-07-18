/** 완료 run의 실제 OpsAgentResultV4를 공문서형 작업지시서로 표시한다. */

import { useState } from 'react'
import type { OperatorReviewDecision, WorkOrderListItem } from '../../api/contracts'
import { ApiError } from '../../api/client'
import { useAgentRun, useAgentRunResult, useArtifacts, useOperatorReviews } from '../../api/hooks'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from '../ui'
import {
  RAW_REVIEW_STATUS_LABELS,
  facilityName,
  formatDateTime,
  priorityLabel,
  priorityTone,
  reviewStatusTone,
  workOrderStatusLabel,
} from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'

type DetailTab = 'document' | 'history'

const DECISION_LABELS: Record<string, string> = {
  approve: '승인', reject: '반려', correct: '교정', keep_human_review: '수정 요청',
}

function decisionTone(decision: string): Tone {
  if (decision === 'approve') return 'success'
  if (decision === 'reject') return 'critical'
  if (decision === 'correct') return 'warning'
  return 'primary'
}

function splitNumberedSteps(detail: string): string[] {
  const parts = detail.split(/(?=\d+\)\s*)/).map((part) => part.trim()).filter(Boolean)
  return parts.length > 1 ? parts.map((part) => part.replace(/^\d+\)\s*/, '')) : [detail.trim()]
}

function splitCautions(value: string): string[] {
  return value.split(/\s*-\s+/).map((part) => part.trim()).filter(Boolean)
}

function workOrderTitle(value: string | null): string {
  return value?.split(' · ')[0]?.trim() || '설비 이상 작업지시서'
}

interface Props {
  readonly item: WorkOrderListItem
  readonly onClose: () => void
  readonly onOpenReport: (artifactId: string) => void
}

export function WorkOrderDetail({ item, onClose, onOpenReport }: Props) {
  const runId = item.run_id
  const run = useAgentRun(runId)
  const result = useAgentRunResult(runId)
  const artifacts = useArtifacts(runId)
  const reviews = useOperatorReviews(runId)
  const [tab, setTab] = useState<DetailTab>('document')
  const [action, setAction] = useState<OperatorReviewDecision | null>(null)

  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const reportArtifact = artifacts.data?.find((artifact) => artifact.kind === 'anomaly_report' || artifact.kind === 'daily_report') ?? null
  const actions = result.data?.actions ?? []
  const title = workOrderTitle(item.alert_reason)
  const cautionItems = splitCautions(run.data?.ops_output?.caution ?? result.data?.cautions.join(' ') ?? '')

  return (
    <SurfaceCard
      action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />}
      className="activity-detail"
      title="작업지시서 상세"
    >
      <div className="detail-body">
        <div className="detail-title">
          <div className="activity-detail-badges">
            <StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge>
            <span title={RAW_REVIEW_STATUS_LABELS[item.operator_review_status]}>
              <StatusBadge tone={reviewStatusTone(item.operator_review_status)}>{workOrderStatusLabel(item.operator_review_status)}</StatusBadge>
            </span>
          </div>
          <h2>{title}</h2>
          <p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p>
          <span>지시서 ID {runId.slice(0, 8)}… · 생성 {formatDateTime(item.created_at)}</span>
          {reportArtifact && (
            <button className="text-link" onClick={() => onOpenReport(reportArtifact.artifact_id)} type="button">
              연결 보고서 보기
            </button>
          )}
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {([['document', '작업지시서'], ['history', '검토 이력']] as const).map(([key, label]) => (
            <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => setTab(key)} role="tab" type="button">{label}</button>
          ))}
        </div>

        {tab === 'document' && (
          <section role="tabpanel">
            <ApiState empty={false} error={result.isError && !resultNotReady} loading={result.isLoading || run.isLoading} retry={() => void result.refetch()} />
            {resultNotReady && <p className="activity-empty-note">실행이 아직 완료되지 않아 작업지시서가 준비되지 않았습니다.</p>}
            {result.data && (
              <article className="work-order-document">
                <header>
                  <div><small>AI 작업지시서</small><h3>{title}</h3></div>
                  <StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge>
                </header>
                <dl>
                  <div><dt>지시서 번호</dt><dd>{runId.slice(0, 8).toUpperCase()}</dd></div>
                  <div><dt>대상 설비</dt><dd>{facilityName(item.substation_id, item.manufacturer_id)}</dd></div>
                  <div><dt>생성 시간</dt><dd>{formatDateTime(item.created_at)}</dd></div>
                  <div><dt>생성 모델</dt><dd>{run.data?.token_usage?.cost_estimate?.model ?? '확인 중'}</dd></div>
                </dl>
                <section>
                  <h4>1. 작업 목적</h4>
                  <p>{title} 대응을 위한 현장 점검과 안전 조치를 수행합니다.</p>
                </section>
                <section>
                  <h4>2. 작업 절차</h4>
                  <ol className="activity-action-list work-order-steps">
                    {actions.flatMap((entry) => splitNumberedSteps(entry.detail).map((step, index) => (
                      <li key={`${entry.priority}-${index}`}>
                        <strong>{index === 0 ? entry.title : `${entry.title} ${index + 1}`}</strong>
                        <span>{step}</span>
                      </li>
                    )))}
                    {actions.length === 0 && <li><span>등록된 작업 항목이 없습니다.</span></li>}
                  </ol>
                </section>
                <section className="caution">
                  <h4>3. 안전 확인</h4>
                  <ul className="work-order-cautions">
                    {cautionItems.map((caution) => <li key={caution}>{caution}</li>)}
                    {cautionItems.length === 0 && <li>확인할 안전 주의사항이 없습니다.</li>}
                  </ul>
                </section>
              </article>
            )}
          </section>
        )}

        {tab === 'history' && (
          <section role="tabpanel">
            <ApiState empty={false} error={reviews.isError} loading={reviews.isLoading} retry={() => void reviews.refetch()} />
            {reviews.data && reviews.data.items.length === 0 && <p className="activity-empty-note">검토 이력이 없습니다.</p>}
            {reviews.data && reviews.data.items.length > 0 && (
              <ul className="review-history">
                {[...reviews.data.items].sort((a, b) => b.review_version - a.review_version).map((record) => (
                  <li key={record.review_id}>
                    <header>
                      <StatusBadge tone={decisionTone(record.decision)}>{DECISION_LABELS[record.decision] ?? record.decision}</StatusBadge>
                      <strong>{record.reviewer}</strong>
                      <time>{formatDateTime(record.created_at)}</time>
                    </header>
                    <span>{record.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <div className="detail-actions activity-actions activity-actions-sticky">
          <Button onClick={() => setAction('keep_human_review')}>수정 요청</Button>
          <Button onClick={() => setAction('approve')} tone="primary">승인</Button>
          <Button onClick={() => setAction('reject')} tone="danger">반려</Button>
        </div>
      </div>

      {action && (
        <ReviewActionModal
          currentOutput={run.data?.ops_output ?? null}
          decision={action}
          onClose={() => setAction(null)}
          runId={runId}
        />
      )}
    </SurfaceCard>
  )
}
