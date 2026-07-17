import { type FormEvent, useEffect, useMemo, useState } from 'react'
import type { ReviewChatMessageResponse, ReviewChatProposalResponse, StageProjection, ToolCallProjection } from '../../api/contracts'
import { ApiError } from '../../api/client'
import {
  useAgentIterations,
  useAgentRun,
  useAgentRunReviewSnapshot,
  useAgentRunResult,
  useArtifacts,
  useArtifactContent,
  useCreateAgentRun,
  useOperatorReviews,
  usePostReviewChatMessage,
  useReplayRunSnapshot,
  useConfirmReviewChatProposal,
  useCancelReviewChatProposal,
  useReviewChatMessages,
  useReviewChatThreadOpen,
  useRunCostBreakdown,
  useRunLineage,
  useRunModelCalls,
  useRunStages,
  useRunToolCalls,
} from '../../api/hooks'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from '../ui'
import {
  facilityName,
  formatDateTime,
  STAGE_LABELS,
  workOrderStatusLabel,
} from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'

type DetailTab = 'summary' | 'review' | 'artifacts' | 'chat' | 'trace' | 'run'

type OperatorDecision = 'approve' | 'reject' | 'correct' | 'keep_human_review'

function makeId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function stateTone(value: string): Tone {
  if (value === 'completed') return 'success'
  if (value === 'failed' || value === 'cancelled') return 'critical'
  if (value === 'running') return 'primary'
  return 'notice'
}

function decisionTone(status: string): Tone {
  if (status === 'approved' || status === 'approve') return 'success'
  if (status === 'rejected' || status === 'reject') return 'critical'
  if (status === 'corrected' || status === 'correct') return 'warning'
  return 'neutral'
}

function runStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: '대기',
    running: '실행 중',
    completed: '완료',
    failed: '실패',
    cancelled: '취소',
  }
  return labels[status] ?? status
}

function priorityLabel(priority: string | null): string {
  const labels: Record<string, string> = { urgent: '심각', high: '경고', normal: '일반' }
  return priority == null ? '-' : (labels[priority] ?? priority)
}

interface Props {
  readonly item: { run_id: string; status: string; priority: string | null; operator_review_status: any; alert_id: string; substation_id: number | null; manufacturer_id: string | null; created_at: string }
  readonly onClose: () => void
}

interface PayloadProposal {
  proposal_id?: string
}

const PROPOSAL_TONES: Record<string, Tone> = {
  awaiting_confirmation: 'notice',
  executing: 'warning',
  executed: 'success',
  cancelled: 'warning',
  failed: 'critical',
  stale: 'warning',
  expired: 'notice',
  conflict: 'warning',
}

export function ExecutionDetail({ item, onClose }: Props) {
  const runId = item.run_id
  const run = useAgentRun(runId)
  const completedRunId = item.status === 'completed' ? runId : null
  const result = useAgentRunResult(completedRunId)
  const review = useAgentRunReviewSnapshot(runId)
  const iterations = useAgentIterations(runId)
  const reviewHistory = useOperatorReviews(runId)
  const stages = useRunStages(runId)
  const lineage = useRunLineage(runId)
  const modelCalls = useRunModelCalls(runId)
  const toolCalls = useRunToolCalls(runId)
  const cost = useRunCostBreakdown(runId)
  const artifacts = useArtifacts(runId)
  const replayProbe = useReplayRunSnapshot(completedRunId)

  const createRun = useCreateAgentRun()

  const [tab, setTab] = useState<DetailTab>('summary')
  const [action, setAction] = useState<OperatorDecision | null>(null)

  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const artifact = artifacts.data?.find((entry) => entry.artifact_id === selectedArtifactId) ?? null
  const artifactContent = useArtifactContent(runId, selectedArtifactId)

  const [threadId, setThreadId] = useState<string | null>(null)
  const [messageText, setMessageText] = useState('')
  const [activeProposal, setActiveProposal] = useState<ReviewChatProposalResponse | null>(null)
  const reviewThread = useReviewChatThreadOpen()
  const chatMessages = useReviewChatMessages(threadId)
  const postMessage = usePostReviewChatMessage()
  const confirmProposal = useConfirmReviewChatProposal()
  const cancelProposal = useCancelReviewChatProposal()

  const [rerunRequestedBy, setRerunRequestedBy] = useState('ops-manager')
  const [rerunReason, setRerunReason] = useState('')
  const [rerunForceNew, setRerunForceNew] = useState(true)
  const [runStatusMessage, setRunStatusMessage] = useState<string | null>(null)

  const reviewVersion = useMemo(() => {
    const items = reviewHistory.data?.items ?? []
    if (items.length === 0) return 0
    return Math.max(...items.map((row) => row.review_version))
  }, [reviewHistory.data])

  const messages = chatMessages.data?.items ?? []
  const latestStructured = messages.at(-1)?.structured_payload as unknown
  const latestProposalFromMessage = useMemo<ReviewChatProposalResponse | null>(() => {
    if (latestStructured == null || typeof latestStructured !== 'object') return null
    const payload = latestStructured as { proposal?: ReviewChatProposalResponse; [key: string]: unknown }
    const candidate = (payload as PayloadProposal).proposal_id != null
      ? (payload as unknown as ReviewChatProposalResponse)
      : payload.proposal
    return candidate?.proposal_id ? candidate : null
  }, [latestStructured])

  const activeProposalView = activeProposal ?? latestProposalFromMessage

  const openChatThread = () => {
    if (threadId != null || reviewThread.isPending) return
    reviewThread.mutate(
      {
        runId,
        created_by: 'ops-manager',
        idempotency_key: makeId(`thread-${runId}`),
      },
      {
        onSuccess: (thread) => {
          setThreadId(thread.thread_id)
          setRunStatusMessage('검토 대화가 열렸습니다.')
        },
        onError: () => setRunStatusMessage('검토 대화를 열지 못했습니다. 다시 시도해 주세요.'),
      },
    )
  }

  const sendMessage = (event?: FormEvent) => {
    event?.preventDefault()
    if (!threadId || postMessage.isPending || messageText.trim().length === 0) return
    postMessage.mutate(
      {
        threadId,
        body: {
          content: messageText.trim(),
          created_by: 'ops-manager',
          idempotency_key: makeId(`msg-${runId}`),
        },
      },
      {
        onSuccess: (payload) => {
          if (payload.proposal) setActiveProposal(payload.proposal)
          setMessageText('')
          void chatMessages.refetch()
        },
        onError: () => setRunStatusMessage('검토 의견을 전송하지 못했습니다.'),
      },
    )
  }

  const confirmActiveProposal = () => {
    if (!activeProposalView || confirmProposal.isPending) return
    confirmProposal.mutate(
      {
        proposalId: activeProposalView.proposal_id,
        body: {
          confirmed_by: 'ops-manager',
          idempotency_key: makeId(`confirm-${activeProposalView.proposal_id}`),
          expected_proposal_status: 'awaiting_confirmation',
          expected_review_version: reviewVersion,
        },
      },
      {
        onSuccess: (payload) => {
          setRunStatusMessage(payload.child_run_id ? `후속 실행이 생성되었습니다: ${payload.child_run_id}` : '제안이 승인되었습니다.')
          setActiveProposal(null)
          void reviewHistory.refetch()
          void run.refetch()
        },
        onError: () => setRunStatusMessage('제안을 승인하지 못했습니다.'),
      },
    )
  }

  const cancelActiveProposal = () => {
    if (!activeProposalView || cancelProposal.isPending) return
    cancelProposal.mutate(
      {
        proposalId: activeProposalView.proposal_id,
        body: { cancelled_by: 'ops-manager', idempotency_key: makeId(`cancel-${activeProposalView.proposal_id}`) },
      },
      {
        onSuccess: () => {
          setRunStatusMessage('제안이 취소되었습니다.')
          setActiveProposal(null)
          void chatMessages.refetch()
        },
        onError: () => setRunStatusMessage('제안을 취소하지 못했습니다.'),
      },
    )
  }

  const createRerun = () => {
    if (createRun.isPending) return
    createRun.mutate(
      {
        alertId: item.alert_id,
        forceNew: rerunForceNew,
        requestedBy: rerunRequestedBy,
        reason: rerunReason.trim() || '운영자 화면에서 재실행',
      },
      {
        onSuccess: (newRun) => {
          setRunStatusMessage(`새 실행이 생성되었습니다: ${newRun.run_id}`)
        },
        onError: () => setRunStatusMessage('재실행을 생성하지 못했습니다.'),
      },
    )
  }

  useEffect(() => {
    if (activeProposalView == null && activeProposal != null) {
      setActiveProposal(null)
    }
  }, [activeProposal, activeProposalView])

  return (
    <SurfaceCard action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />} className="activity-detail" title="실행 상세">
      <div className="detail-body">
        <div className="detail-title">
          <div className="activity-detail-badges">
            <StatusBadge tone={item.priority === 'urgent' ? 'critical' : item.priority === 'high' ? 'warning' : 'primary'}>
              {priorityLabel(item.priority)}
            </StatusBadge>
            <StatusBadge tone={stateTone(item.status)}>{runStatusLabel(item.status)}</StatusBadge>
            <StatusBadge tone={item.operator_review_status === 'approved' ? 'success' : item.operator_review_status === 'pending' ? 'notice' : 'warning'}>
              {workOrderStatusLabel(item.operator_review_status)}
            </StatusBadge>
          </div>
          <h2>{facilityName(item.substation_id, item.manufacturer_id)} / 실행 {runId.slice(0, 8)}...</h2>
          <p>실행 시작: {formatDateTime(item.created_at)}</p>
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {(
            [['summary', '요약'], ['review', '검토'], ['artifacts', '산출물'], ['chat', '검토 대화'], ['trace', '실행 추적'], ['run', '재실행']] as const
          ).map(([key, label]) => (
            <button
              aria-selected={tab === key}
              className={tab === key ? 'active' : ''}
              key={key}
              onClick={() => setTab(key)}
              role="tab"
              type="button"
            >
              {label}
            </button>
          ))}
        </div>

        {runStatusMessage && <p className="activity-empty-note">{runStatusMessage}</p>}

        {tab === 'summary' && (
          <section role="tabpanel">
            <ApiState
              empty={false}
              error={run.isError || result.isError}
              loading={run.isLoading || result.isLoading || review.isLoading}
              retry={() => {
                void run.refetch()
                void result.refetch()
              }}
            />
            {run.data && (
              <>
                <article className="activity-evidence-card">
                  <header>
                    <h3>실행 정보</h3>
                    <span>알림 {run.data.alert_id}</span>
                  </header>
                  <p><strong>상태:</strong> {runStatusLabel(run.data.status)}</p>
                  <p><strong>입력:</strong> {run.data.input_source === 'alert' ? '알림' : run.data.input_source}</p>
                  <p><strong>에이전트 모드:</strong> {run.data.agent_mode ?? '-'}</p>
                  {run.data.error && <p><strong>오류:</strong> {run.data.error}</p>}
                </article>
                <article className="activity-evidence-card">
                  <h3>분석 결과</h3>
                  <p>{run.data.ops_output?.summary ?? result.data?.situation ?? '분석 결과를 준비 중입니다.'}</p>
                </article>
                <article className="activity-evidence-card">
                  <h3>실행 메타데이터</h3>
                  <p><strong>반복:</strong> {run.data.loop_summary?.iterations ?? '-'} / 최대 {run.data.loop_summary?.max_iterations ?? '-'}</p>
                  <p><strong>검토 상태:</strong> {review.data?.status ?? '-'}</p>
                </article>
              </>
            )}
          </section>
        )}

        {tab === 'review' && (
          <section role="tabpanel">
            <ApiState
              empty={false}
              error={reviewHistory.isError}
              loading={reviewHistory.isLoading}
              retry={() => void reviewHistory.refetch()}
            />
            {!review.data && <p className="activity-empty-note">검토 정보를 준비 중입니다.</p>}
            {review.data && (
              <>
                <article className="activity-evidence-card">
                  <h3>검토 개요</h3>
                  <p><strong>결과 상태:</strong> {review.data.snapshot?.result?.status}</p>
                  <p><strong>에이전트 모드:</strong> {review.data.snapshot?.result?.agent_mode ?? '-'}</p>
                  <p><strong>검토 필요:</strong> {review.data.snapshot?.model_verification ? review.data.snapshot.model_verification.status : '정보 없음'}</p>
                </article>
                <article className="activity-evidence-card">
                  <h3>검토 이력</h3>
                  <ul className="review-history">
                    {reviewHistory.data?.items.length === 0 && <li>검토 이력이 없습니다.</li>}
                    {reviewHistory.data?.items.map((entry) => (
                      <li key={entry.review_id}>
                        <header>
                          <StatusBadge tone={decisionTone(entry.decision)}>{entry.decision}</StatusBadge>
                          <strong>{entry.reviewer}</strong>
                          <time>{formatDateTime(entry.created_at)}</time>
                        </header>
                        <span>{entry.reason}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              </>
            )}
            <p className="review-scope-note">검토 작업은 실행 검토 이력에 기록됩니다.</p>
            <div className="detail-actions activity-actions">
              <Button onClick={() => setAction('keep_human_review')}>운영자 검토 유지</Button>
              <Button onClick={() => setAction('reject')} tone="danger">반려</Button>
              <Button onClick={() => setAction('approve')} tone="primary">승인</Button>
            </div>
          </section>
        )}

        {tab === 'artifacts' && (
          <section role="tabpanel">
            <div className="activity-evidence-card">
              <h3>산출물</h3>
              <ApiState empty={false} error={artifacts.isError} loading={artifacts.isLoading} retry={() => void artifacts.refetch()} />
              <div className="table-scroll">
                <table className="ops-table activity-table">
                  <thead>
                    <tr>
                      <th>산출물</th>
                      <th>유형</th>
                      <th>생성 시간</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(artifacts.data ?? []).map((entry) => (
                      <tr key={entry.artifact_id}>
                        <td>{entry.name}</td>
                        <td>{entry.kind}</td>
                        <td>{formatDateTime(entry.created_at)}</td>
                        <td>
                          <Button onClick={() => setSelectedArtifactId(entry.artifact_id)} icon="document">열기</Button>
                        </td>
                      </tr>
                    ))}
                    {artifacts.data?.length === 0 && <tr><td colSpan={4}>생성된 산출물이 없습니다.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            {artifact && (
              <article className="activity-evidence-card">
                <h3>산출물 내용</h3>
                <p><strong>{artifact.name}</strong> ({artifact.artifact_id})</p>
                <ApiState
                  empty={artifactContent.isLoading === false && !artifactContent.data}
                  error={artifactContent.isError}
                  loading={artifactContent.isLoading}
                  retry={() => void artifactContent.refetch()}
                />
                {artifactContent.data != null && <pre className="activity-report-body">{artifactContent.data}</pre>}
              </article>
            )}
          </section>
        )}

        {tab === 'chat' && (
          <section role="tabpanel">
            <div className="detail-actions">
              <Button onClick={openChatThread}>검토 대화 열기</Button>
            </div>
            <ApiState
              empty={false}
              error={chatMessages.isError}
              loading={chatMessages.isLoading || reviewThread.isPending}
              retry={() => void chatMessages.refetch()}
            />

            <ul className="review-history">
              {messages.map((message: ReviewChatMessageResponse) => (
                <li key={message.message_id}>
                  <header>
                    <StatusBadge tone={message.role === 'operator' ? 'primary' : message.role === 'assistant' ? 'notice' : 'neutral'}>
                      {message.role}
                    </StatusBadge>
                    <strong>{message.message_kind}</strong>
                    <time>{formatDateTime(message.created_at)}</time>
                  </header>
                  <span>{message.content}</span>
                </li>
              ))}
              {messages.length === 0 && <li>대화 내용이 없습니다.</li>}
            </ul>

            {activeProposalView && (
              <article className="activity-evidence-card">
                <h3>변경 제안</h3>
                <p><strong>상태:</strong> <StatusBadge tone={PROPOSAL_TONES[activeProposalView.status] ?? 'notice'}>{activeProposalView.status}</StatusBadge></p>
                <p><strong>결정:</strong> {activeProposalView.decision}</p>
                <p><strong>사유:</strong> {activeProposalView.reason}</p>
                <p><strong>대상 단계:</strong> {activeProposalView.target_stage ?? '-'}</p>
                <div className="policy-actions">
                  <Button
                    disabled={activeProposalView.status !== 'awaiting_confirmation'}
                    onClick={confirmActiveProposal}
                  >
                    승인
                  </Button>
                  <Button tone="danger" onClick={cancelActiveProposal}>취소</Button>
                </div>
              </article>
            )}

            <form className="review-form" onSubmit={sendMessage}>
              <textarea
                rows={3}
                value={messageText}
                onChange={(event) => setMessageText(event.target.value)}
                placeholder="작업지시서 검토 의견을 입력하세요"
              />
              <div className="policy-actions">
                <Button onClick={sendMessage} disabled={!threadId || postMessage.isPending || messageText.trim().length === 0} tone="primary">
                  전송
                </Button>
              </div>
            </form>
          </section>
        )}

        {tab === 'trace' && (
          <section role="tabpanel">
            <div className="activity-evidence-card">
              <h3>실행 추적</h3>
              <ApiState
                empty={false}
                error={stages.isError}
                loading={stages.isLoading || lineage.isLoading || modelCalls.isLoading || toolCalls.isLoading || cost.isLoading}
                retry={() => {
                  void stages.refetch()
                  void lineage.refetch()
                  void modelCalls.refetch()
                  void toolCalls.refetch()
                  void cost.refetch()
                }}
              />
              {stages.data?.items.length === 0 && <p className="activity-empty-note">단계 정보가 없습니다.</p>}
              {(stages.data?.items ?? []).map((entry: StageProjection) => (
                <article className="activity-evidence-card" key={entry.stage_snapshot_id}>
                  <h3>{STAGE_LABELS[entry.stage_name] ?? entry.stage_name}</h3>
                  <p><StatusBadge tone={stateTone(entry.execution_status)}>{runStatusLabel(entry.execution_status)}</StatusBadge> 시도 {entry.attempt}</p>
                  <p><strong>점수:</strong> {entry.score ?? '-'} / 기준 {entry.threshold ?? '-'}</p>
                  <p><strong>품질:</strong> {entry.quality_status ?? '-'}</p>
                  <p><strong>근거:</strong> {entry.reasons.join(', ') || '-'}</p>
                  <p><strong>재시도 소진:</strong> {String(entry.retry_exhausted)} / 강제 검토: {String(entry.force_review)}</p>
                </article>
              ))}
              <article className="activity-evidence-card">
                <h3>실행 계보</h3>
                {lineage.data ? (
                  <>
                    <p><strong>최초 실행:</strong> {lineage.data.root_run_id}</p>
                    <p><strong>현재 실행:</strong> {lineage.data.current_run_id}</p>
                    <p><strong>깊이:</strong> {lineage.data.depth}</p>
                    <p><strong>후속 실행:</strong> {lineage.data.children.length}</p>
                  </>
                ) : <p className="activity-empty-note">실행 계보를 준비 중입니다.</p>}
              </article>
              <article className="activity-evidence-card">
                <h3>호출 내역</h3>
                {cost.data && (
                  <p><strong>토큰:</strong> {cost.data.total_tokens}</p>
                )}
                <p><strong>모델 호출:</strong> {modelCalls.data?.length ?? 0}</p>
                <p><strong>도구 호출:</strong> {toolCalls.data?.length ?? 0}</p>
                {(toolCalls.data ?? []).slice(0, 6).map((entry: ToolCallProjection) => (
                  <p key={entry.tool_call_id}>
                    <strong>{entry.tool_name}</strong> / {entry.stage_name} ({entry.status})
                  </p>
                ))}
              </article>
            </div>
          </section>
        )}

        {tab === 'run' && (
          <section role="tabpanel">
            <article className="activity-evidence-card">
              <h3>재실행 설정</h3>
              <div className="review-form">
                <label>
                  요청자
                  <input onChange={(event) => setRerunRequestedBy(event.target.value)} value={rerunRequestedBy} />
                </label>
                <label>
                  재실행 사유
                  <input onChange={(event) => setRerunReason(event.target.value)} value={rerunReason} />
                </label>
                <label>
                  새 실행 강제 생성
                  <select onChange={(event) => setRerunForceNew(event.target.value === 'true')} value={rerunForceNew ? 'true' : 'false'}>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                </label>
                <Button onClick={createRerun} tone="primary">재실행 생성</Button>
              </div>
              {createRun.isError && <p className="form-error">재실행을 생성하지 못했습니다.</p>}
            </article>

            <article className="activity-evidence-card">
              <h3>실행 이력</h3>
              <p><strong>반복 횟수:</strong> {iterations.data?.length ?? '-'}</p>
              <p><strong>검토 상태:</strong> {review.data?.status ?? '-'}</p>
              <p><strong>실행 종료:</strong> {item.status === 'completed' || item.status === 'failed' ? '예' : '아니요'}</p>
            </article>

            <article className="activity-evidence-card">
              <h3>재생 실행 조회</h3>
              <p>재생 기능이 활성화되어 있으면 이 실행과 연결된 재생 실행을 확인할 수 있습니다.</p>
              <ApiState
                empty={false}
                error={replayProbe.isError}
                loading={replayProbe.isLoading}
                retry={() => void replayProbe.refetch()}
              />
              {replayProbe.isError && replayProbe.error instanceof ApiError && replayProbe.error.status === 404 && (
                <p className="activity-empty-note">현재 실행과 연결된 재생 정보가 없습니다.</p>
              )}
            </article>
          </section>
        )}
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
