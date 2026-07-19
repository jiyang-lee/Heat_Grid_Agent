import { useState } from 'react'
import type { OperatorReviewDecision, OpsAgentOutput, ReviewChatMessageResponse, ReviewChatProposalResponse, WorkOrderListItem } from '../../api/contracts'
import { ApiError } from '../../api/client'
import { useCancelReviewChatProposal, useConfirmReviewChatProposal, usePostReviewChatMessage, useReviewChatMessages, useReviewChatThreadOpen, useAgentRunResult } from '../../api/hooks'
import { downloadDocumentPdf } from '../../scenario/documentPdf'
import { ApiState, Button, StatusBadge, SurfaceCard } from '../ui'
import { facilityName, formatDateTime, priorityLabel, priorityTone, reviewStatusTone, workOrderStatusLabel } from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'

interface Props {
  readonly item: WorkOrderListItem
  readonly onClose: () => void
  readonly onOpenDetail?: () => void
  readonly mode?: 'preview' | 'detail'
}

function compactDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'unknown'
  return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function chatErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return '다른 검토 변경과 충돌했습니다. 문서를 새로 고친 뒤 다시 시도해 주세요.'
  if (error instanceof ApiError && error.status === 422) return '수정 요청 내용을 확인한 뒤 다시 보내 주세요.'
  return 'AI 검토 요청을 처리하지 못했습니다. 입력 내용은 유지됩니다.'
}

function chatText(content: string): string {
  return content.replace(/\*\*|__|`/g, '').replace(/^\s{0,3}#{1,6}\s+/gm, '').trim()
}

export function WorkOrderDetail({ item, mode = 'detail', onClose, onOpenDetail }: Props) {
  const result = useAgentRunResult(item.run_id)
  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [reviewDecision, setReviewDecision] = useState<OperatorReviewDecision | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [chatError, setChatError] = useState<string | null>(null)
  const [proposal, setProposal] = useState<ReviewChatProposalResponse | null>(null)
  const [localMessages, setLocalMessages] = useState<readonly ReviewChatMessageResponse[]>([])
  const reviewThread = useReviewChatThreadOpen()
  const postMessage = usePostReviewChatMessage()
  const confirmProposal = useConfirmReviewChatProposal()
  const cancelProposal = useCancelReviewChatProposal()
  const reviewMessages = useReviewChatMessages(threadId)
  const title = item.alert_reason ?? `${facilityName(item.substation_id, item.manufacturer_id)} 이상 대응 작업지시서`
  const number = `HG-${compactDate(item.created_at)}-${item.substation_id ?? 'NA'}-v1`
  const body = result.data == null ? '' : ['1. 작업 목적', `${title} 대응을 위한 현장 점검과 안전 조치를 수행합니다.`, '', '2. 작업 절차', ...result.data.actions.map((action, index) => `${index + 1}. ${action.title}\n${action.detail}`), '', '3. 안전 확인', ...result.data.cautions.map((caution) => `- ${caution}`)].join('\n')
  const reviewOutput: OpsAgentOutput | null = result.data == null ? null : { summary: result.data.situation, action_plan: result.data.actions.map((action) => `${action.title}: ${action.detail}`).join('\n'), caution: result.data.cautions.join('\n') }
  const messages = reviewMessages.data?.items.length ? reviewMessages.data.items : localMessages

  const download = async () => {
    if (!body) return
    setDownloadState('working')
    try {
      await downloadDocumentPdf({ title: '작업지시서 v1', fileName: `heatgrid-work-order-${number}-v1.pdf`, metadata: [`문서번호 ${number}`, `대상 설비 ${facilityName(item.substation_id, item.manufacturer_id)}`, `생성 ${formatDateTime(item.created_at)}`], content: body })
      setDownloadState('idle')
    } catch (error: unknown) {
      setDownloadState('error')
      setChatError(chatErrorMessage(error))
    }
  }

  const sendMessage = async () => {
    const content = draft.trim()
    if (!content || postMessage.isPending || proposal != null) return
    setChatError(null)
    try {
      let activeThreadId = threadId
      if (activeThreadId == null) {
        const thread = await reviewThread.mutateAsync({ runId: item.run_id, created_by: 'ops-manager', idempotency_key: requestId(`thread-${item.run_id}`) })
        activeThreadId = thread.thread_id
        setThreadId(activeThreadId)
      }
      const response = await postMessage.mutateAsync({ threadId: activeThreadId, body: { content, created_by: 'ops-manager', idempotency_key: requestId(`message-${item.run_id}`) } })
      setLocalMessages((current) => [...current, response.operator_message, response.assistant_message])
      setProposal(response.proposal)
      setDraft('')
      void reviewMessages.refetch()
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const confirm = async () => {
    if (proposal == null) return
    setChatError(null)
    try {
      const confirmation = await confirmProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { confirmed_by: 'ops-manager', idempotency_key: requestId(`confirm-${proposal.proposal_id}`), expected_proposal_status: 'awaiting_confirmation', expected_review_version: proposal.expected_review_version } })
      setProposal(null)
      setLocalMessages((current) => [...current, { message_id: `confirmation-${Date.now()}`, thread_id: proposal.thread_id, sequence: current.length + 1, role: 'system_event', message_kind: 'execution_result', content: confirmation.child_run_id == null ? '검토 의견을 저장했습니다.' : 'AI가 수정 작업을 시작했습니다. 분석 목록에서 상태를 확인하세요.', structured_payload: {}, citations: [], context_hash: proposal.context_hash, created_at: new Date().toISOString() }])
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const cancel = async () => {
    if (proposal == null) return
    setChatError(null)
    try {
      await cancelProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { cancelled_by: 'ops-manager', idempotency_key: requestId(`cancel-${proposal.proposal_id}`) } })
      setProposal(null)
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const preview = mode === 'preview'
  return <SurfaceCard action={<Button aria-label={preview ? '미리보기 닫기' : '상세 닫기'} icon="x" onClick={onClose} />} className="activity-detail" title={preview ? '작업지시서 미리보기' : '작업지시서 상세'}>
    <div className="detail-body">
      <div className="detail-title"><StatusBadge tone={reviewStatusTone(item.operator_review_status)}>{workOrderStatusLabel(item.operator_review_status)}</StatusBadge><h2>{title}</h2><p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p><span>생성 {formatDateTime(item.created_at)}</span></div>
      <ApiState empty={false} error={result.isError && !resultNotReady} loading={result.isLoading} retry={() => void result.refetch()} />
      {resultNotReady && <p className="activity-empty-note">실행이 완료되면 작업지시서 본문을 준비합니다.</p>}
      {preview && result.data && <section className="work-order-preview"><h3>조치 요약</h3><ol>{result.data.actions.slice(0, 3).map((action) => <li key={action.title}><strong>{action.title}</strong><span>{action.detail}</span></li>)}</ol><Button icon="arrow" onClick={onOpenDetail} tone="primary">상세 보기</Button></section>}
      {!preview && result.data && <><article className="work-order-document"><header><div><small>현장 작업지시서</small><h3>{title}</h3></div><StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge></header><dl><div><dt>문서번호</dt><dd>{number}</dd></div><div><dt>대상 설비</dt><dd>{facilityName(item.substation_id, item.manufacturer_id)}</dd></div><div><dt>생성 시각</dt><dd>{formatDateTime(item.created_at)}</dd></div><div><dt>문서 버전</dt><dd>v1</dd></div></dl><pre className="activity-report-body report-single-body">{body}</pre></article><section className="work-order-review-chat" aria-label="AI 수정 챗봇"><header><div><h3>AI 수정 챗봇</h3><p>수정할 작업 절차, 안전 기준 또는 표현을 요청하고 제안은 직접 승인하세요.</p></div></header><div className="work-order-chat-log" aria-live="polite">{messages.length === 0 ? <p>AI 검토 대화가 아직 없습니다.</p> : messages.map((message) => <p className={message.role} key={message.message_id}><strong>{message.role === 'operator' ? '운영자' : message.role === 'assistant' ? 'AI' : '시스템'}</strong>{chatText(message.content)}</p>)}</div>{proposal && <div className="work-order-chat-proposal"><strong>AI 제안: {proposal.reason}</strong><span>승인하면 필요한 수정 작업을 시작합니다.</span><div><Button disabled={confirmProposal.isPending} onClick={() => void cancel()}>제안 취소</Button><Button disabled={confirmProposal.isPending} icon="check" onClick={() => void confirm()} tone="primary">수정 실행 승인</Button></div></div>}<label className="work-order-chat-compose"><span>수정 요청</span><textarea disabled={postMessage.isPending || proposal != null} onChange={(event) => setDraft(event.target.value)} placeholder="예: 밸브 차단 전 현장 확인 절차를 추가해 주세요." value={draft} /><Button disabled={!draft.trim() || postMessage.isPending || proposal != null} onClick={() => void sendMessage()} tone="primary">{postMessage.isPending ? 'AI 검토 중' : 'AI에게 요청'}</Button></label>{chatError && <p className="form-error" role="alert">{chatError}</p>}</section></>}
      {downloadState === 'error' && <p className="scenario-document-error" role="alert">PDF를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.</p>}
      {!preview && <div className="detail-actions activity-guide-actions"><Button disabled={!body || downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'PDF 생성 중' : 'PDF 다운로드'}</Button>{result.data && <><Button onClick={() => setReviewDecision('correct')}>수정</Button><Button icon="check" onClick={() => setReviewDecision('approve')} tone="primary">승인</Button></>}</div>}
    </div>
    {reviewDecision && <ReviewActionModal currentOutput={reviewOutput} decision={reviewDecision} onClose={() => setReviewDecision(null)} runId={item.run_id} />}
  </SurfaceCard>
}
