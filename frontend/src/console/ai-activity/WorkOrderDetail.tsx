/**
 * 작업지시서 상세 — 완료 run의 OpsAgentResultV4를 작업지시서로 표시한다.
 * 담당자/연락처/현장 첨부는 백엔드 계약에 없으므로 '미지정'으로 정직하게 표시하고,
 * 체크리스트 완료 여부는 저장 API가 없어 개수만 보여준다(가짜 완료 수 금지).
 */

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

type DetailTab = 'info' | 'checklist' | 'field' | 'history'

const DECISION_LABELS: Record<string, string> = {
  approve: '승인', reject: '반려', correct: '교정', keep_human_review: '수정 요청',
}

function decisionTone(decision: string): Tone {
  if (decision === 'approve') return 'success'
  if (decision === 'reject') return 'critical'
  if (decision === 'correct') return 'warning'
  return 'primary'
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
  const [tab, setTab] = useState<DetailTab>('info')
  const [action, setAction] = useState<OperatorReviewDecision | null>(null)

  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const reportArtifact = artifacts.data?.find((artifact) => artifact.kind === 'anomaly_report' || artifact.kind === 'daily_report') ?? null
  const actions = result.data?.actions ?? []

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
          <h2>{result.data?.headline ?? item.alert_reason ?? '작업지시서'}</h2>
          <p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p>
          <span>지시서 ID {runId.slice(0, 8)}… · 생성 {formatDateTime(item.created_at)}</span>
          {reportArtifact && (
            <button className="text-link" onClick={() => onOpenReport(reportArtifact.artifact_id)} type="button">
              연결 보고서 보기
            </button>
          )}
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {([['info', '작업 정보'], ['checklist', '체크리스트'], ['field', '현장 기록'], ['history', '이력']] as const).map(([key, label]) => (
            <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => setTab(key)} role="tab" type="button">{label}</button>
          ))}
        </div>

        {tab === 'info' && (
          <section role="tabpanel">
            <ApiState empty={false} error={result.isError && !resultNotReady} loading={result.isLoading || run.isLoading} retry={() => void result.refetch()} />
            {resultNotReady && <p className="activity-empty-note">실행이 아직 완료되지 않아 작업지시서가 준비되지 않았습니다.</p>}
            {result.data && (
              <>
                <article className="activity-evidence-card">
                  <h3>작업 목적</h3>
                  <p>{run.data?.ops_output?.summary ?? result.data.situation}</p>
                </article>
                <div className="work-order-meta activity-order-meta">
                  <span>우선순위 <strong>{priorityLabel(item.priority)}</strong></span>
                  <span>생성 시간 <strong>{formatDateTime(item.created_at)}</strong></span>
                  <span>담당자 <strong>미지정</strong></span>
                  <span>연락처 <strong>미지정</strong></span>
                </div>
                <article className="activity-evidence-card">
                  <h3>작업 내용</h3>
                  <ol className="activity-action-list">
                    {actions.map((entry) => (
                      <li key={entry.priority}><strong>{entry.title}</strong><span>{entry.detail}</span></li>
                    ))}
                    {actions.length === 0 && <li><span>등록된 작업 항목이 없습니다.</span></li>}
                  </ol>
                </article>
                <article className="activity-evidence-card caution">
                  <h3>안전 확인</h3>
                  <p>{run.data?.ops_output?.caution ?? result.data.cautions.join(' ') ?? '데이터 없음'}</p>
                </article>
                <p className="activity-empty-note">첨부 파일: 등록된 파일 없음 (현장 첨부 계약 미지원)</p>
              </>
            )}
          </section>
        )}

        {tab === 'checklist' && (
          <section role="tabpanel">
            {actions.length === 0 && <p className="activity-empty-note">체크리스트로 만들 작업 항목이 없습니다.</p>}
            {actions.length > 0 && (
              <>
                <p className="activity-empty-note">체크리스트 {actions.length}개 항목 — 완료 여부 저장 기능 미연동(0/{actions.length})</p>
                <ul className="activity-checklist">
                  {actions.map((entry) => (
                    <li key={entry.priority}><input aria-label={`${entry.title} (저장 미지원)`} disabled type="checkbox" /><span>{entry.title}</span></li>
                  ))}
                </ul>
              </>
            )}
          </section>
        )}

        {tab === 'field' && (
          <section role="tabpanel">
            <p className="activity-empty-note">현장 기록 저장 API가 아직 없어 표시할 기록이 없습니다.</p>
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

        <p className="review-scope-note">아래 결정은 이 실행의 산출물 전체(작업지시서·보고서)에 적용됩니다.</p>
        <div className="detail-actions activity-actions">
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
