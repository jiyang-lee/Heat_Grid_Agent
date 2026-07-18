import { type FormEvent, useMemo, useState } from 'react'
import type {
  AgentRunListItem,
  ReviewChatMessageResponse,
  ReviewChatProposalResponse,
} from '../../api/contracts'
import {
  useAgentRun,
  useAgentRunResult,
  useAgentRunReviewSnapshot,
  useArtifacts,
  useArtifactContent,
  useOperatorReviews,
  usePostReviewChatMessage,
  useConfirmReviewChatProposal,
  useCancelReviewChatProposal,
  useReviewChatMessages,
  useReviewChatThreadOpen,
} from '../../api/hooks'
import { ApiState, Button, StatusBadge, SurfaceCard, type Tone } from '../ui'
import { facilityName, formatDateTime, workOrderStatusLabel } from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'

type DetailTab = 'summary' | 'review' | 'artifacts' | 'chat'
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
    queued: '대기', running: '실행 중', completed: '완료', failed: '실패', cancelled: '취소',
  }
  return labels[status] ?? status
}

function priorityLabel(priority: string | null): string {
  const labels: Record<string, string> = { urgent: '심각', high: '경고', normal: '일반' }
  return priority == null ? '-' : (labels[priority] ?? priority)
}

interface Props {
  readonly item: AgentRunListItem
  readonly onClose: () => void
  readonly onOpenWorkOrder: (runId: string) => void
}

interface PayloadProposal {
  proposal_id?: string
}

const PROPOSAL_TONES: Record<string, Tone> = {
  awaiting_confirmation: 'notice', executing: 'warning', executed: 'success', cancelled: 'warning',
  failed: 'critical', stale: 'warning', expired: 'notice', conflict: 'warning',
}

export function ExecutionDetail({ item, onClose, onOpenWorkOrder }: Props) {
  const runId = item.run_id
  const run = useAgentRun(runId)
  const result = useAgentRunResult(item.status === 'completed' ? runId : null)
  const review = useAgentRunReviewSnapshot(runId)
  const reviewHistory = useOperatorReviews(runId)
  const artifacts = useArtifacts(runId)
  const [tab, setTab] = useState<DetailTab>('summary')
  const [action, setAction] = useState<OperatorDecision | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

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

  const reviewVersion = useMemo(() => {
    const items = reviewHistory.data?.items ?? []
    return items.length === 0 ? 0 : Math.max(...items.map((row) => row.review_version))
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
      { runId, created_by: 'ops-manager', idempotency_key: makeId(`thread-${runId}`) },
      {
        onSuccess: (thread) => { setThreadId(thread.thread_id); setStatusMessage('검토 대화가 열렸습니다.') },
        onError: () => setStatusMessage('검토 대화를 열지 못했습니다. 다시 시도해 주세요.'),
      },
    )
  }

  const sendMessage = (event?: FormEvent) => {
    event?.preventDefault()
    if (!threadId || postMessage.isPending || messageText.trim().length === 0) return
    postMessage.mutate(
      {
        threadId,
        body: { content: messageText.trim(), created_by: 'ops-manager', idempotency_key: makeId(`msg-${runId}`) },
      },
      {
        onSuccess: (payload) => {
          if (payload.proposal) setActiveProposal(payload.proposal)
          setMessageText('')
          void chatMessages.refetch()
        },
        onError: () => setStatusMessage('검토 의견을 전송하지 못했습니다.'),
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
        onSuccess: () => {
          setStatusMessage('검토 제안이 승인되었습니다.')
          setActiveProposal(null)
          void reviewHistory.refetch()
          void run.refetch()
        },
        onError: () => setStatusMessage('제안을 승인하지 못했습니다.'),
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
        onSuccess: () => { setStatusMessage('제안이 취소되었습니다.'); setActiveProposal(null); void chatMessages.refetch() },
        onError: () => setStatusMessage('제안을 취소하지 못했습니다.'),
      },
    )
  }

  const actions = result.data?.actions ?? []

  return (
    <SurfaceCard action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />} className="activity-detail" title="조치 계획">
      <div className="detail-body">
        <div className="detail-title">
          <div className="activity-detail-badges">
            <StatusBadge tone={item.priority === 'urgent' ? 'critical' : item.priority === 'high' ? 'warning' : 'primary'}>{priorityLabel(item.priority)}</StatusBadge>
            <StatusBadge tone={stateTone(item.status)}>{runStatusLabel(item.status)}</StatusBadge>
            <StatusBadge tone={item.operator_review_status === 'approved' ? 'success' : item.operator_review_status === 'pending' ? 'notice' : 'warning'}>
              {workOrderStatusLabel(item.operator_review_status)}
            </StatusBadge>
          </div>
          <h2>{facilityName(item.substation_id, item.manufacturer_id)}</h2>
          <p>실행 {runId.slice(0, 8)}… · {formatDateTime(item.created_at)}</p>
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {([['summary', '조치 계획'], ['review', '검토'], ['artifacts', '산출물'], ['chat', '검토 대화']] as const).map(([key, label]) => (
            <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => setTab(key)} role="tab" type="button">{label}</button>
          ))}
        </div>

        {statusMessage && <p className="activity-empty-note">{statusMessage}</p>}

        {tab === 'summary' && (
          <section role="tabpanel">
            <ApiState
              empty={false}
              error={run.isError || result.isError}
              loading={run.isLoading || result.isLoading || review.isLoading}
              retry={() => { void run.refetch(); void result.refetch() }}
            />
            {run.data && (
              <article className="activity-evidence-card highlight work-order-guide">
                <header>
                  <h3>작업지시서 가이드</h3>
                  <span>AI 모델 {run.data.token_usage?.cost_estimate?.model ?? '확인 중'}</span>
                </header>
                <p className="work-order-guide-target"><strong>대상</strong> {facilityName(run.data.substation_id, run.data.manufacturer_id)}</p>
                <div className="activity-plan-split">
                  <section>
                    <h4>판단 근거</h4>
                    <p>{run.data.ops_output?.summary ?? result.data?.situation ?? '분석 결과를 준비 중입니다.'}</p>
                  </section>
                  <section>
                    <h4>AI 권장 조치</h4>
                    <ol>
                      {actions.slice(0, 3).map((entry) => <li key={entry.priority}><strong>{entry.title}</strong><span>{entry.detail}</span></li>)}
                      {actions.length === 0 && <li>권장 조치를 준비 중입니다.</li>}
                    </ol>
                  </section>
                </div>
                <div className="policy-actions activity-guide-actions">
                  <Button disabled={!item.has_result} onClick={() => onOpenWorkOrder(runId)} tone="primary">
                    {item.has_result ? '작업지시서 보기' : '분석 완료 후 확인'}
                  </Button>
                </div>
              </article>
            )}
          </section>
        )}

        {tab === 'review' && (
          <section role="tabpanel">
            <ApiState empty={false} error={reviewHistory.isError} loading={reviewHistory.isLoading} retry={() => void reviewHistory.refetch()} />
            <article className="activity-evidence-card">
              <h3>검토 이력</h3>
              <ul className="review-history">
                {reviewHistory.data?.items.length === 0 && <li>검토 이력이 없습니다.</li>}
                {reviewHistory.data?.items.map((entry) => (
                  <li key={entry.review_id}>
                    <header><StatusBadge tone={decisionTone(entry.decision)}>{entry.decision}</StatusBadge><strong>{entry.reviewer}</strong><time>{formatDateTime(entry.created_at)}</time></header>
                    <span>{entry.reason}</span>
                  </li>
                ))}
              </ul>
            </article>
          </section>
        )}

        {tab === 'artifacts' && (
          <section role="tabpanel">
            <article className="activity-evidence-card">
              <h3>산출물</h3>
              <ApiState empty={false} error={artifacts.isError} loading={artifacts.isLoading} retry={() => void artifacts.refetch()} />
              <div className="table-scroll"><table className="ops-table activity-table"><thead><tr><th>산출물</th><th>유형</th><th>생성 시간</th><th /></tr></thead><tbody>
                {(artifacts.data ?? []).map((entry) => <tr key={entry.artifact_id}><td>{entry.name}</td><td>{entry.kind}</td><td>{formatDateTime(entry.created_at)}</td><td><Button icon="document" onClick={() => setSelectedArtifactId(entry.artifact_id)}>열기</Button></td></tr>)}
                {artifacts.data?.length === 0 && <tr><td colSpan={4}>생성된 산출물이 없습니다.</td></tr>}
              </tbody></table></div>
            </article>
            {artifact && <article className="activity-evidence-card"><h3>{artifact.name}</h3><ApiState empty={!artifactContent.isLoading && !artifactContent.data} error={artifactContent.isError} loading={artifactContent.isLoading} retry={() => void artifactContent.refetch()} />{artifactContent.data != null && <pre className="activity-report-body">{artifactContent.data}</pre>}</article>}
          </section>
        )}

        {tab === 'chat' && (
          <section role="tabpanel">
            <div className="detail-actions"><Button onClick={openChatThread}>검토 대화 열기</Button></div>
            <ApiState empty={false} error={chatMessages.isError} loading={chatMessages.isLoading || reviewThread.isPending} retry={() => void chatMessages.refetch()} />
            <ul className="review-history">
              {messages.map((message: ReviewChatMessageResponse) => <li key={message.message_id}><header><StatusBadge tone={message.role === 'operator' ? 'primary' : message.role === 'assistant' ? 'notice' : 'neutral'}>{message.role}</StatusBadge><strong>{message.message_kind}</strong><time>{formatDateTime(message.created_at)}</time></header><span>{message.content}</span></li>)}
              {messages.length === 0 && <li>대화 내용이 없습니다.</li>}
            </ul>
            {activeProposalView && <article className="activity-evidence-card"><h3>변경 제안</h3><p><strong>상태:</strong> <StatusBadge tone={PROPOSAL_TONES[activeProposalView.status] ?? 'notice'}>{activeProposalView.status}</StatusBadge></p><p><strong>결정:</strong> {activeProposalView.decision}</p><p><strong>사유:</strong> {activeProposalView.reason}</p><div className="policy-actions"><Button disabled={activeProposalView.status !== 'awaiting_confirmation'} onClick={confirmActiveProposal}>승인</Button><Button onClick={cancelActiveProposal} tone="danger">취소</Button></div></article>}
            <form className="review-form" onSubmit={sendMessage}><textarea onChange={(event) => setMessageText(event.target.value)} placeholder="작업지시서 검토 의견을 입력하세요" rows={3} value={messageText} /><div className="policy-actions"><Button disabled={!threadId || postMessage.isPending || messageText.trim().length === 0} onClick={sendMessage} tone="primary">전송</Button></div></form>
          </section>
        )}

        <div className="detail-actions activity-actions activity-actions-sticky">
          <Button onClick={() => setAction('keep_human_review')}>수정 요청</Button>
          <Button onClick={() => setAction('approve')} tone="primary">승인</Button>
          <Button onClick={() => setAction('reject')} tone="danger">반려</Button>
        </div>
      </div>

      {action && <ReviewActionModal currentOutput={run.data?.ops_output ?? null} decision={action} onClose={() => setAction(null)} runId={runId} />}
    </SurfaceCard>
  )
}
