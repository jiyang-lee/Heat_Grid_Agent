/**
 * 실행 활동 상세 — 6단계 stepper(stages API 정본) + 진행 현황/판단 근거/검토 이력.
 * 판단 근거는 검토 스냅샷 V1 실데이터만 사용하고, 없는 값은 '데이터 없음'으로 정직하게 표시한다.
 */

import { useState } from 'react'
import type { AgentRunListItem, OperatorReviewDecision, StageProjection } from '../../api/contracts'
import {
  useAgentIterations,
  useAgentRun,
  useAgentRunReviewSnapshot,
  useOperatorReviews,
  useRunStages,
} from '../../api/hooks'
import { Icon } from '../icons'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from '../ui'
import {
  STAGE_LABELS,
  USER_STEPS,
  deriveStepper,
  executionStatus,
  executionStatusTone,
  facilityName,
  formatDateTime,
  priorityLabel,
  priorityTone,
} from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'

type DetailTab = 'progress' | 'evidence' | 'reviews'

const DECISION_LABELS: Record<string, string> = {
  approve: '승인', reject: '반려', correct: '교정', keep_human_review: '사람 검토 유지',
}

function decisionTone(decision: string): Tone {
  if (decision === 'approve') return 'success'
  if (decision === 'reject') return 'critical'
  if (decision === 'correct') return 'warning'
  return 'primary'
}

interface Props {
  readonly item: AgentRunListItem
  readonly onClose: () => void
}

export function ExecutionDetail({ item, onClose }: Props) {
  const runId = item.run_id
  const run = useAgentRun(runId)
  const stages = useRunStages(runId)
  const review = useAgentRunReviewSnapshot(runId)
  const reviews = useOperatorReviews(runId)
  const [tab, setTab] = useState<DetailTab>('progress')
  const [logOpen, setLogOpen] = useState(false)
  const [action, setAction] = useState<OperatorReviewDecision | null>(null)

  const stepper = deriveStepper({ status: item.status, currentStage: item.current_stage, hasResult: item.has_result })
  const status = executionStatus(item)
  const snapshot = review.data?.snapshot ?? null

  return (
    <SurfaceCard
      action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />}
      className="activity-detail"
      title="실행 상세"
    >
      <div className="detail-body">
        <div className="detail-title">
          <div className="activity-detail-badges">
            <StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge>
            <StatusBadge tone={executionStatusTone(status)}>{status}</StatusBadge>
          </div>
          <h2>{item.alert_reason ?? '연결 알림 정보 없음'}</h2>
          <p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p>
          <span>{formatDateTime(run.data?.created_at ?? item.created_at)} 시작 · 실행 {runId.slice(0, 8)}…</span>
          <button className="text-link" onClick={() => setLogOpen(true)} type="button">상세 로그 보기 <Icon name="arrow" /></button>
        </div>

        <div className="run-steps activity-steps">
          {USER_STEPS.map((step, index) => {
            const complete = item.status === 'completed' || index < stepper.currentIndex
            const active = item.status !== 'completed' && index === stepper.currentIndex
            const failedHere = stepper.failed && index === stepper.currentIndex
            return (
              <div className={failedHere ? 'failed' : complete ? 'complete' : active ? 'active' : ''} key={step}>
                <b>{complete && !failedHere ? '✓' : index + 1}</b>
                <span>{step}</span>
              </div>
            )
          })}
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {([['progress', '진행 현황'], ['evidence', '판단 근거'], ['reviews', '검토 이력']] as const).map(([key, label]) => (
            <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => setTab(key)} role="tab" type="button">{label}</button>
          ))}
        </div>

        {tab === 'progress' && (
          <section role="tabpanel">
            <ApiState empty={false} error={stages.isError} loading={stages.isLoading} retry={() => void stages.refetch()} />
            {stages.data && stages.data.items.length === 0 && <p className="activity-empty-note">기록 없음 — 이 실행에는 저장된 단계 스냅샷이 없습니다.</p>}
            {stages.data && stages.data.items.length > 0 && (
              <ol className="activity-stage-log">
                {stages.data.items.map((stage: StageProjection) => (
                  <li key={stage.stage_snapshot_id}>
                    <StatusBadge tone={stage.execution_status === 'failed' ? 'critical' : stage.execution_status === 'passed' ? 'success' : 'neutral'}>
                      {stage.execution_status}
                    </StatusBadge>
                    <div>
                      <strong>{STAGE_LABELS[stage.stage_name]}</strong>
                      <small>
                        {formatDateTime(stage.created_at)}
                        {stage.quality_status ? ` · 품질 ${stage.quality_status}${stage.score != null ? ` (${stage.score}점)` : ''}` : ''}
                        {stage.reused_from_snapshot_id ? ' · 이전 스냅샷 재사용' : ''}
                      </small>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {run.data && (
              <div className="run-metrics">
                <span>모드 <strong>{run.data.agent_mode ?? '대기'}</strong></span>
                <span>모델 호출 <strong>{run.data.token_usage?.model_calls ?? 0}회</strong></span>
                <span>토큰 <strong>{run.data.token_usage?.total_tokens.toLocaleString('ko-KR') ?? 0}</strong></span>
                <span>검토 캡처 <strong>{review.data?.status ?? '-'}</strong></span>
              </div>
            )}
            {run.data?.error && <p className="form-error">{run.data.error}</p>}
          </section>
        )}

        {tab === 'evidence' && (
          <section role="tabpanel">
            <ApiState empty={false} error={review.isError} loading={review.isLoading} retry={() => void review.refetch()} />
            {review.data && !snapshot && (
              <p className="activity-empty-note">{review.data.unavailable_reason ?? '판단 근거 스냅샷이 아직 없습니다.'}</p>
            )}
            {snapshot && (
              <div className="activity-evidence-stack">
                <article className="activity-evidence-card highlight">
                  <header><h3>최종 판단</h3>{snapshot.diagnostic.hypotheses[0] && <span className="confidence-chip">신뢰도 {snapshot.diagnostic.hypotheses[0].confidence.toFixed(2)}</span>}</header>
                  <p>{snapshot.result.ops_output?.summary ?? snapshot.handling_reason}</p>
                </article>
                <article className="activity-evidence-card">
                  <h3>실행 사유</h3>
                  <p>{snapshot.handling_reason}</p>
                </article>
                {snapshot.diagnostic.hypotheses.length > 0 ? (
                  <article className="activity-evidence-card">
                    <h3>가설 요약</h3>
                    {snapshot.diagnostic.hypotheses.map((hypothesis) => (
                      <p key={hypothesis.hypothesis_id}><strong>{hypothesis.title}</strong> — {hypothesis.rationale} <em>(신뢰도 {hypothesis.confidence.toFixed(2)})</em></p>
                    ))}
                  </article>
                ) : (
                  <article className="activity-evidence-card"><h3>가설 요약</h3><p>데이터 없음</p></article>
                )}
                <div className="activity-evidence-grid">
                  <article className="activity-evidence-card">
                    <h3>모델 재검증</h3>
                    {snapshot.model_verification ? (
                      <p>
                        <StatusBadge tone={snapshot.model_verification.status === 'verified' ? 'success' : 'warning'}>{snapshot.model_verification.status}</StatusBadge>
                        {' '}{snapshot.model_verification.reason}
                        {snapshot.model_verification.current_score != null && <em> · 점수 {snapshot.model_verification.current_score.toFixed(1)}</em>}
                      </p>
                    ) : <p>데이터 없음</p>}
                  </article>
                  <article className="activity-evidence-card">
                    <h3>날씨 정보</h3>
                    {snapshot.weather ? (
                      <p>
                        {snapshot.weather.temperature_c != null ? `외기 ${snapshot.weather.temperature_c}°C` : '기온 정보 없음'}
                        {snapshot.weather.humidity_percent != null ? ` · 습도 ${snapshot.weather.humidity_percent}%` : ''}
                        {snapshot.weather.precipitation_mm != null ? ` · 강수 ${snapshot.weather.precipitation_mm}mm` : ''}
                        <em> · 출처 {snapshot.weather.provenance.source}</em>
                      </p>
                    ) : <p>데이터 없음</p>}
                  </article>
                </div>
                <article className="activity-evidence-card">
                  <h3>내부 참고 근거</h3>
                  {snapshot.evidence.filter((entry) => entry.document_type === 'internal_rag').length === 0 && <p>데이터 없음</p>}
                  {snapshot.evidence.filter((entry) => entry.document_type === 'internal_rag').map((entry) => (
                    <p key={entry.evidence_id}><strong>{entry.title}</strong> — {entry.excerpt}</p>
                  ))}
                </article>
                <article className="activity-evidence-card">
                  <h3>수기 근거 (운영 노트)</h3>
                  {snapshot.evidence.filter((entry) => entry.document_type === 'operator_manual_evidence').length === 0 && <p>데이터 없음</p>}
                  {snapshot.evidence.filter((entry) => entry.document_type === 'operator_manual_evidence').map((entry) => (
                    <p key={entry.evidence_id}><strong>{entry.title}</strong> — {entry.excerpt}</p>
                  ))}
                </article>
                {snapshot.result.ops_output?.caution && (
                  <article className="activity-evidence-card caution">
                    <h3>한계 및 주의사항</h3>
                    <p>{snapshot.result.ops_output.caution}</p>
                  </article>
                )}
              </div>
            )}
          </section>
        )}

        {tab === 'reviews' && (
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
                      <span>v{record.review_version}</span>
                      <time>{formatDateTime(record.created_at)}</time>
                    </header>
                    <span>{record.reason}</span>
                    {record.correction && <small>교정 요약: {record.correction.corrected_summary ?? '-'}</small>}
                    {record.child_run_id && <small>재실행 연결: {record.child_run_id.slice(0, 8)}…</small>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <div className="detail-actions activity-actions">
          <Button disabled={item.status !== 'completed'} onClick={() => setAction('approve')} tone="primary">✓ 승인</Button>
          <Button disabled={item.status !== 'completed'} onClick={() => setAction('correct')}>교정</Button>
          <Button disabled={item.status !== 'completed'} onClick={() => setAction('keep_human_review')}>사람 검토 유지</Button>
        </div>
      </div>

      {logOpen && (
        <ExecutionLogModal onClose={() => setLogOpen(false)} runId={runId} />
      )}
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

/** 상세 로그 — 저장된 stage 스냅샷/반복 이력/검토 이력을 읽기 전용으로 나열한다. */
function ExecutionLogModal({ runId, onClose }: { readonly runId: string; readonly onClose: () => void }) {
  const stages = useRunStages(runId)
  const iterations = useAgentIterations(runId)
  const reviews = useOperatorReviews(runId)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div aria-label="실행 상세 로그" aria-modal="true" className="invite-modal activity-log-modal" onClick={(event) => event.stopPropagation()} role="dialog">
        <header><h2>상세 로그</h2><Button aria-label="로그 닫기" icon="x" onClick={onClose} /></header>
        <h3>단계 기록</h3>
        {stages.data?.items.length ? (
          <ol className="activity-log">
            {stages.data.items.map((stage) => (
              <li key={stage.stage_snapshot_id}>
                <strong>{STAGE_LABELS[stage.stage_name]}</strong>
                <span>{stage.execution_status}{stage.quality_status ? ` / ${stage.quality_status}` : ''}</span>
                <small>{formatDateTime(stage.created_at)}</small>
              </li>
            ))}
          </ol>
        ) : <p className="activity-empty-note">기록 없음</p>}
        <h3>판단 반복</h3>
        {iterations.data?.length ? (
          <ol className="activity-log">
            {iterations.data.map((iteration) => (
              <li key={iteration.iteration_id}>
                <strong>{iteration.phase}</strong>
                <span>{iteration.decision}</span>
                <small>신뢰도 {(iteration.confidence * 100).toFixed(0)}% · {formatDateTime(iteration.created_at)}</small>
              </li>
            ))}
          </ol>
        ) : <p className="activity-empty-note">기록 없음</p>}
        <h3>검토 이력</h3>
        {reviews.data?.items.length ? (
          <ol className="activity-log">
            {reviews.data.items.map((record) => (
              <li key={record.review_id}>
                <strong>{DECISION_LABELS[record.decision] ?? record.decision}</strong>
                <span>{record.reviewer} · {record.reason}</span>
                <small>{formatDateTime(record.created_at)}</small>
              </li>
            ))}
          </ol>
        ) : <p className="activity-empty-note">기록 없음</p>}
      </div>
    </div>
  )
}
