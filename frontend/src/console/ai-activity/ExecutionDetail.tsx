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
  const result = useAgentRunResult(runId)
  const review = useAgentRunReviewSnapshot(runId)
  const iterations = useAgentIterations(runId)
  const reviewHistory = useOperatorReviews(runId)
  const stages = useRunStages(runId)
  const lineage = useRunLineage(runId)
  const modelCalls = useRunModelCalls(runId)
  const toolCalls = useRunToolCalls(runId)
  const cost = useRunCostBreakdown(runId)
  const artifacts = useArtifacts(runId)
  const replayProbe = useReplayRunSnapshot(runId)

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
          setRunStatusMessage('Review chat opened.')
        },
        onError: () => setRunStatusMessage('Failed to open review chat. Try again.'),
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
        onError: () => setRunStatusMessage('Failed to send review chat message.'),
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
          setRunStatusMessage(payload.child_run_id ? `Child run created: ${payload.child_run_id}` : 'Proposal confirmed.')
          setActiveProposal(null)
          void reviewHistory.refetch()
          void run.refetch()
        },
        onError: () => setRunStatusMessage('Failed to confirm proposal.'),
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
          setRunStatusMessage('Proposal cancelled.')
          setActiveProposal(null)
          void chatMessages.refetch()
        },
        onError: () => setRunStatusMessage('Failed to cancel proposal.'),
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
        reason: rerunReason.trim() || 'manual rerun from UI',
      },
      {
        onSuccess: (newRun) => {
          setRunStatusMessage(`New run created: ${newRun.run_id}`)
        },
        onError: () => setRunStatusMessage('Failed to create rerun.'),
      },
    )
  }

  useEffect(() => {
    if (activeProposalView == null && activeProposal != null) {
      setActiveProposal(null)
    }
  }, [activeProposal, activeProposalView])

  return (
    <SurfaceCard action={<Button aria-label="Close" icon="x" onClick={onClose} />} className="activity-detail" title="Execution detail">
      <div className="detail-body">
        <div className="detail-title">
          <div className="activity-detail-badges">
            <StatusBadge tone={item.priority === 'urgent' ? 'critical' : item.priority === 'high' ? 'warning' : 'primary'}>
              {item.priority ?? '-'}
            </StatusBadge>
            <StatusBadge tone={stateTone(item.status)}>{item.status}</StatusBadge>
            <StatusBadge tone={item.operator_review_status === 'approved' ? 'success' : item.operator_review_status === 'pending' ? 'notice' : 'warning'}>
              {workOrderStatusLabel(item.operator_review_status)}
            </StatusBadge>
          </div>
          <h2>{facilityName(item.substation_id, item.manufacturer_id)} / run {runId.slice(0, 8)}...</h2>
          <p>Run created: {formatDateTime(item.created_at)}</p>
        </div>

        <div className="activity-tabs activity-inner-tabs" role="tablist">
          {(
            [['summary', 'Summary'], ['review', 'Review'], ['artifacts', 'Artifacts'], ['chat', 'Review Chat'], ['trace', 'Trace'], ['run', 'Run']] as const
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
                    <h3>Run snapshot</h3>
                    <span>Alert {run.data.alert_id}</span>
                  </header>
                  <p><strong>Status:</strong> {run.data.status}</p>
                  <p><strong>Input:</strong> {run.data.input_source}</p>
                  <p><strong>Agent mode:</strong> {run.data.agent_mode ?? '-'}</p>
                  {run.data.error && <p><strong>Error:</strong> {run.data.error}</p>}
                </article>
                <article className="activity-evidence-card">
                  <h3>Result</h3>
                  <p>{run.data.ops_output?.summary ?? result.data?.situation ?? 'No result payload yet.'}</p>
                </article>
                <article className="activity-evidence-card">
                  <h3>Run metadata</h3>
                  <p><strong>Loop:</strong> {run.data.loop_summary?.iterations ?? '-'} / max {run.data.loop_summary?.max_iterations ?? '-'}</p>
                  <p><strong>Review status:</strong> {review.data?.status ?? '-'}</p>
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
            {!review.data && <p className="activity-empty-note">Review snapshot is not available yet.</p>}
            {review.data && (
              <>
                <article className="activity-evidence-card">
                  <h3>Review overview</h3>
                  <p><strong>Result status:</strong> {review.data.result?.status}</p>
                  <p><strong>Agent mode:</strong> {review.data.result?.agent_mode ?? '-'}</p>
                  <p><strong>Review required:</strong> {review.data.snapshot?.model_verification ? review.data.snapshot.model_verification.status : 'no snapshot'}</p>
                </article>
                <article className="activity-evidence-card">
                  <h3>Review history</h3>
                  <ul className="review-history">
                    {reviewHistory.data?.items.length === 0 && <li>No review history.</li>}
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
            <p className="review-scope-note">Review operations are recorded to the run review timeline.</p>
            <div className="detail-actions activity-actions">
              <Button onClick={() => setAction('keep_human_review')}>Keep Human Review</Button>
              <Button onClick={() => setAction('reject')} tone="danger">Reject</Button>
              <Button onClick={() => setAction('approve')} tone="primary">Approve</Button>
            </div>
          </section>
        )}

        {tab === 'artifacts' && (
          <section role="tabpanel">
            <div className="activity-evidence-card">
              <h3>Artifacts</h3>
              <ApiState empty={false} error={artifacts.isError} loading={artifacts.isLoading} retry={() => void artifacts.refetch()} />
              <div className="table-scroll">
                <table className="ops-table activity-table">
                  <thead>
                    <tr>
                      <th>Artifact</th>
                      <th>Kind</th>
                      <th>Created</th>
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
                          <Button onClick={() => setSelectedArtifactId(entry.artifact_id)} icon="document">Open</Button>
                        </td>
                      </tr>
                    ))}
                    {artifacts.data?.length === 0 && <tr><td colSpan={4}>No artifacts.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            {artifact && (
              <article className="activity-evidence-card">
                <h3>Artifact content</h3>
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
              <Button onClick={openChatThread}>Open Review Chat</Button>
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
              {messages.length === 0 && <li>No messages.</li>}
            </ul>

            {activeProposalView && (
              <article className="activity-evidence-card">
                <h3>Proposal</h3>
                <p><strong>Status:</strong> <StatusBadge tone={PROPOSAL_TONES[activeProposalView.status] ?? 'notice'}>{activeProposalView.status}</StatusBadge></p>
                <p><strong>Decision:</strong> {activeProposalView.decision}</p>
                <p><strong>Reason:</strong> {activeProposalView.reason}</p>
                <p><strong>Target stage:</strong> {activeProposalView.target_stage ?? '-'}</p>
                <div className="policy-actions">
                  <Button
                    disabled={activeProposalView.status !== 'awaiting_confirmation'}
                    onClick={confirmActiveProposal}
                  >
                    Confirm
                  </Button>
                  <Button tone="danger" onClick={cancelActiveProposal}>Cancel</Button>
                </div>
              </article>
            )}

            <form className="review-form" onSubmit={sendMessage}>
              <textarea
                rows={3}
                value={messageText}
                onChange={(event) => setMessageText(event.target.value)}
                placeholder="Send operator message in review chat"
              />
              <div className="policy-actions">
                <Button onClick={sendMessage} disabled={!threadId || postMessage.isPending || messageText.trim().length === 0} tone="primary">
                  Send
                </Button>
              </div>
            </form>
          </section>
        )}

        {tab === 'trace' && (
          <section role="tabpanel">
            <div className="activity-evidence-card">
              <h3>Execution trace</h3>
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
              {stages.data?.items.length === 0 && <p className="activity-empty-note">No stage data.</p>}
              {(stages.data?.items ?? []).map((entry: StageProjection) => (
                <article className="activity-evidence-card" key={entry.stage_snapshot_id}>
                  <h3>{STAGE_LABELS[entry.stage_name] ?? entry.stage_name}</h3>
                  <p><StatusBadge tone={stateTone(entry.execution_status)}>{entry.execution_status}</StatusBadge> attempt {entry.attempt}</p>
                  <p><strong>Score:</strong> {entry.score ?? '-'} / threshold {entry.threshold ?? '-'}</p>
                  <p><strong>Quality:</strong> {entry.quality_status ?? '-'}</p>
                  <p><strong>Reasons:</strong> {entry.reasons.join(', ') || '-'}</p>
                  <p><strong>Retries:</strong> {String(entry.retry_exhausted)} / force_review: {String(entry.force_review)}</p>
                </article>
              ))}
              <article className="activity-evidence-card">
                <h3>Lineage</h3>
                {lineage.data ? (
                  <>
                    <p><strong>Root run:</strong> {lineage.data.root_run_id}</p>
                    <p><strong>Current run:</strong> {lineage.data.current_run_id}</p>
                    <p><strong>Depth:</strong> {lineage.data.depth}</p>
                    <p><strong>Children:</strong> {lineage.data.children.length}</p>
                  </>
                ) : <p className="activity-empty-note">Lineage not ready.</p>}
              </article>
              <article className="activity-evidence-card">
                <h3>Calls</h3>
                {cost.data && (
                  <p><strong>Tokens:</strong> {cost.data.total_tokens}</p>
                )}
                <p><strong>Model calls:</strong> {modelCalls.data?.length ?? 0}</p>
                <p><strong>Tool calls:</strong> {toolCalls.data?.length ?? 0}</p>
                {(toolCalls.data ?? []).slice(0, 6).map((entry: ToolCallProjection) => (
                  <p key={entry.tool_call_id}>
                    <strong>{entry.tool_name}</strong> in {entry.stage_name} ({entry.status})
                  </p>
                ))}
              </article>
            </div>
          </section>
        )}

        {tab === 'run' && (
          <section role="tabpanel">
            <article className="activity-evidence-card">
              <h3>Run controls</h3>
              <div className="review-form">
                <label>
                  Requested by
                  <input onChange={(event) => setRerunRequestedBy(event.target.value)} value={rerunRequestedBy} />
                </label>
                <label>
                  Reason
                  <input onChange={(event) => setRerunReason(event.target.value)} value={rerunReason} />
                </label>
                <label>
                  Force new run
                  <select onChange={(event) => setRerunForceNew(event.target.value === 'true')} value={rerunForceNew ? 'true' : 'false'}>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                </label>
                <Button onClick={createRerun} tone="primary">Create Rerun</Button>
              </div>
              {createRun.isError && <p className="form-error">Failed to create rerun.</p>}
            </article>

            <article className="activity-evidence-card">
              <h3>Execution history</h3>
              <p><strong>Iteration count:</strong> {iterations.data?.length ?? '-'}</p>
              <p><strong>Review snapshot status:</strong> {review.data?.status ?? '-'}</p>
              <p><strong>Run completed:</strong> {item.status === 'completed' || item.status === 'failed' ? 'yes' : 'no'}</p>
            </article>

            <article className="activity-evidence-card">
              <h3>Replay lookup</h3>
              <p>If replay feature is enabled, you can open a related replay run from this run.</p>
              <ApiState
                empty={false}
                error={replayProbe.isError}
                loading={replayProbe.isLoading}
                retry={() => void replayProbe.refetch()}
              />
              {replayProbe.isError && replayProbe.error instanceof ApiError && replayProbe.error.status === 404 && (
                <p className="activity-empty-note">No replay snapshot by current run_id.</p>
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
