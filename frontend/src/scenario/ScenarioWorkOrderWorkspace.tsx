import { useEffect, useState, type KeyboardEvent } from 'react'
import type { ReviewChatProposalResponse } from '../api/contracts'
import { ApiError } from '../api/client'
import { useCancelReviewChatProposal, useConfirmReviewChatProposal, usePostReviewChatMessage, useReviewChatThreadOpen } from '../api/hooks'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { downloadDocumentPdf } from './documentPdf'
import type { ScenarioAlert, ScenarioState } from './types'
import { ScenarioVersionRail } from './ScenarioVersionRail'

interface Props {
  readonly alert: ScenarioAlert
  readonly runId: string | null
  readonly state: ScenarioState
  readonly onAccept: (version: 1 | 2 | 3) => void
  readonly onCreateReport: () => void
  readonly onAppendMessages: (messages: ScenarioState['messages']) => void
  readonly onAppendRevision: (runId: string, result: import('../api/contracts').OpsAgentResultV4, instruction: string) => void
  readonly onSelectVersion: (version: 1 | 2 | 3) => void
  readonly onUpdateContent: (version: 1 | 2 | 3, content: string) => void
}

function documentNumber(alert: ScenarioAlert, version: 1 | 2 | 3): string {
  const date = new Date(alert.detectedAt)
  const compactDate = Number.isNaN(date.getTime())
    ? '20200113'
    : `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`
  return `HG-${compactDate}-${alert.substationId}-v${version}`
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return '다른 검토 변경과 충돌했습니다. 문서 편집 내용은 유지되며 다시 시도할 수 있습니다.'
  return 'AI 검토 요청을 처리하지 못했습니다. 입력 내용은 유지됩니다.'
}

function chatText(content: string): string {
  return content.replace(/\*\*|__|`/g, '').replace(/^\s{0,3}#{1,6}\s+/gm, '').trim()
}

function proposalTargetLabel(proposal: ReviewChatProposalResponse): string {
  if (proposal.revision?.target_area === 'risk_evidence') return '위험성 및 근거'
  if (proposal.reason_category === 'ml_prediction_issue') return '모델 재검증'
  if (proposal.reason_category === 'weather_context_issue') return '외부 데이터'
  if (proposal.reason_category === 'rag_retrieval_issue') return '참고 문서'
  return '작업지시서 본문'
}

export function ScenarioWorkOrderWorkspace({ alert, runId, state, onAccept, onAppendMessages, onAppendRevision, onCreateReport, onSelectVersion, onUpdateContent }: Props) {
  const latestOrder = state.workOrders.at(-1)
  const selectedOrder = state.workOrders.find((order) => order.version === state.selectedWorkOrderVersion) ?? latestOrder
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(selectedOrder?.content ?? '')
  const [rerunning, setRerunning] = useState(false)
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [apiProposal, setApiProposal] = useState<ReviewChatProposalResponse | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const reviewThread = useReviewChatThreadOpen()
  const postMessage = usePostReviewChatMessage()
  const confirmProposal = useConfirmReviewChatProposal()
  const cancelProposal = useCancelReviewChatProposal()

  useEffect(() => {
    setDraft(selectedOrder?.content ?? '')
    setEditing(false)
  }, [selectedOrder?.content, selectedOrder?.version])

  if (!latestOrder || !selectedOrder) {
    return <SurfaceCard title="작업지시서"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 대기</StatusBadge><p>계획서에서 작업지시서를 먼저 생성하세요.</p></div></SurfaceCard>
  }

  const rerunsRemaining = Math.max(0, 2 - state.workOrderRerunCount)
  const chatbotLocked = rerunsRemaining === 0
  const number = documentNumber(alert, selectedOrder.version)
  const adopted = state.acceptedWorkOrderVersion === selectedOrder.version

  const sendMessage = async () => {
    if (!message.trim() || chatbotLocked || rerunning || apiProposal != null) return
    setApiError(null)
    if (runId == null) {
      setApiError('이전 세션에서 만든 작업지시서라 AI 재생성에 연결되지 않았습니다. 상단 새로고침 후 계획서에서 작업지시서를 다시 생성해 주세요.')
      return
    }
    try {
      let assistantContent = '수정 제안을 준비하지 못했습니다.'
      let activeThreadId = threadId
      if (activeThreadId == null) {
        const thread = await reviewThread.mutateAsync({ runId, created_by: 'ops-manager', idempotency_key: requestId(`thread-${runId}`) })
        activeThreadId = thread.thread_id
        setThreadId(activeThreadId)
      }
      const response = await postMessage.mutateAsync({ threadId: activeThreadId, body: { content: message.trim(), created_by: 'ops-manager', idempotency_key: requestId(`message-${runId}`) } })
      setApiProposal(response.proposal)
      assistantContent = chatText(response.assistant_message.content)
      const createdAt = new Date().toISOString()
      onAppendMessages([
        { id: `operator-${Date.now()}`, role: 'operator', content: message.trim(), createdAt, workOrderVersion: latestOrder.version },
        { id: `assistant-${Date.now()}`, role: 'assistant', content: assistantContent, createdAt, workOrderVersion: latestOrder.version },
      ])
      setMessage('')
    } catch (error: unknown) {
      setApiError(apiErrorMessage(error))
    }
  }
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }
  const discardProposal = async () => {
    const proposal = apiProposal
    if (proposal == null) return
    setApiProposal(null)
    try {
      await cancelProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { cancelled_by: 'ops-manager', idempotency_key: requestId(`cancel-${proposal.proposal_id}`) } })
    } catch (error: unknown) {
      setApiError(apiErrorMessage(error))
    }
  }
  const saveEdit = () => {
    onUpdateContent(selectedOrder.version, draft)
    setEditing(false)
    void discardProposal()
  }
  const adoptVersion = () => {
    if (!window.confirm(`작업지시서 v${selectedOrder.version}을 최종 채택할까요?\n보고서는 이 버전을 기준으로 생성됩니다.`)) return
    onAccept(selectedOrder.version)
  }
  const createNextVersion = async () => {
    if (rerunning) return
    setRerunning(true)
    setApiError(null)
    try {
      if (apiProposal == null) return
      const confirmation = await confirmProposal.mutateAsync({ proposalId: apiProposal.proposal_id, body: { confirmed_by: 'ops-manager', idempotency_key: requestId(`confirm-${apiProposal.proposal_id}`), expected_proposal_status: 'awaiting_confirmation', expected_review_version: apiProposal.expected_review_version } })
      if (confirmation.child_run_id == null) throw new Error('자식 실행이 생성되지 않았습니다.')
      const waitForResult = async () => {
        const { agentRunsApi } = await import('../api/backend')
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const status = await agentRunsApi.get(confirmation.child_run_id as string)
          if (status.status === 'completed') return agentRunsApi.result(confirmation.child_run_id as string)
          if (status.status === 'failed') throw new Error(status.error ?? 'AI 재실행에 실패했습니다.')
          await new Promise<void>((resolve) => window.setTimeout(resolve, 1_000))
        }
        throw new Error('AI 재실행 시간이 초과되었습니다.')
      }
      const result = await waitForResult()
      onAppendRevision(confirmation.child_run_id, result, apiProposal.reason)
      onAppendMessages([{ id: `system-${Date.now()}`, role: 'system', content: `작업지시서 v${latestOrder.version + 1}을 생성했습니다.`, createdAt: new Date().toISOString(), workOrderVersion: (latestOrder.version + 1) as 2 | 3 }])
      setApiProposal(null)
    } catch (error: unknown) {
      setApiError(apiErrorMessage(error))
    } finally {
      setRerunning(false)
    }
  }
  const cancelNextVersion = async () => discardProposal()
  const download = async () => {
    setDownloadState('working')
    try {
      await downloadDocumentPdf({
        title: `작업지시서 v${selectedOrder.version}`,
        fileName: `heatgrid-work-order-${number}-v${selectedOrder.version}.pdf`,
        metadata: [`문서번호 ${number}`, `대상 설비 ${alert.facility}`, `생성 ${new Date(selectedOrder.createdAt).toLocaleString('ko-KR')}`],
        content: selectedOrder.content,
      })
      setDownloadState('idle')
    } catch {
      setDownloadState('error')
    }
  }

  return <div className="scenario-order-layout">
    <SurfaceCard className="scenario-version-rail-card" title="작업지시서 목록"><ScenarioVersionRail acceptedVersion={state.acceptedWorkOrderVersion} latestVersion={latestOrder.version} messages={state.messages} onSelect={onSelectVersion} orders={state.workOrders} selectedVersion={selectedOrder.version} /></SurfaceCard>
    <SurfaceCard
      action={<StatusBadge tone={adopted ? 'success' : 'notice'}>{adopted ? '최종 채택' : '검토 중'}</StatusBadge>}
      className="scenario-order-document"
      title="작업지시서 상세"
    >
      <div className="scenario-document-toolbar">
        <div aria-label="작업지시서 버전" className="scenario-version-switch" role="tablist">
          {state.workOrders.map((order) => <button aria-selected={order.version === selectedOrder.version} className={order.version === selectedOrder.version ? 'active' : ''} key={order.version} onClick={() => onSelectVersion(order.version)} role="tab" type="button">v{order.version}{state.acceptedWorkOrderVersion === order.version ? ' · 채택' : ''}</button>)}
        </div>
        <div className="scenario-document-commands">
          {editing ? <><Button onClick={() => { setDraft(selectedOrder.content); setEditing(false) }}>취소</Button><Button icon="check" onClick={saveEdit} tone="primary">저장</Button></> : <Button icon="document" onClick={() => setEditing(true)}>수정</Button>}
          <Button disabled={downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'PDF 생성 중' : 'PDF 다운로드'}</Button>
        </div>
      </div>
      <article className="scenario-order-body">
        <header><div><span>문서번호 {number}</span><h2>{selectedOrder.title}</h2></div><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority === 'urgent' ? '긴급' : '경고'}</StatusBadge></header>
        <dl><div><dt>대상 설비</dt><dd>{alert.facility}</dd></div><div><dt>조치 기준</dt><dd>anomaly 우선순위에 따라 즉시 검토</dd></div><div><dt>담당</dt><dd>현장 운전팀</dd></div></dl>
        {editing ? <textarea aria-label="작업지시서 본문 편집" className="scenario-document-editor" onChange={(event) => setDraft(event.target.value)} value={draft} /> : <pre className="scenario-document-content">{selectedOrder.content}</pre>}
        {downloadState === 'error' && <p className="scenario-document-error" role="alert">PDF를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.</p>}
        <footer className="scenario-order-accept"><span>{adopted ? '이 버전이 보고서 생성 기준입니다.' : 'v1-v3 중 현장 조치 기준으로 사용할 버전을 선택하세요.'}</span><div><Button icon="check" onClick={adoptVersion} tone="primary">{adopted ? '최종 채택됨' : '최종 채택'}</Button><Button disabled={state.acceptedWorkOrderVersion == null} icon="document" onClick={onCreateReport}>보고서 생성</Button></div></footer>
      </article>
    </SurfaceCard>

    <SurfaceCard action={<StatusBadge tone={chatbotLocked ? 'neutral' : 'primary'}>재실행 {rerunsRemaining}회 남음</StatusBadge>} className="scenario-chat-card" title="AI 수정 챗봇">
      <div className="scenario-chat">
        <div className="scenario-chat-source"><StatusBadge tone="primary">큰 영역 수정</StatusBadge><span>모델·외부 데이터·RAG 문서 또는 문서 구조 변경을 확인한 뒤 새 버전을 생성합니다.</span></div>
        <div className="scenario-chat-messages">{state.messages.length === 0 && <p>큰 범위의 변경 내용을 입력하세요. 단어나 문장 말투는 왼쪽의 수정 기능으로 횟수 제한 없이 고칠 수 있습니다.</p>}{state.messages.map((item) => <article className={item.role} key={item.id}><strong>{item.role === 'operator' ? '운영자' : item.role === 'assistant' ? 'AI 검토' : '실행 결과'}</strong><span>{chatText(item.content)}</span></article>)}</div>
        <div className="scenario-chat-input"><label htmlFor="scenario-chat-message">수정 요청</label><textarea aria-describedby="scenario-chat-hint" disabled={chatbotLocked || rerunning || apiProposal != null} id="scenario-chat-message" onChange={(event) => setMessage(event.target.value)} onKeyDown={submitOnEnter} placeholder="예: 최신 점검 매뉴얼을 다시 검색해서 안전 절차를 보강해줘." value={message} /><span id="scenario-chat-hint">Enter 전송 · Shift+Enter 줄바꿈</span><Button disabled={!message.trim() || chatbotLocked || rerunning || apiProposal != null || reviewThread.isPending || postMessage.isPending} onClick={() => void sendMessage()} tone="primary">{reviewThread.isPending || postMessage.isPending ? '검토 중' : '제안 확인'}</Button></div>
        {apiError && <p className="scenario-analysis-error" role="alert">{apiError}</p>}
        {apiProposal && <div className="scenario-proposal"><header><div><span>수정 제안</span><strong>{proposalTargetLabel(apiProposal)}</strong></div><StatusBadge tone="warning">확인 필요</StatusBadge></header><p>{chatText(apiProposal.reason)}</p><dl><div><dt>생성 버전</dt><dd>v{latestOrder.version + 1}</dd></div><div><dt>남은 기회</dt><dd>실행 후 {Math.max(0, rerunsRemaining - 1)}회</dd></div></dl><div><Button disabled={rerunning || confirmProposal.isPending} onClick={() => void createNextVersion()} tone="primary">{rerunning || confirmProposal.isPending ? '재실행 중' : apiProposal.next_action === 'targeted_rerun' ? '새 버전 생성' : '검토 이력 저장'}</Button><Button disabled={rerunning || cancelProposal.isPending} onClick={() => void cancelNextVersion()}>취소</Button></div></div>}
        {chatbotLocked && <div className="scenario-chat-locked"><StatusBadge tone="neutral">v3 생성 완료</StatusBadge><p>AI 재실행 2회를 모두 사용했습니다. 문서 본문의 직접 수정은 계속할 수 있습니다.</p></div>}
      </div>
    </SurfaceCard>
  </div>
}
