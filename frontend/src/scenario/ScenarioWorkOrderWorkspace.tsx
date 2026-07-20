import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { OpsAgentResultV4, ReviewChatConfirmationResponse, ReviewChatProposalResponse, ReviewChatThreadResponse } from '../api/contracts'
import { ApiError, incidentDocumentsApi, reviewChatApi } from '../api/client'
import { useApproveIncidentWorkOrder, useCancelReviewChatProposal, useConfirmReviewChatProposal, useIncidentDocuments, usePostReviewChatMessage, useReviewChatMessages, useReviewChatPendingProposal, useReviewChatThreadOpen } from '../api/hooks'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { downloadDocumentPdf } from './documentPdf'
import type { ScenarioAlert, ScenarioState } from './types'
import { ScenarioVersionRail } from './ScenarioVersionRail'
import { detectWorkOrderRevisionTarget, isWorkOrderQuestion, isWorkOrderRevisionRequest, loadStoredReviewChatProposal, resolveWorkOrderRevisionTarget, reviewChatRequest, storeReviewChatProposal, visibleReviewChatContent, workOrderProposalPreview, type WorkOrderRevisionTarget } from './workOrderRevision'

interface Props {
  readonly alert: ScenarioAlert
  readonly state: ScenarioState
  readonly onAccept: (version: 1 | 2 | 3) => void
  readonly onCreateReport: () => void
  readonly onOpenAnalysis: () => void
  readonly onAppendMessages: (messages: ScenarioState['messages']) => void
  readonly onAppendRevision: (runId: string, result: import('../api/contracts').OpsAgentResultV4, instruction: string, target: WorkOrderRevisionTarget, baseVersion: 1 | 2 | 3, documentContent?: string) => void
  readonly onSelectDocumentGroup: (groupId: string) => void
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
  if (error instanceof ApiError && error.status === 409) {
    if (/expired|만료/i.test(error.message)) return '수정 초안의 확인 시간이 만료되었습니다. 같은 요청을 다시 보내 주세요.'
    if (/document version is stale|문서 버전/i.test(error.message)) return '선택한 문서 버전이 최신 상태와 다릅니다. 버전을 다시 선택해 주세요.'
    return '다른 검토 변경과 충돌했습니다. 최신 대화와 문서를 불러온 뒤 다시 시도해 주세요.'
  }
  if (error instanceof ApiError && error.status === 404) return '이 작업지시서의 대화 또는 문서 연결을 찾지 못했습니다.'
  if (error instanceof ApiError && error.status === 422) return '질문 또는 수정 요청 내용을 확인한 뒤 다시 보내 주세요.'
  if (error instanceof Error && /시간이 초과/.test(error.message)) return `${error.message} 서버 작업은 계속될 수 있으니 AI 분석 목록에서 상태를 확인해 주세요.`
  if (error instanceof Error && error.message.trim()) return error.message
  return 'AI 검토 요청을 처리하지 못했습니다. 입력 내용은 유지됩니다.'
}

function documentContextUnavailable(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || (error.status === 409 && /incident context is required for document lookup/i.test(error.message)))
}

function confirmationBlockReason(confirmation: ReviewChatConfirmationResponse): string | null {
  const reason = confirmation.blocked_reason ?? confirmation.block_reason
  if (reason) return reason
  const status = confirmation.rerun_status ?? confirmation.execution_status
  return status?.startsWith('blocked_') || status === 'rerun_limit_reached' || status === 'schedule_failed' ? status : null
}

function blockedReasonMessage(reason: string): string {
  if (reason === 'rerun_limit_reached') return 'v3까지 생성되어 AI 문서 수정 한도에 도달했습니다. 문서 질문은 계속할 수 있습니다.'
  if (reason === 'blocked_legacy_input_unavailable') return '원본 실행 입력을 복원할 수 없어 새 문서 버전을 만들지 못했습니다.'
  if (reason === 'blocked_integration_disabled') return '필요한 외부 근거 연동이 비활성화되어 새 문서 버전을 만들지 못했습니다.'
  if (reason === 'schedule_failed') return '수정 실행 예약에 실패했습니다. 잠시 후 같은 초안을 다시 확정해 주세요.'
  return `수정 실행이 차단되었습니다. (${reason})`
}

function savedDocumentNotice(version: number, reason: string): string {
  const detail = reason === 'rerun_limit_reached'
    ? '재실행 한도에 도달했습니다.'
    : reason === 'blocked_legacy_input_unavailable'
      ? '원본 실행 입력을 복원할 수 없었습니다.'
      : reason === 'blocked_integration_disabled'
        ? '외부 근거 연동이 비활성화되어 있습니다.'
        : reason === 'schedule_failed'
          ? '근거 재평가 예약에 실패했습니다.'
          : `재평가 상태: ${reason}`
  return `작업지시서 v${version} 문서는 저장됐고 근거 재평가는 생략되었습니다. ${detail}`
}

function canonicalDocumentBody(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value !== 'object' || value == null) return null
  if ('body' in value && typeof value.body === 'string') return value.body.trim() || null
  if ('content' in value && typeof value.content === 'string') return value.content.trim() || null
  return null
}

function canonicalResult(
  value: unknown,
  order: ScenarioState['workOrders'][number],
  runId: string,
  alert: ScenarioAlert,
): OpsAgentResultV4 {
  const record = typeof value === 'object' && value != null ? value as Record<string, unknown> : {}
  const stringList = (candidate: unknown): string[] => Array.isArray(candidate) ? candidate.filter((item): item is string => typeof item === 'string') : typeof candidate === 'string' ? candidate.split('\n').map((item) => item.trim()).filter(Boolean) : []
  const actionItems = stringList(record.actions)
  const safetyNotes = stringList(record.safety_notes)
  const evidenceItems = Array.isArray(record.evidence) ? record.evidence : []
  const actionSection = order.sections.find((section) => /작업\s*절차|권장\s*조치/.test(section.title))
  const cautionSection = order.sections.find((section) => /안전\s*확인|주의/.test(section.title))
  const evidenceSection = order.sections.find((section) => /위험|근거/.test(section.title))
  const headline = typeof record.title === 'string' ? record.title : order.title
  const body = canonicalDocumentBody(value) ?? order.content
  return {
    schema_version: 'ops_agent_result.v4',
    run_id: runId,
    card_id: `scenario-${alert.id}`,
    evaluation_run_id: null,
    manufacturer_id: null,
    substation_id: alert.substationId,
    headline,
    situation: evidenceSection?.items[0] ?? alert.summary,
    evidence: evidenceItems.flatMap((item, index) => {
      if (typeof item === 'string') return [{ label: `근거 ${index + 1}`, content: item, source: 'manual' as const }]
      if (typeof item !== 'object' || item == null) return []
      const label = 'label' in item && typeof item.label === 'string' ? item.label : `근거 ${index + 1}`
      const content = 'content' in item && typeof item.content === 'string' ? item.content : label
      return [{ label, content, source: 'manual' as const }]
    }),
    actions: (actionItems.length > 0 ? actionItems : actionSection?.items ?? []).map((item, index) => ({ priority: index + 1, title: item, detail: item })),
    cautions: safetyNotes.length > 0 ? safetyNotes : [...(cautionSection?.items ?? [])],
    report: { title: headline, format: 'markdown', content: body },
  }
}

function chatText(content: string): string {
  return content.replace(/\*\*|__|`/g, '').replace(/^\s{0,3}#{1,6}\s+/gm, '').trim()
}

function proposalTargetLabel(proposal: ReviewChatProposalResponse, target: WorkOrderRevisionTarget | null): string {
  if (target != null) return target.label
  if (proposal.revision?.target_area === 'risk_evidence') return '위험성 및 근거'
  if (proposal.reason_category === 'ml_prediction_issue') return '모델 재검증'
  if (proposal.reason_category === 'weather_context_issue') return '외부 데이터'
  if (proposal.reason_category === 'rag_retrieval_issue') return '참고 문서'
  return '작업지시서 본문'
}

export function ScenarioWorkOrderWorkspace({ alert, state, onAccept, onAppendMessages, onAppendRevision, onCreateReport, onOpenAnalysis, onSelectDocumentGroup, onSelectVersion, onUpdateContent }: Props) {
  const latestOrder = state.workOrders.at(-1)
  const selectedOrder = state.workOrders.find((order) => order.version === state.selectedWorkOrderVersion) ?? latestOrder
  const conversationRunId = state.workOrders[0]?.sourceRunId ?? null
  const conversationMessages = state.messages
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(selectedOrder?.content ?? '')
  const [rerunning, setRerunning] = useState(false)
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [threadRunId, setThreadRunId] = useState<string | null>(null)
  const [threadContext, setThreadContext] = useState<ReviewChatThreadResponse | null>(null)
  const [apiProposal, setApiProposal] = useState<ReviewChatProposalResponse | null>(null)
  const [pendingInstruction, setPendingInstruction] = useState<string | null>(null)
  const [pendingTarget, setPendingTarget] = useState<WorkOrderRevisionTarget | null>(null)
  const [pendingBaseVersion, setPendingBaseVersion] = useState<1 | 2 | 3 | null>(null)
  const [pendingBeforeContent, setPendingBeforeContent] = useState('')
  const [executionState, setExecutionState] = useState<'idle' | 'confirming' | 'queued' | 'running' | 'completed' | 'blocked' | 'failed'>('idle')
  const [contextNotice, setContextNotice] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const documentBodyRef = useRef<HTMLElement>(null)
  const chatMessagesRef = useRef<HTMLDivElement>(null)
  const reviewThread = useReviewChatThreadOpen()
  const postMessage = usePostReviewChatMessage()
  const confirmProposal = useConfirmReviewChatProposal()
  const cancelProposal = useCancelReviewChatProposal()
  const approveIncidentWorkOrder = useApproveIncidentWorkOrder()
  const reviewMessages = useReviewChatMessages(threadId)
  const pendingProposalQuery = useReviewChatPendingProposal(threadId)
  const incidentDocuments = useIncidentDocuments(threadContext?.incident_id ?? null)
  const messageIsRevision = isWorkOrderRevisionRequest(message)
  const previewData = apiProposal && pendingTarget
    ? workOrderProposalPreview(apiProposal, pendingTarget, pendingBeforeContent || selectedOrder?.content || '', pendingInstruction ?? apiProposal.reason)
    : null

  useEffect(() => {
    setDraft(selectedOrder?.content ?? '')
    setEditing(false)
  }, [selectedOrder?.content, selectedOrder?.version])

  useEffect(() => {
    const storedProposal = conversationRunId == null ? null : loadStoredReviewChatProposal(conversationRunId)
    setThreadId(null)
    setThreadRunId(null)
    setThreadContext(null)
    setApiProposal(storedProposal?.proposal ?? null)
    setPendingInstruction(storedProposal?.instruction ?? null)
    setPendingTarget(storedProposal?.target ?? null)
    setPendingBaseVersion(storedProposal?.baseVersion === 1 || storedProposal?.baseVersion === 2 || storedProposal?.baseVersion === 3 ? storedProposal.baseVersion : null)
    setPendingBeforeContent(storedProposal?.beforeContent ?? '')
    setExecutionState('idle')
    setContextNotice(null)
    if (conversationRunId == null) {
      setThreadId(null)
      return undefined
    }
    let cancelled = false
    void reviewChatApi.open(conversationRunId, { created_by: 'ops-manager', idempotency_key: requestId(`restore-thread-${conversationRunId}`) })
      .then((thread) => {
        if (!cancelled) {
          setThreadId(thread.thread_id)
          setThreadRunId(conversationRunId)
          setThreadContext(thread)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setApiError(apiErrorMessage(error))
      })
    return () => { cancelled = true }
  }, [alert.substationId, conversationRunId])

  useEffect(() => {
    if (!reviewMessages.data?.items.length || latestOrder == null || threadRunId !== conversationRunId) return
    onAppendMessages(reviewMessages.data.items.map((item) => ({
      id: `api-${item.message_id}`,
      role: item.role === 'operator' ? 'operator' as const : item.role === 'assistant' ? 'assistant' as const : 'system' as const,
      content: item.role === 'operator' ? visibleReviewChatContent(item.content) : item.content,
      createdAt: item.created_at,
      workOrderVersion: item.structured_payload.document_version === 1 || item.structured_payload.document_version === 2 || item.structured_payload.document_version === 3 ? item.structured_payload.document_version : latestOrder.version,
    })))
  }, [conversationRunId, latestOrder, onAppendMessages, reviewMessages.data?.items, threadRunId])

  useEffect(() => {
    const lookup = pendingProposalQuery.data
    if (conversationRunId == null || lookup == null || !lookup.supported) return
    if (lookup.proposal == null) {
      storeReviewChatProposal(conversationRunId, null)
      setApiProposal(null)
      setPendingInstruction(null)
      setPendingTarget(null)
      setPendingBaseVersion(null)
      setPendingBeforeContent('')
      setExecutionState('idle')
      return
    }
    const stored = loadStoredReviewChatProposal(conversationRunId)
    const instruction = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.instruction : lookup.proposal.reason
    const target = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.target : detectWorkOrderRevisionTarget(instruction)
    const baseVersionValue = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.baseVersion : lookup.proposal.base_document_version ?? selectedOrder?.version ?? latestOrder?.version ?? 1
    const baseVersion = baseVersionValue === 2 || baseVersionValue === 3 ? baseVersionValue : 1
    const beforeContent = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.beforeContent : selectedOrder?.content ?? ''
    setApiProposal(lookup.proposal)
    setPendingInstruction(instruction)
    setPendingTarget(target)
    setPendingBaseVersion(baseVersion)
    setPendingBeforeContent(beforeContent)
    storeReviewChatProposal(conversationRunId, { proposal: lookup.proposal, instruction, target, baseVersion, beforeContent, storedAt: new Date().toISOString() })
  }, [conversationRunId, latestOrder?.version, pendingProposalQuery.data, selectedOrder?.content, selectedOrder?.version])

  useEffect(() => {
    const log = chatMessagesRef.current
    if (log == null) return
    log.scrollTop = log.scrollHeight
  }, [apiProposal?.proposal_id, conversationMessages.length, executionState])

  if (!latestOrder || !selectedOrder) {
    return <SurfaceCard title="작업지시서"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 대기</StatusBadge><p>AI 분석 목록에서 완료된 분석을 열어 작업지시서를 생성하세요.</p><Button icon="arrow" onClick={onOpenAnalysis}>AI 분석 목록으로 이동</Button></div></SurfaceCard>
  }

  const rerunsRemaining = Math.max(0, 2 - state.workOrderRerunCount)
  const chatbotLocked = rerunsRemaining === 0
  const number = documentNumber(alert, selectedOrder.version)
  const adopted = state.acceptedWorkOrderVersion === selectedOrder.version
  const selectedServerDocument = incidentDocuments.data?.items.find((document) => document.document_type === 'work_order' && document.version === selectedOrder.version)
  const executionStateLabel: Record<typeof executionState, string> = {
    idle: '',
    confirming: '수정 초안을 확정하고 있습니다.',
    queued: 'AI 문서 수정 실행이 대기 중입니다.',
    running: '근거를 재검토하고 새 문서 버전을 생성하고 있습니다.',
    completed: '새 문서 버전 생성이 완료되었습니다.',
    blocked: '새 문서 버전 생성이 차단되었습니다.',
    failed: '새 문서 버전 생성 중 오류가 발생했습니다.',
  }

  const sendMessage = async () => {
    const instruction = message.trim()
    if (!instruction || reviewThread.isPending || postMessage.isPending || rerunning || apiProposal != null) return
    if (messageIsRevision && chatbotLocked) {
      setApiError('v3까지 생성되어 AI 문서 수정은 더 실행할 수 없습니다. 이전 요청 회상과 문서 질문은 계속할 수 있습니다.')
      return
    }
    setApiError(null)
    setContextNotice(null)
    if (conversationRunId == null) {
      setApiError('이전 세션에서 만든 작업지시서라 AI 재생성에 연결되지 않았습니다. 상단 새로고침 후 계획서에서 작업지시서를 다시 생성해 주세요.')
      return
    }
    try {
      let assistantContent = '수정 제안을 준비하지 못했습니다.'
      let activeThreadId = threadId
      if (activeThreadId == null || threadRunId !== conversationRunId) {
        const thread = await reviewThread.mutateAsync({ runId: conversationRunId, created_by: 'ops-manager', idempotency_key: requestId(`thread-${conversationRunId}`) })
        activeThreadId = thread.thread_id
        setThreadId(activeThreadId)
        setThreadRunId(conversationRunId)
        setThreadContext(thread)
      }
      const target = resolveWorkOrderRevisionTarget(
        instruction,
        conversationMessages.filter((item) => item.role === 'operator').map((item) => item.content),
      )
      const idempotencyKey = requestId(`message-${conversationRunId}`)
      const baseRequest = { content: reviewChatRequest(instruction, target), created_by: 'ops-manager', idempotency_key: idempotencyKey }
      const serverDocument = incidentDocuments.data?.items.find((document) => document.document_type === 'work_order' && document.version === selectedOrder.version)
      let response
      try {
        response = await postMessage.mutateAsync({
          threadId: activeThreadId,
          body: {
            ...baseRequest,
            ...(threadContext?.incident_id ? { incident_id: threadContext.incident_id } : {}),
            document_context: {
              ...(serverDocument?.document_version_id || (selectedOrder.version === 1 && threadContext?.document_version_id)
                ? { document_version_id: serverDocument?.document_version_id ?? threadContext?.document_version_id as string }
                : { document_type: 'work_order' as const }),
              expected_version: serverDocument?.version ?? (selectedOrder.version === 1 ? threadContext?.document_version ?? selectedOrder.version : selectedOrder.version),
            },
          },
        })
      } catch (error: unknown) {
        if (!documentContextUnavailable(error)) throw error
        response = await postMessage.mutateAsync({ threadId: activeThreadId, body: baseRequest })
        setContextNotice(`서버 문서 버전 연결을 찾지 못해 화면의 v${selectedOrder.version} 내용과 대화 이력을 기준으로 요청했습니다.`)
      }
      let nextProposal = response.proposal
      assistantContent = chatText(response.assistant_message.content)
      if (isWorkOrderQuestion(instruction) && nextProposal != null) {
        await cancelProposal.mutateAsync({ proposalId: nextProposal.proposal_id, body: { cancelled_by: 'ops-manager', idempotency_key: requestId(`question-cancel-${nextProposal.proposal_id}`) } })
        const remembered = conversationMessages.filter((item) => item.role === 'operator' && isWorkOrderRevisionRequest(item.content)).slice(-5)
        assistantContent = /(?:기억|뭐였지|무엇이었|요청한\s*(?:내용|사항))/.test(instruction) && remembered.length > 0
          ? `최근 문서 수정 요청은 다음과 같습니다.\n${remembered.map((item, index) => `${index + 1}. ${item.content}`).join('\n')}`
          : '질문을 문서 수정 실행으로 잘못 분류한 제안은 안전하게 취소했습니다. 문서 내용은 변경되지 않았습니다.'
        nextProposal = null
      }
      setApiProposal(nextProposal)
      setPendingInstruction(nextProposal == null ? null : instruction)
      setPendingTarget(nextProposal == null ? null : target)
      setPendingBaseVersion(nextProposal == null ? null : selectedOrder.version)
      setPendingBeforeContent(nextProposal == null ? '' : selectedOrder.content)
      if (nextProposal != null) storeReviewChatProposal(conversationRunId, { proposal: nextProposal, instruction, target, baseVersion: selectedOrder.version, beforeContent: selectedOrder.content, storedAt: new Date().toISOString() })
      else storeReviewChatProposal(conversationRunId, null)
      const createdAt = new Date().toISOString()
      onAppendMessages([
        { id: `api-${response.operator_message.message_id}`, role: 'operator', content: instruction, createdAt, workOrderVersion: selectedOrder.version },
        { id: `api-${response.assistant_message.message_id}`, role: 'assistant', content: assistantContent, createdAt, workOrderVersion: selectedOrder.version },
      ])
      setMessage((current) => current.trim() === instruction ? '' : current)
      void reviewMessages.refetch()
      void pendingProposalQuery.refetch()
    } catch (error: unknown) {
      setApiError(apiErrorMessage(error))
    }
  }
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }
  const scrollToChat = () => {
    chatMessagesRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  }
  const scrollToDocument = () => {
    documentBodyRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  }
  const discardProposal = async () => {
    const proposal = apiProposal
    if (proposal == null) return true
    try {
      await cancelProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { cancelled_by: 'ops-manager', idempotency_key: requestId(`cancel-${proposal.proposal_id}`) } })
      setApiProposal(null)
      setPendingInstruction(null)
      setPendingTarget(null)
      setPendingBaseVersion(null)
      setPendingBeforeContent('')
      setExecutionState('idle')
      if (conversationRunId) storeReviewChatProposal(conversationRunId, null)
      void pendingProposalQuery.refetch()
      return true
    } catch (error: unknown) {
      setApiError(apiErrorMessage(error))
      return false
    }
  }
  const saveEdit = async () => {
    if (adopted && state.report.status !== 'idle' && !window.confirm('이 버전은 현재 보고서의 기준 문서입니다.\n편집을 저장하면 기존 보고서와 보고서 메모를 초기화하고 다시 생성해야 합니다. 계속할까요?')) return
    if (!await discardProposal()) return
    onUpdateContent(selectedOrder.version, draft)
    setEditing(false)
  }
  const adoptVersion = async () => {
    const replacesReport = state.acceptedWorkOrderVersion != null && state.acceptedWorkOrderVersion !== selectedOrder.version && state.report.status !== 'idle'
    const reportWarning = replacesReport ? '\n기존 보고서와 보고서 메모는 초기화되며 새 기준 버전으로 다시 생성해야 합니다.' : ''
    if (!window.confirm(`작업지시서 v${selectedOrder.version}을 최종 채택할까요?\n보고서는 이 버전을 기준으로 생성됩니다.${reportWarning}`)) return
    const serverDocument = incidentDocuments.data?.items.find((document) => document.document_type === 'work_order' && document.version === selectedOrder.version)
    if (serverDocument != null) {
      const latestServerVersion = Math.max(...(incidentDocuments.data?.items.filter((document) => document.document_type === 'work_order').map((document) => document.version) ?? [serverDocument.version]))
      if (serverDocument.version !== latestServerVersion) {
        setApiError(`서버 정본은 v${latestServerVersion}입니다. 최신 버전만 최종 승인할 수 있습니다.`)
        return
      }
      try {
        await approveIncidentWorkOrder.mutateAsync({ incidentId: serverDocument.episode_id, body: { expected_version: serverDocument.version, approved_by: 'ops-manager', idempotency_key: requestId(`approve-document-${serverDocument.document_version_id}`), note: `작업지시서 v${selectedOrder.version} 운영자 최종 승인` } })
        void incidentDocuments.refetch()
      } catch (error: unknown) {
        setApiError(apiErrorMessage(error))
        return
      }
    }
    onAccept(selectedOrder.version)
  }
  const createNextVersion = async () => {
    if (rerunning || chatbotLocked) return
    setRerunning(true)
    setApiError(null)
    setContextNotice(null)
    setExecutionState('confirming')
    try {
      if (apiProposal == null) return
      const confirmation = await confirmProposal.mutateAsync({ proposalId: apiProposal.proposal_id, body: { confirmed_by: 'ops-manager', idempotency_key: requestId(`confirm-${apiProposal.proposal_id}`), expected_proposal_status: 'awaiting_confirmation', expected_review_version: apiProposal.expected_review_version } })
      const confirmedVersion = confirmation.document_version === 2 || confirmation.document_version === 3
        ? confirmation.document_version
        : (latestOrder.version + 1) as 2 | 3
      const confirmationIncidentId = confirmation.incident_id ?? threadContext?.incident_id ?? null
      let canonicalPayload: unknown = confirmation.document_content ?? (confirmation.document != null && typeof confirmation.document.content !== 'undefined' ? confirmation.document.content : confirmation.document)
      let documentContent = canonicalDocumentBody(canonicalPayload) ?? undefined
      if (confirmation.document_version != null && documentContent == null && confirmationIncidentId != null) {
        try {
          const documents = await incidentDocumentsApi.list(confirmationIncidentId)
          const savedDocument = documents.items.find((document) => document.document_type === 'work_order' && document.version === confirmation.document_version)
          if (savedDocument != null) {
            canonicalPayload = savedDocument.content
            documentContent = savedDocument.content.body.trim() || undefined
          }
        } catch {
          // The confirmation is authoritative; the normal query retry restores the document later.
        }
      }
      if (confirmation.document_version != null && documentContent == null) {
        const proposalDraft = apiProposal.draft_content?.trim() || apiProposal.revision?.body?.trim()
        if (proposalDraft) {
          canonicalPayload = { ...apiProposal.revision, body: proposalDraft }
          documentContent = proposalDraft
        } else if (apiProposal.revision != null) {
          canonicalPayload = apiProposal.revision
        }
      }
      if (confirmationIncidentId != null) {
        setThreadContext((current) => current == null ? current : {
          ...current,
          incident_id: confirmationIncidentId,
          document_version: confirmation.document_version ?? current.document_version,
          document_version_id: confirmation.document_version_id ?? current.document_version_id,
          document_content: documentContent != null ? { body: documentContent } : current.document_content,
        })
      }
      const documentSaved = confirmation.document_version != null || documentContent != null
      const blockedReason = confirmationBlockReason(confirmation)
      if (blockedReason != null && !documentSaved) {
        setExecutionState('blocked')
        setApiError(blockedReasonMessage(blockedReason))
        setApiProposal(null)
        setPendingInstruction(null)
        setPendingTarget(null)
        setPendingBaseVersion(null)
        setPendingBeforeContent('')
        if (conversationRunId) storeReviewChatProposal(conversationRunId, null)
        return
      }
      if (blockedReason != null) setContextNotice(savedDocumentNotice(confirmedVersion, blockedReason))
      if (confirmation.child_run_id == null && !documentSaved) {
        const message = apiProposal.next_action === 'targeted_rerun' ? '서버가 새 문서 버전을 만들지 못했습니다. 실행 입력과 재실행 제한 상태를 확인해 주세요.' : '실행 검토 의견을 저장했습니다. 문서 내용은 변경되지 않았습니다.'
        onAppendMessages([{ id: `system-${Date.now()}`, role: 'system', content: message, createdAt: new Date().toISOString(), workOrderVersion: selectedOrder.version }])
        setExecutionState(apiProposal.next_action === 'targeted_rerun' ? 'blocked' : 'completed')
        if (apiProposal.next_action === 'targeted_rerun') setApiError(message)
        setApiProposal(null)
        setPendingInstruction(null)
        setPendingTarget(null)
        setPendingBaseVersion(null)
        setPendingBeforeContent('')
        if (conversationRunId) storeReviewChatProposal(conversationRunId, null)
        return
      }
      const waitForResult = async () => {
        if (confirmation.child_run_id == null) throw new Error('새 문서 버전의 실행 결과를 찾지 못했습니다.')
        const { agentRunsApi } = await import('../api/backend')
        setExecutionState('queued')
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const status = await agentRunsApi.get(confirmation.child_run_id as string)
          if (status.status === 'completed') return agentRunsApi.result(confirmation.child_run_id as string)
          if (status.status === 'failed') throw new Error(status.error ?? 'AI 재실행에 실패했습니다.')
          setExecutionState(status.status === 'queued' ? 'queued' : 'running')
          await new Promise<void>((resolve) => window.setTimeout(resolve, 1_000))
        }
        throw new Error('AI 재실행 시간이 초과되었습니다.')
      }
      const instruction = pendingInstruction ?? apiProposal.reason
      const target = pendingTarget ?? detectWorkOrderRevisionTarget(instruction)
      const baseVersion = pendingBaseVersion ?? selectedOrder.version
      const revisionRunId = confirmation.child_run_id ?? confirmation.document_version_id ?? conversationRunId
      if (revisionRunId == null) throw new Error('새 문서 버전의 연결 ID를 찾지 못했습니다.')
      const result = documentSaved
        ? canonicalResult(canonicalPayload, selectedOrder, revisionRunId, alert)
        : await waitForResult()
      onAppendRevision(revisionRunId, result, instruction, target, baseVersion, documentContent)
      const completionMessage = blockedReason == null
        ? `v${baseVersion} 기준으로 ${target.label}을 수정한 작업지시서 v${confirmedVersion}을 생성했습니다.`
        : savedDocumentNotice(confirmedVersion, blockedReason)
      onAppendMessages([{ id: `system-${Date.now()}`, role: 'system', content: completionMessage, createdAt: new Date().toISOString(), workOrderVersion: confirmedVersion }])
      setApiProposal(null)
      setPendingInstruction(null)
      setPendingTarget(null)
      setPendingBaseVersion(null)
      setPendingBeforeContent('')
      setExecutionState('completed')
      if (conversationRunId) storeReviewChatProposal(conversationRunId, null)
      void reviewMessages.refetch()
      void pendingProposalQuery.refetch()
      if (threadContext?.incident_id) void incidentDocuments.refetch()
    } catch (error: unknown) {
      setApiError(apiErrorMessage(error))
      setExecutionState('failed')
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
    <SurfaceCard className="scenario-version-rail-card" title="작업지시서 목록"><ScenarioVersionRail activeGroupId={state.activeDocumentGroupId} groups={state.documentGroups} onSelect={onSelectDocumentGroup} /></SurfaceCard>
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
          <Button icon="activity" onClick={scrollToChat} tone="primary">AI 수정·질문으로 이동</Button>
          {editing ? <><Button onClick={() => { setDraft(selectedOrder.content); setEditing(false) }}>취소</Button><Button icon="check" onClick={() => void saveEdit()} tone="primary">세션 편집 저장</Button></> : selectedServerDocument ? <Button disabled icon="document">서버 정본은 AI 수정 사용</Button> : <Button icon="document" onClick={() => setEditing(true)}>세션 본문 직접 편집</Button>}
          <Button disabled={downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'PDF 생성 중' : 'PDF 다운로드'}</Button>
        </div>
      </div>
      <article className="scenario-order-body" ref={documentBodyRef}>
        <header><div><span>문서번호 {number}</span><h2>{selectedOrder.title}</h2></div><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority === 'urgent' ? '긴급' : '경고'}</StatusBadge></header>
        <dl><div><dt>대상 설비</dt><dd>{alert.facility}</dd></div><div><dt>조치 기준</dt><dd>anomaly 우선순위에 따라 즉시 검토</dd></div><div><dt>담당</dt><dd>현장 운전팀</dd></div></dl>
        {editing && <p className="work-order-chat-context-note">이 편집은 서버 정본이 없는 시나리오 세션 문서에만 저장됩니다. 저장 후에는 해당 버전을 다시 최종 채택해야 합니다.</p>}
        {editing ? <textarea aria-label="작업지시서 본문 편집" className="scenario-document-editor" onChange={(event) => setDraft(event.target.value)} value={draft} /> : <pre className="scenario-document-content">{selectedOrder.content}</pre>}
        {downloadState === 'error' && <p className="scenario-document-error" role="alert">PDF를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.</p>}
        <footer className="scenario-order-accept"><span>{adopted ? '이 버전이 보고서 생성 기준입니다.' : state.acceptedWorkOrderVersion != null ? `현재 보고서는 채택된 v${state.acceptedWorkOrderVersion} 기준입니다.` : 'v1-v3 중 현장 조치 기준으로 사용할 버전을 선택하세요.'}</span><div><Button disabled={approveIncidentWorkOrder.isPending} icon="check" onClick={() => void adoptVersion()} tone="primary">{adopted ? '최종 채택됨' : approveIncidentWorkOrder.isPending ? '문서 승인 중' : '선택 버전 최종 채택'}</Button><Button disabled={state.acceptedWorkOrderVersion == null} icon="document" onClick={onCreateReport}>{state.report.status === 'idle' ? '보고서 생성' : '보고서 보기'}</Button></div></footer>
      </article>
    </SurfaceCard>

    <SurfaceCard action={<StatusBadge tone={chatbotLocked ? 'neutral' : 'primary'}>문서 수정 {rerunsRemaining}회 남음</StatusBadge>} className="scenario-chat-card" title="AI 문서 검토 챗봇">
      <div className="scenario-chat">
        <div className="scenario-chat-source"><StatusBadge tone="primary">기계실 {alert.substationId} · 선택 v{selectedOrder.version}</StatusBadge><span>이 기계실 작업지시서 전용 대화입니다. 선택한 버전을 문맥과 수정 기준으로 사용하며 다른 기계실과 공유하지 않습니다.</span><Button onClick={scrollToDocument}>문서 본문 보기</Button></div>
        <div aria-busy={reviewMessages.isLoading} aria-live="polite" className="scenario-chat-messages" ref={chatMessagesRef}>{reviewMessages.isLoading && conversationMessages.length === 0 ? <p>이 작업지시서의 대화 기록을 불러오는 중입니다.</p> : conversationMessages.length === 0 && <p>수정 범위와 내용을 함께 입력하세요. 예: “안전 확인 2번째 항목만 보호구 기준에 맞게 수정해줘.”</p>}{conversationMessages.map((item) => <article className={item.role} key={item.id}><strong>{item.role === 'operator' ? '운영자' : item.role === 'assistant' ? 'AI 검토' : '실행 결과'}</strong><span>{chatText(item.content)}</span></article>)}</div>
        <div className="scenario-chat-input"><label htmlFor="scenario-chat-message">문서 질문 또는 수정 요청</label><textarea aria-describedby="scenario-chat-hint" disabled={reviewThread.isPending || postMessage.isPending || rerunning || apiProposal != null} id="scenario-chat-message" onChange={(event) => setMessage(event.target.value)} onKeyDown={submitOnEnter} placeholder={chatbotLocked ? '예: 내가 요청한 수정 내용이 뭐였지?' : '예: 안전 확인 2번째 항목만 최신 보호구 기준으로 수정해줘.'} value={message} /><span id="scenario-chat-hint">Enter 전송 · Shift+Enter 줄바꿈 · v3에서도 질문 가능</span><Button disabled={!message.trim() || (chatbotLocked && messageIsRevision) || rerunning || apiProposal != null || reviewThread.isPending || postMessage.isPending} onClick={() => void sendMessage()} tone="primary">{reviewThread.isPending || postMessage.isPending ? '검토 중' : messageIsRevision ? '수정 초안 요청' : '질문 보내기'}</Button></div>
        {apiError && <p className="scenario-analysis-error" role="alert">{apiError}</p>}
        {apiProposal && previewData && <div className="scenario-proposal"><header><div><span>확정 전 수정 초안</span><strong>{proposalTargetLabel(apiProposal, pendingTarget)}</strong></div><StatusBadge tone="warning">v{pendingBaseVersion ?? selectedOrder.version} → v{Math.min(3, latestOrder.version + 1)}</StatusBadge></header><p>{previewData.changeSummary}</p><div className="work-order-proposal-diff"><section><b>수정 전</b><pre>{previewData.before || '비교할 기존 문구가 없습니다.'}</pre></section>{previewData.after && <section><b>{previewData.afterLabel}</b><pre>{previewData.after}</pre></section>}</div>{!previewData.after && <p className="work-order-proposal-note">서버가 문안 초안을 제공하지 않아 변경 요약만 표시합니다. 확정 시 선택한 버전을 기준으로 새 문서를 생성합니다.</p>}<dl><div><dt>기준 버전</dt><dd>v{pendingBaseVersion ?? selectedOrder.version}</dd></div><div><dt>유지 범위</dt><dd>{pendingTarget?.section === 'document' ? '전체 문서 재작성' : '지정 부분 외 모두 유지'}</dd></div><div><dt>생성 버전</dt><dd>v{Math.min(3, latestOrder.version + 1)}</dd></div><div><dt>남은 기회</dt><dd>실행 후 {Math.max(0, rerunsRemaining - 1)}회</dd></div></dl><div><Button disabled={rerunning || cancelProposal.isPending} onClick={() => void cancelNextVersion()}>초안 취소</Button><Button disabled={rerunning || confirmProposal.isPending || chatbotLocked} onClick={() => void createNextVersion()} tone="primary">{rerunning || confirmProposal.isPending ? '새 버전 생성 중' : `초안 확정 · v${Math.min(3, latestOrder.version + 1)} 생성`}</Button></div></div>}
        {executionState !== 'idle' && <p className={`work-order-chat-execution ${executionState}`} role="status">{executionStateLabel[executionState]}</p>}
        {contextNotice && <p className="work-order-chat-context-note">{contextNotice}</p>}
        {chatbotLocked && <div className="scenario-chat-locked"><StatusBadge tone="neutral">v3 생성 완료</StatusBadge><p>AI 문서 수정 2회를 모두 사용했습니다. 이전 요청 회상과 문서 질문은 계속할 수 있으며, 서버 정본이 없는 세션 문서만 직접 편집할 수 있습니다.</p></div>}
      </div>
    </SurfaceCard>
  </div>
}
