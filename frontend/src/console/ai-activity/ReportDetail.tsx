/**
 * 보고서 상세 — report artifact + 해당 run의 OpsAgentResultV4/검토 스냅샷을 표시한다.
 * 내려받기는 실제 artifact 파일 형식 그대로 안내한다(PDF로 가장하지 않음).
 */

import { useState } from 'react'
import type { AgentReportListItem, OperatorReviewDecision } from '../../api/contracts'
import { API_BASE, ApiError } from '../../api/client'
import {
  useAgentRun,
  useAgentRunResult,
  useAgentRunReviewSnapshot,
  useOperatorReviews,
} from '../../api/hooks'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from '../ui'
import {
  RAW_REVIEW_STATUS_LABELS,
  facilityName,
  formatDateTime,
  priorityLabel,
  priorityTone,
  reportStatusLabel,
  reportTitle,
  reviewStatusTone,
} from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'

type DetailTab = 'summary' | 'evidence' | 'actions' | 'references' | 'history'

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
  readonly item: AgentReportListItem
  readonly onClose: () => void
}

export function ReportDetail({ item, onClose }: Props) {
  const runId = item.run_id
  const run = useAgentRun(runId)
  const result = useAgentRunResult(runId)
  const review = useAgentRunReviewSnapshot(runId)
  const reviews = useOperatorReviews(runId)
  const [tab, setTab] = useState<DetailTab>('summary')
  const [action, setAction] = useState<OperatorReviewDecision | null>(null)

  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const snapshot = review.data?.snapshot ?? null
  const fileExtension = item.name.includes('.') ? item.name.split('.').at(-1)?.toUpperCase() : null
  const downloadUrl = `${API_BASE}/agent-runs/${runId}/artifacts/${item.artifact_id}/content`

  return (
    <SurfaceCard
      action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />}
      className="activity-detail"
      title="보고서 상세"
    >
      <div className="detail-body">
        <div className="detail-title">
          <div className="activity-detail-badges">
            <StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge>
            <span title={RAW_REVIEW_STATUS_LABELS[item.operator_review_status]}>
              <StatusBadge tone={reviewStatusTone(item.operator_review_status)}>{reportStatusLabel(item.operator_review_status)}</StatusBadge>
            </span>
          </div>
          <h2>{result.data?.report.title ?? reportTitle(item.kind, item.name)}</h2>
          <p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p>
          <span>보고서 ID {item.artifact_id.slice(0, 8)}… · 생성 {formatDateTime(item.created_at)} · 작성 주체 AI 자동 생성</span>
          <div className="activity-title-actions">
            <a className="text-link" download={item.name} href={downloadUrl}>
              {fileExtension ? `${fileExtension} 파일 내려받기` : '파일 내려받기'}
            </a>
          </div>
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {([['summary', '보고서 요약'], ['evidence', '판단 근거'], ['actions', '권장 조치'], ['references', '참고 자료'], ['history', '수정 이력']] as const).map(([key, label]) => (
            <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => setTab(key)} role="tab" type="button">{label}</button>
          ))}
        </div>

        {tab === 'summary' && (
          <section role="tabpanel">
            <ApiState empty={false} error={result.isError && !resultNotReady} loading={result.isLoading} retry={() => void result.refetch()} />
            {resultNotReady && <p className="activity-empty-note">실행이 완료되지 않아 보고서 본문이 준비되지 않았습니다.</p>}
            {result.data && (
              <>
                <article className="activity-evidence-card highlight">
                  <h3>AI 요약</h3>
                  <p>{result.data.situation}</p>
                </article>
                <article className="activity-evidence-card">
                  <h3>보고서 본문 ({result.data.report.format})</h3>
                  <pre className="activity-report-body">{result.data.report.content}</pre>
                </article>
              </>
            )}
          </section>
        )}

        {tab === 'evidence' && (
          <section role="tabpanel">
            <ApiState empty={false} error={review.isError} loading={review.isLoading} retry={() => void review.refetch()} />
            {!snapshot && review.data && <p className="activity-empty-note">{review.data.unavailable_reason ?? '판단 근거 스냅샷이 없습니다.'}</p>}
            {snapshot && (
              <>
                <article className="activity-evidence-card">
                  <h3>판단 요약</h3>
                  <p>{snapshot.handling_reason}</p>
                </article>
                {snapshot.model_verification && (
                  <article className="activity-evidence-card">
                    <h3>모델 재검증</h3>
                    <p><StatusBadge tone={snapshot.model_verification.status === 'verified' ? 'success' : 'warning'}>{snapshot.model_verification.status}</StatusBadge> {snapshot.model_verification.reason}</p>
                  </article>
                )}
                {snapshot.decisions.length > 0 && (
                  <article className="activity-evidence-card">
                    <h3>판단 과정</h3>
                    <ol className="activity-action-list">
                      {snapshot.decisions.map((step) => (
                        <li key={step.sequence}><strong>{step.decision}</strong><span>{step.reason}</span></li>
                      ))}
                    </ol>
                  </article>
                )}
              </>
            )}
          </section>
        )}

        {tab === 'actions' && (
          <section role="tabpanel">
            {result.data ? (
              <ol className="activity-action-list">
                {result.data.actions.map((entry) => (
                  <li key={entry.priority}><strong>{entry.title}</strong><span>{entry.detail}</span></li>
                ))}
                {result.data.actions.length === 0 && <li><span>권장 조치가 없습니다.</span></li>}
              </ol>
            ) : <p className="activity-empty-note">{resultNotReady ? '실행 미완료로 권장 조치가 없습니다.' : '데이터 없음'}</p>}
          </section>
        )}

        {tab === 'references' && (
          <section role="tabpanel">
            {snapshot && snapshot.evidence.length > 0 ? (
              <ul className="review-history">
                {snapshot.evidence.map((entry) => (
                  <li key={entry.evidence_id}>
                    <header>
                      <StatusBadge tone="neutral">{entry.document_type === 'internal_rag' ? '내부 문서' : '운영 노트'}</StatusBadge>
                      <strong>{entry.title}</strong>
                    </header>
                    <span>{entry.excerpt}</span>
                    <small>출처: {entry.source}{entry.section ? ` · ${entry.section}` : ''}</small>
                  </li>
                ))}
              </ul>
            ) : <p className="activity-empty-note">참고 자료가 없습니다.</p>}
            {snapshot?.weather && (
              <p className="activity-empty-note">
                기상 맥락: {snapshot.weather.temperature_c != null ? `외기 ${snapshot.weather.temperature_c}°C` : '데이터 없음'} (출처 {snapshot.weather.provenance.source}) — 기상은 부하 맥락 참고용이며 원인 확정 근거가 아닙니다.
              </p>
            )}
          </section>
        )}

        {tab === 'history' && (
          <section role="tabpanel">
            <ApiState empty={false} error={reviews.isError} loading={reviews.isLoading} retry={() => void reviews.refetch()} />
            {reviews.data && reviews.data.items.length === 0 && <p className="activity-empty-note">수정 이력이 없습니다.</p>}
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
                    {record.correction && <small>교정 요약: {record.correction.corrected_summary ?? '-'}</small>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <p className="review-scope-note">아래 결정은 이 실행의 산출물 전체(작업지시서·보고서)에 적용됩니다.</p>
        <div className="detail-actions activity-actions">
          <Button onClick={() => setAction('keep_human_review')}>수정 요청</Button>
          <Button onClick={() => setAction('approve')} tone="primary">✓ 승인</Button>
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
