import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { OperatorReviewDecision, OpsAgentOutput, OpsAgentResultV4, ReviewChatConfirmationResponse, ReviewChatMessageResponse, ReviewChatProposalResponse, ReviewChatThreadResponse, WorkOrderListItem } from '../../api/contracts'
import { isWorkOrderStructuredContent } from '../../api/contracts'
import { displayAlertReason } from '../../domain/alertReason'
import { ApiError, incidentDocumentsApi, reviewChatApi } from '../../api/client'
import { useApproveIncidentWorkOrder, useCancelReviewChatProposal, useConfirmReviewChatProposal, useEditIncidentWorkOrder, useIncidentDocuments, usePostReviewChatMessage, useReviewChatMessages, useReviewChatPendingProposal, useReviewChatThreadOpen, useAgentRunResult } from '../../api/hooks'
import { downloadDocumentPdf } from '../../scenario/documentPdf'
import { useConfirmDialog } from '../ConfirmDialog'
import { ApiState, Button, StatusBadge, SurfaceCard } from '../ui'
import { facilityName, formatDateTime, priorityLabel, priorityTone, reviewStatusTone, workOrderStatusLabel } from './activityMappers'
import { ReviewActionModal } from './ReviewActionModal'
import { WorkOrderStructuredPanel } from './WorkOrderStructuredPanel'
import { legacyViewOfContent } from './workOrderStructuredView'
import { detectWorkOrderRevisionTarget, isWorkOrderProposalConfirmation, isWorkOrderRevisionRequest, loadStoredReviewChatProposal, mergeOpsAgentResult, resolveWorkOrderRevisionScope, reviewChatRequest, storeReviewChatProposal, visibleReviewChatContent, workOrderProposalPreview, type WorkOrderRevisionTarget } from '../../scenario/workOrderRevision'

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
  if (error instanceof ApiError && error.status === 409) {
    if (/expired|만료/i.test(error.message)) return '수정 초안의 확인 시간이 만료되었습니다. 같은 요청을 다시 보내 새 초안을 받아 주세요.'
    if (/document version is stale|문서 버전/i.test(error.message)) return '선택한 문서 버전이 최신 상태와 다릅니다. 버전을 다시 선택한 뒤 요청해 주세요.'
    return '다른 검토 변경과 충돌했습니다. 최신 대화와 문서를 불러온 뒤 다시 시도해 주세요.'
  }
  if (error instanceof ApiError && error.status === 422) {
    if (/부적절한 내용/.test(error.message)) return '부적절한 내용이 포함되어 있어 처리할 수 없습니다.'
    return '수정 요청 내용을 확인한 뒤 다시 보내 주세요.'
  }
  if (error instanceof ApiError && error.status === 404) return '이 작업지시서의 대화 또는 문서 연결을 찾지 못했습니다.'
  if (error instanceof Error && /시간이 초과/.test(error.message)) return `${error.message} 서버 작업은 계속될 수 있으니 AI 분석 목록에서 상태를 확인해 주세요.`
  if (error instanceof Error && error.message.trim()) return error.message
  return 'AI 검토 요청을 처리하지 못했습니다. 입력 내용은 유지됩니다.'
}

function documentContextUnavailable(error: unknown): boolean {
  return error instanceof ApiError && (
    error.status === 404 ||
    (error.status === 409 && /incident context is required for document lookup/i.test(error.message))
  )
}

function blockedReasonMessage(reason: string | null | undefined): string | null {
  if (!reason) return null
  if (reason === 'rerun_limit_reached') return 'v3까지 생성되어 AI 문서 수정 한도에 도달했습니다. 기존 버전 질문과 실행 검토는 계속할 수 있습니다.'
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

function confirmationBlockReason(confirmation: ReviewChatConfirmationResponse): string | null {
  const reason = confirmation.blocked_reason ?? confirmation.block_reason
  if (reason) return reason
  const status = confirmation.rerun_status ?? confirmation.execution_status
  return status?.startsWith('blocked_') || status === 'rerun_limit_reached' || status === 'schedule_failed' ? status : null
}

function canonicalDocument(value: unknown): { readonly title: string | null; readonly body: string | null } {
  if (typeof value === 'string') return { title: null, body: value.trim() || null }
  if (typeof value !== 'object' || value == null) return { title: null, body: null }
  const title = 'title' in value && typeof value.title === 'string' ? value.title.trim() || null : null
  const body = 'body' in value && typeof value.body === 'string'
    ? value.body.trim() || null
    : 'content' in value && typeof value.content === 'string'
      ? value.content.trim() || null
      : null
  return { title, body }
}

function chatText(content: string): string {
  return content.replace(/\*\*|__|`/g, '').replace(/^\s{0,3}#{1,6}\s+/gm, '').trim()
}

function visibleMessageContent(message: ReviewChatMessageResponse): string {
  const content = chatText(message.content)
  return message.role === 'operator' ? visibleReviewChatContent(content) : content
}

interface StoredRevision {
  readonly version: number
  readonly title: string
  readonly result: OpsAgentResultV4
  readonly content?: string
  readonly runId?: string
  readonly documentVersionId?: string
  readonly documentVersion?: number
  readonly incidentId?: string
  readonly approved?: boolean
  readonly instruction: string
  readonly target: WorkOrderRevisionTarget
  readonly createdAt: string
}

function revisionStorageKey(runId: string): string {
  return `heatgrid:work-order-revisions:${runId}`
}

function loadRevisions(runId: string): readonly StoredRevision[] {
  try {
    const raw = window.sessionStorage.getItem(revisionStorageKey(runId))
    if (raw == null) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is StoredRevision => (
      typeof item === 'object' && item != null &&
      'version' in item && typeof item.version === 'number' && Number.isInteger(item.version) && item.version >= 2 &&
      'title' in item && typeof item.title === 'string' &&
      'instruction' in item && typeof item.instruction === 'string' &&
      'createdAt' in item && typeof item.createdAt === 'string' &&
      'result' in item && typeof item.result === 'object' && item.result != null &&
      'schema_version' in item.result && item.result.schema_version === 'ops_agent_result.v4' &&
      'target' in item && typeof item.target === 'object' && item.target != null
    )).sort((left, right) => left.version - right.version)
  } catch {
    return []
  }
}

function mergeRevisions(...groups: readonly (readonly StoredRevision[])[]): readonly StoredRevision[] {
  const versions = new Map<number, StoredRevision>()
  for (const group of groups) for (const revision of group) versions.set(revision.version, revision)
  return [...versions.values()].sort((left, right) => left.version - right.version)
}

function storeRevisions(runId: string, revisions: readonly StoredRevision[]): void {
  window.sessionStorage.setItem(revisionStorageKey(runId), JSON.stringify(revisions))
}

function bodyFromResult(title: string, result: OpsAgentResultV4): string {
  return [
    '1. 작업 목적',
    `${title} 대응을 위한 현장 점검과 안전 조치를 수행합니다.`,
    '',
    '2. 작업 절차',
    ...result.actions.map((action, index) => `${index + 1}. ${action.title}\n${action.detail}`),
    '',
    '3. 안전 확인',
    ...result.cautions.map((caution) => `- ${caution}`),
  ].join('\n')
}

function numberedActionSteps(detail: string): readonly string[] {
  return [...detail.matchAll(/(?:^|\s)\d+\)\s*([\s\S]*?)(?=\s+\d+\)\s|$)/gu)]
    .map((match) => match[1]?.trim() ?? '')
    .filter(Boolean)
}

function workOrderSummaryLines(actions: OpsAgentResultV4['actions']): readonly string[] {
  return actions.flatMap((action) => {
    const steps = numberedActionSteps(action.detail)
    if (steps.length > 0) return steps
    return [`${action.title}${action.detail ? ` · ${action.detail}` : ''}`]
  }).filter(Boolean).slice(0, 3)
}

export function WorkOrderDetail({ item, mode = 'detail', onClose, onOpenDetail }: Props) {
  const result = useAgentRunResult(item.run_id)
  const { confirm: askConfirm, dialog: confirmDialog } = useConfirmDialog()
  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [reviewDecision, setReviewDecision] = useState<OperatorReviewDecision | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [threadContext, setThreadContext] = useState<ReviewChatThreadResponse | null>(null)
  const [draft, setDraft] = useState('')
  const [chatError, setChatError] = useState<string | null>(null)
  const [proposal, setProposal] = useState<ReviewChatProposalResponse | null>(null)
  const [localMessages, setLocalMessages] = useState<readonly ReviewChatMessageResponse[]>([])
  const [revisions, setRevisions] = useState<readonly StoredRevision[]>(() => loadRevisions(item.run_id))
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [pendingInstruction, setPendingInstruction] = useState<string | null>(null)
  const [pendingTarget, setPendingTarget] = useState<WorkOrderRevisionTarget | null>(null)
  const [pendingBaseVersion, setPendingBaseVersion] = useState<number | null>(null)
  const [pendingBeforeContent, setPendingBeforeContent] = useState('')
  const [revising, setRevising] = useState(false)
  const [executionState, setExecutionState] = useState<'idle' | 'confirming' | 'queued' | 'running' | 'completed' | 'blocked' | 'failed'>('idle')
  const [contextNotice, setContextNotice] = useState<string | null>(null)
  const [manualEditing, setManualEditing] = useState(false)
  const [manualTitle, setManualTitle] = useState('')
  const [manualBody, setManualBody] = useState('')
  const [manualNote, setManualNote] = useState('운영자 직접 편집')
  const documentSectionRef = useRef<HTMLElement>(null)
  const chatSectionRef = useRef<HTMLElement>(null)
  const chatLogRef = useRef<HTMLDivElement>(null)
  const reviewThread = useReviewChatThreadOpen()
  const postMessage = usePostReviewChatMessage()
  const confirmProposal = useConfirmReviewChatProposal()
  const cancelProposal = useCancelReviewChatProposal()
  const approveIncidentWorkOrder = useApproveIncidentWorkOrder()
  const editIncidentWorkOrder = useEditIncidentWorkOrder()
  const reviewMessages = useReviewChatMessages(threadId)
  const pendingProposalQuery = useReviewChatPendingProposal(threadId)
  const storageRunId = threadContext?.run_id ?? item.run_id
  const knownIncidentId = threadContext?.incident_id ?? revisions.find((revision) => revision.incidentId)?.incidentId ?? null
  const incidentDocuments = useIncidentDocuments(knownIncidentId)
  const alertReason = displayAlertReason(item.alert_reason)
  const baseTitle = alertReason === '-' ? `${facilityName(item.substation_id, item.manufacturer_id)} 이상 대응 작업지시서` : alertReason
  const latestRevision = revisions.at(-1)
  const latestVersion = latestRevision?.version ?? 1
  const activeVersion = selectedVersion ?? latestRevision?.version ?? 1
  const activeRevision = revisions.find((revision) => revision.version === activeVersion)
  const activeResult = activeRevision?.result ?? result.data ?? null
  const baseServerDocument = incidentDocuments.data?.items.find((document) => document.document_type === 'work_order' && document.version === 1)
  const baseServerContentView = baseServerDocument ? legacyViewOfContent(baseServerDocument.content) : null
  const structuredContent = baseServerDocument && isWorkOrderStructuredContent(baseServerDocument.content) ? baseServerDocument.content : null
  const threadDocument = canonicalDocument(threadContext?.document_content)
  const activeThreadDocument = (threadContext?.document_version ?? 1) === activeVersion ? threadDocument : { title: null, body: null }
  const title = activeRevision?.title ?? baseServerContentView?.title ?? activeThreadDocument.title ?? baseTitle
  const number = `HG-${compactDate(item.created_at)}-${item.substation_id ?? 'NA'}-v${activeVersion}`
  const body = activeRevision?.content ?? baseServerContentView?.body ?? activeThreadDocument.body ?? (activeResult == null ? '' : bodyFromResult(title, activeResult))
  const reviewOutput: OpsAgentOutput | null = activeResult == null ? null : { summary: activeResult.situation, action_plan: activeResult.actions.map((action) => `${action.title}: ${action.detail}`).join('\n'), caution: activeResult.cautions.join('\n') }
  const previewActions = activeResult == null ? [] : workOrderSummaryLines(activeResult.actions)
  const messages = useMemo(() => {
    const merged = new Map<string, ReviewChatMessageResponse>()
    for (const message of reviewMessages.data?.items ?? []) merged.set(message.message_id, message)
    for (const message of localMessages) merged.set(message.message_id, message)
    return [...merged.values()].sort((left, right) => left.sequence - right.sequence || left.created_at.localeCompare(right.created_at))
  }, [localMessages, reviewMessages.data?.items])
  const chatHistoryLoading = mode === 'detail' && chatError == null && (threadId == null || reviewMessages.isLoading)
  const rerunsRemaining = Math.max(0, 3 - latestVersion)
  const revisionLimitReached = rerunsRemaining === 0
  const draftIsRevision = isWorkOrderRevisionRequest(draft)
  const activeReviewRunId = activeRevision?.runId ?? activeRevision?.result.run_id ?? item.run_id
  const activeServerDocument = incidentDocuments.data?.items.find((document) => document.document_type === 'work_order' && document.version === activeVersion)
  const activeStructuredContent = activeServerDocument && isWorkOrderStructuredContent(activeServerDocument.content) ? activeServerDocument.content : structuredContent
  const activeIncidentId = activeRevision?.incidentId ?? activeServerDocument?.episode_id ?? threadContext?.incident_id ?? null
  const activeDocumentVersion = activeRevision?.documentVersion ?? activeServerDocument?.version ?? (activeVersion === 1 ? threadContext?.document_version ?? null : null)
  const activeDocumentVersionId = activeRevision?.documentVersionId ?? activeServerDocument?.document_version_id ?? (activeVersion === 1 ? threadContext?.document_version_id ?? null : null)
  const activeDocumentApproved = activeRevision?.approved ?? activeServerDocument?.status === 'approved'
  const latestCanonicalVersion = Math.max(latestVersion, ...(incidentDocuments.data?.items.filter((document) => document.document_type === 'work_order').map((document) => document.version) ?? [1]))
  const selectedIsLatest = activeVersion === latestCanonicalVersion
  const draftConfirmsProposal = proposal != null && isWorkOrderProposalConfirmation(draft)
  const pendingRequirements = pendingInstruction?.split('\n').map((item) => item.trim()).filter(Boolean) ?? []
  const previewData = proposal && pendingTarget
    ? workOrderProposalPreview(proposal, pendingTarget, pendingBeforeContent || body, pendingInstruction ?? proposal.reason)
    : null
  const executionStateLabel: Record<typeof executionState, string> = {
    idle: '',
    confirming: '수정 초안을 확정하고 있습니다.',
    queued: 'AI 문서 수정 실행이 대기 중입니다.',
    running: '근거를 재검토하고 새 문서 버전을 생성하고 있습니다.',
    completed: '새 문서 버전 생성이 완료되었습니다.',
    blocked: '새 문서 버전 생성이 차단되었습니다.',
    failed: '새 문서 버전 생성 중 오류가 발생했습니다.',
  }

  useEffect(() => {
    const log = chatLogRef.current
    if (log == null) return
    log.scrollTop = log.scrollHeight
  }, [executionState, messages.length, proposal?.proposal_id])

  useEffect(() => {
    const stored = loadRevisions(item.run_id)
    const storedProposal = loadStoredReviewChatProposal(item.run_id)
    setRevisions(stored)
    setSelectedVersion(stored.at(-1)?.version ?? null)
    setThreadId(null)
    setThreadContext(null)
    setLocalMessages([])
    setProposal(storedProposal?.proposal ?? null)
    setPendingInstruction(storedProposal?.instruction ?? null)
    setPendingTarget(storedProposal?.target ?? null)
    setPendingBaseVersion(storedProposal?.baseVersion ?? null)
    setPendingBeforeContent(storedProposal?.beforeContent ?? '')
    setExecutionState('idle')
    setContextNotice(null)
    setManualEditing(false)
  }, [item.run_id])

  useEffect(() => {
    if (mode !== 'detail') {
      setThreadId(null)
      setThreadContext(null)
      setChatError(null)
      return undefined
    }
    let cancelled = false
    setThreadId(null)
    setLocalMessages([])
    setChatError(null)
    void reviewChatApi.open(item.run_id, { created_by: 'ops-manager', idempotency_key: requestId(`restore-thread-${item.run_id}`) })
      .then((thread) => {
        if (!cancelled) {
          setThreadId(thread.thread_id)
          setThreadContext(thread)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setChatError(chatErrorMessage(error))
      })
    return () => { cancelled = true }
  }, [item.run_id, mode])

  useEffect(() => {
    const canonicalRunId = threadContext?.run_id
    if (canonicalRunId == null || canonicalRunId === item.run_id) return
    setRevisions((current) => {
      const next = mergeRevisions(loadRevisions(canonicalRunId), loadRevisions(item.run_id), current)
      storeRevisions(canonicalRunId, next)
      return next
    })
    const stored = loadStoredReviewChatProposal(canonicalRunId) ?? loadStoredReviewChatProposal(item.run_id)
    if (stored != null) {
      storeReviewChatProposal(canonicalRunId, stored)
      setProposal(stored.proposal)
      setPendingInstruction(stored.instruction)
      setPendingTarget(stored.target)
      setPendingBaseVersion(stored.baseVersion)
      setPendingBeforeContent(stored.beforeContent)
    }
  }, [item.run_id, threadContext?.run_id])

  useEffect(() => {
    const lookup = pendingProposalQuery.data
    if (lookup == null || !lookup.supported) return
    if (lookup.proposal == null) {
      storeReviewChatProposal(storageRunId, null)
      setProposal(null)
      setPendingInstruction(null)
      setPendingTarget(null)
      setPendingBaseVersion(null)
      setPendingBeforeContent('')
      setExecutionState('idle')
      return
    }
    const stored = loadStoredReviewChatProposal(storageRunId)
    const instruction = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.instruction : lookup.proposal.reason
    const target = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.target : detectWorkOrderRevisionTarget(instruction)
    const baseVersion = stored?.proposal.proposal_id === lookup.proposal.proposal_id
      ? stored.baseVersion
      : lookup.proposal.base_document_version ?? activeVersion
    const beforeContent = stored?.proposal.proposal_id === lookup.proposal.proposal_id ? stored.beforeContent : body
    setProposal(lookup.proposal)
    setPendingInstruction(instruction)
    setPendingTarget(target)
    setPendingBaseVersion(baseVersion)
    setPendingBeforeContent(beforeContent)
    storeReviewChatProposal(storageRunId, { proposal: lookup.proposal, instruction, target, baseVersion, beforeContent, storedAt: new Date().toISOString() })
  }, [activeVersion, body, pendingProposalQuery.data, storageRunId])

  useEffect(() => {
    if (proposal != null || pendingProposalQuery.data?.supported) return
    const stored = loadStoredReviewChatProposal(storageRunId)
    if (stored == null) return
    const pendingId = [...messages].reverse().find((message) => message.message_kind === 'action_proposal')?.structured_payload.proposal_id
    const executedAfter = [...messages].reverse().find((message) => message.message_kind === 'execution_result')
    if (executedAfter != null || (typeof pendingId === 'string' && pendingId !== stored.proposal.proposal_id)) return
    setProposal(stored.proposal)
    setPendingInstruction(stored.instruction)
    setPendingTarget(stored.target)
    setPendingBaseVersion(stored.baseVersion)
    setPendingBeforeContent(stored.beforeContent)
  }, [messages, pendingProposalQuery.data?.supported, proposal, storageRunId])

  useEffect(() => {
    const context = threadContext
    const version = context?.document_version
    const document = canonicalDocument(context?.document_content)
    const baseResult = result.data
    if (context == null || version == null || version < 2 || document.body == null || baseResult == null) return
    setRevisions((current) => {
      const existing = current.find((revision) => revision.version === version)
      const restored: StoredRevision = {
        version,
        title: document.title ?? existing?.title ?? baseTitle,
        result: existing?.result ?? baseResult,
        content: document.body as string,
        runId: existing?.runId,
        documentVersionId: context.document_version_id ?? existing?.documentVersionId,
        documentVersion: version,
        incidentId: context.incident_id ?? existing?.incidentId,
        approved: existing?.approved,
        instruction: existing?.instruction ?? '서버 최신 문서에서 복원',
        target: existing?.target ?? detectWorkOrderRevisionTarget('작업지시서 전체 수정'),
        createdAt: existing?.createdAt ?? context.created_at,
      }
      const next = mergeRevisions(current, [restored])
      storeRevisions(storageRunId, next)
      return next
    })
    setSelectedVersion((current) => current ?? version)
  }, [baseTitle, result.data, storageRunId, threadContext])

  useEffect(() => {
    const baseResult = result.data
    const documents = incidentDocuments.data?.items
      .filter((document) => document.document_type === 'work_order' && document.version >= 2)
      .sort((left, right) => left.version - right.version)
    if (baseResult == null || documents == null || documents.length === 0) return
    setRevisions((current) => {
      const next = documents.map((document): StoredRevision => {
        const existing = current.find((revision) => revision.version === document.version)
        const contentView = legacyViewOfContent(document.content)
        return {
          version: document.version,
          title: contentView.title,
          result: existing?.result ?? baseResult,
          content: contentView.body,
          runId: existing?.runId,
          documentVersionId: document.document_version_id,
          documentVersion: document.version,
          incidentId: document.episode_id,
          approved: document.status === 'approved',
          instruction: existing?.instruction ?? '서버 문서 버전에서 복원',
          target: existing?.target ?? detectWorkOrderRevisionTarget('작업지시서 전체 수정'),
          createdAt: document.created_at,
        }
      })
      storeRevisions(storageRunId, next)
      return next
    })
    setSelectedVersion((current) => current === 1 || (current != null && documents.some((document) => document.version === current)) ? current : documents.at(-1)?.version ?? null)
  }, [incidentDocuments.data?.items, result.data, storageRunId])

  const download = async () => {
    if (!body) return
    setDownloadState('working')
    try {
      await downloadDocumentPdf({ title: `작업지시서 v${activeVersion}`, fileName: `heatgrid-work-order-${number}-v${activeVersion}.pdf`, metadata: [`문서번호 ${number}`, `대상 설비 ${facilityName(item.substation_id, item.manufacturer_id)}`, `생성 ${formatDateTime(activeRevision?.createdAt ?? item.created_at)}`], content: body })
      setDownloadState('idle')
    } catch (error: unknown) {
      setDownloadState('error')
      setChatError(chatErrorMessage(error))
    }
  }

  const sendMessage = async () => {
    const content = draft.trim()
    if (!content || reviewThread.isPending || postMessage.isPending || revising) return
    if (proposal != null && isWorkOrderProposalConfirmation(content)) {
      setDraft('')
      await confirm()
      return
    }
    const revisionRequest = isWorkOrderRevisionRequest(content)
    if (revisionRequest && revisionLimitReached) {
      setChatError('v3까지 생성되어 AI 문서 수정은 더 실행할 수 없습니다. 기존 버전에 대한 질문은 계속할 수 있습니다.')
      return
    }
    setChatError(null)
    setContextNotice(null)
    try {
      const previousProposal = proposal
      const previousInstruction = pendingInstruction
      const previousTarget = pendingTarget
      let activeThreadId = threadId
      if (activeThreadId == null) {
        const thread = await reviewThread.mutateAsync({ runId: item.run_id, created_by: 'ops-manager', idempotency_key: requestId(`thread-${item.run_id}`) })
        activeThreadId = thread.thread_id
        setThreadId(activeThreadId)
        setThreadContext(thread)
      }
      const scope = resolveWorkOrderRevisionScope(
        content,
        messages.filter((chatMessage) => chatMessage.role === 'operator').map(visibleMessageContent),
        body,
      )
      const target = scope.target ?? previousTarget
      if (revisionRequest && target == null) {
        setChatError(scope.clarification ?? '수정할 문서 범위를 확인해 주세요.')
        return
      }
      const requestTarget = target ?? detectWorkOrderRevisionTarget(content)
      const messageContent = reviewChatRequest(content, requestTarget)
      const idempotencyKey = requestId(`message-${item.run_id}`)
      const baseRequest = { content: messageContent, created_by: 'ops-manager', idempotency_key: idempotencyKey }
      let response
      try {
        response = await postMessage.mutateAsync({
          threadId: activeThreadId,
          body: {
            ...baseRequest,
            ...(activeIncidentId ? { incident_id: activeIncidentId } : {}),
            document_context: {
              ...(activeDocumentVersionId ? { document_version_id: activeDocumentVersionId } : { document_type: 'work_order' as const }),
              expected_version: activeDocumentVersion ?? activeVersion,
            },
          },
        })
      } catch (error: unknown) {
        if (!documentContextUnavailable(error)) throw error
        response = await postMessage.mutateAsync({ threadId: activeThreadId, body: baseRequest })
        setContextNotice(`서버 문서 버전 연결을 찾지 못해 화면의 v${activeVersion} 내용과 대화 이력을 기준으로 요청했습니다.`)
      }
      const nextProposal = response.proposal ?? previousProposal
      setLocalMessages((current) => [...current, { ...response.operator_message, content }, response.assistant_message])
      setProposal(nextProposal)
      const combinedInstruction = previousProposal != null && previousInstruction
        ? `${previousInstruction}\n추가 요구: ${content}`
        : content
      const nextInstruction = response.proposal == null ? previousInstruction : combinedInstruction
      const nextTarget = response.proposal == null ? previousTarget : requestTarget
      const nextBaseVersion = response.proposal == null ? pendingBaseVersion : activeVersion
      const nextBeforeContent = response.proposal == null ? pendingBeforeContent : body
      setPendingInstruction(nextProposal == null ? null : nextInstruction)
      setPendingTarget(nextProposal == null ? null : nextTarget)
      setPendingBaseVersion(nextProposal == null ? null : nextBaseVersion)
      setPendingBeforeContent(nextProposal == null ? '' : nextBeforeContent)
      if (nextProposal != null) {
        storeReviewChatProposal(storageRunId, { proposal: nextProposal, instruction: nextInstruction ?? nextProposal.reason, target: nextTarget ?? requestTarget, baseVersion: nextBaseVersion ?? activeVersion, beforeContent: nextBeforeContent, storedAt: new Date().toISOString() })
      } else {
        storeReviewChatProposal(storageRunId, null)
      }
      setDraft((current) => current.trim() === content ? '' : current)
      void reviewMessages.refetch()
      void pendingProposalQuery.refetch()
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }

  const scrollToSection = (target: HTMLElement | null) => {
    target?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  }

  const confirm = async () => {
    if (proposal == null) return
    if (revisionLimitReached) {
      setChatError('v3까지 생성되어 이 수정 초안을 실행할 수 없습니다. 초안을 취소하거나 기존 버전에 관해 질문해 주세요.')
      return
    }
    setChatError(null)
    setContextNotice(null)
    setRevising(true)
    setExecutionState('confirming')
    try {
      const confirmation = await confirmProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { confirmed_by: 'ops-manager', idempotency_key: requestId(`confirm-${proposal.proposal_id}`), expected_proposal_status: 'awaiting_confirmation', expected_review_version: proposal.expected_review_version } })
      const baseVersion = pendingBaseVersion ?? activeVersion
      const baseRevision = revisions.find((revision) => revision.version === baseVersion)
      const baseResult = baseRevision?.result ?? result.data
      if (baseResult == null) throw new Error('선택한 기준 작업지시서 결과를 찾지 못했습니다.')
      const target = pendingTarget ?? detectWorkOrderRevisionTarget(pendingInstruction ?? proposal.reason)
      const instruction = pendingInstruction ?? proposal.reason
      const confirmationIncidentId = confirmation.incident_id ?? activeIncidentId
      let canonicalPayload: unknown = confirmation.document_content
        ?? (confirmation.document != null && typeof confirmation.document.content !== 'undefined' ? confirmation.document.content : confirmation.document)
      let canonical = canonicalDocument(canonicalPayload)
      if (confirmation.document_version != null && canonical.body == null && confirmationIncidentId != null) {
        try {
          const documents = await incidentDocumentsApi.list(confirmationIncidentId)
          const savedDocument = documents.items.find((document) => document.document_type === 'work_order' && document.version === confirmation.document_version)
          if (savedDocument != null) {
            canonicalPayload = savedDocument.content
            canonical = canonicalDocument(savedDocument.content)
          }
        } catch {
          // The confirmation is authoritative; the normal query retry restores the document later.
        }
      }
      if (confirmation.document_version != null && canonical.body == null) {
        const proposalDraft = proposal.draft_content?.trim() || proposal.revision?.body?.trim()
        if (proposalDraft) canonicalPayload = { ...proposal.revision, body: proposalDraft }
        else if (proposal.revision != null) canonicalPayload = proposal.revision
        canonical = canonicalDocument(canonicalPayload)
      }
      const documentSaved = confirmation.document_version != null || canonical.body != null
      const nextVersionValue = confirmation.document_version ?? Math.min(3, latestVersion + 1)
      const blockedReason = confirmationBlockReason(confirmation)
      if (blockedReason != null && !documentSaved) {
        setExecutionState('blocked')
        setChatError(blockedReasonMessage(blockedReason))
        setProposal(null)
        setPendingInstruction(null)
        setPendingTarget(null)
        setPendingBaseVersion(null)
        setPendingBeforeContent('')
        storeReviewChatProposal(storageRunId, null)
        return
      }
      if (blockedReason != null) setContextNotice(savedDocumentNotice(nextVersionValue, blockedReason))
      if (confirmationIncidentId != null) {
        setThreadContext((current) => current == null ? current : {
          ...current,
          incident_id: confirmationIncidentId,
          document_version: confirmation.document_version ?? current.document_version,
          document_version_id: confirmation.document_version_id ?? current.document_version_id,
          document_content: canonical.body != null ? { ...(canonical.title ? { title: canonical.title } : {}), body: canonical.body } : current.document_content,
        })
      }
      let revisionResult: OpsAgentResultV4 | null = !documentSaved ? null : {
        ...baseResult,
        run_id: confirmation.child_run_id ?? confirmation.document_version_id ?? baseResult.run_id,
        ...(canonical.title ? { headline: canonical.title } : {}),
      }
      if (revisionResult == null && confirmation.child_run_id != null) {
        setExecutionState('queued')
        const { agentRunsApi } = await import('../../api/backend')
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const status = await agentRunsApi.get(confirmation.child_run_id)
          if (status.status === 'completed') {
            revisionResult = await agentRunsApi.result(confirmation.child_run_id)
            break
          }
          if (status.status === 'failed') throw new Error(status.error ?? 'AI 재실행에 실패했습니다.')
          setExecutionState(status.status === 'queued' ? 'queued' : 'running')
          await new Promise<void>((resolve) => window.setTimeout(resolve, 1_000))
        }
        if (revisionResult == null) throw new Error('AI 재실행 시간이 초과되었습니다.')
      }
      if (revisionResult != null) {
        if (nextVersionValue !== 2 && nextVersionValue !== 3) throw new Error('서버가 지원 범위를 벗어난 문서 버전을 반환했습니다.')
        const mergedResult = canonical.body == null ? mergeOpsAgentResult(baseResult, revisionResult, target) : revisionResult
        const baseRevisionTitle = baseRevision?.title ?? baseServerContentView?.title ?? threadDocument.title ?? baseTitle
        const nextTitle = canonical.title ?? (target.section === 'title' ? revisionResult.headline : baseRevisionTitle)
        const nextRevision: StoredRevision = {
          version: nextVersionValue,
          title: nextTitle,
          result: mergedResult,
          ...(canonical.body ? { content: canonical.body } : {}),
          ...(confirmation.child_run_id ? { runId: confirmation.child_run_id } : {}),
          ...(confirmation.document_version_id ? { documentVersionId: confirmation.document_version_id } : {}),
          documentVersion: nextVersionValue,
          ...(confirmationIncidentId ? { incidentId: confirmationIncidentId } : {}),
          instruction,
          target,
          createdAt: new Date().toISOString(),
        }
        const nextRevisions = [...revisions.filter((revision) => revision.version !== nextVersionValue), nextRevision].sort((left, right) => left.version - right.version)
        storeRevisions(storageRunId, nextRevisions)
        setRevisions(nextRevisions)
        setSelectedVersion(nextVersionValue)
        setExecutionState('completed')
      } else if (proposal.next_action === 'targeted_rerun' && !documentSaved) {
        setExecutionState('blocked')
        setChatError('서버가 새 문서 버전을 만들지 못했습니다. 실행 입력과 재실행 제한 상태를 확인해 주세요.')
      } else {
        setExecutionState('completed')
      }
      setProposal(null)
      setPendingInstruction(null)
      setPendingTarget(null)
      setPendingBaseVersion(null)
      setPendingBeforeContent('')
      storeReviewChatProposal(storageRunId, null)
      const completionMessage = blockedReason != null && documentSaved
        ? savedDocumentNotice(nextVersionValue, blockedReason)
        : revisionResult == null
          ? '실행 검토 의견을 저장했습니다. 문서 내용은 변경되지 않았습니다.'
          : `v${baseVersion} 기준으로 ${target.label}을 수정한 v${nextVersionValue}을 만들었습니다.`
      setLocalMessages((current) => {
        const nextSequence = Math.max(0, ...messages.map((message) => message.sequence), ...current.map((message) => message.sequence)) + 1
        return [...current, { message_id: `confirmation-${Date.now()}`, thread_id: proposal.thread_id, sequence: nextSequence, role: 'system_event', message_kind: 'execution_result', content: completionMessage, structured_payload: {}, citations: [], context_hash: proposal.context_hash, created_at: new Date().toISOString() }]
      })
      void reviewMessages.refetch()
      void pendingProposalQuery.refetch()
      if (confirmationIncidentId) void incidentDocuments.refetch()
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
      setExecutionState('failed')
    } finally {
      setRevising(false)
    }
  }

  const cancel = async () => {
    if (proposal == null) return
    setChatError(null)
    try {
      await cancelProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { cancelled_by: 'ops-manager', idempotency_key: requestId(`cancel-${proposal.proposal_id}`) } })
      setProposal(null)
      setPendingInstruction(null)
      setPendingTarget(null)
      setPendingBaseVersion(null)
      setPendingBeforeContent('')
      setExecutionState('idle')
      storeReviewChatProposal(storageRunId, null)
      void pendingProposalQuery.refetch()
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const beginManualEdit = () => {
    if (!selectedIsLatest) {
      setChatError('직접 편집은 최신 문서 버전에서만 시작할 수 있습니다.')
      return
    }
    if (activeIncidentId == null || activeDocumentVersion == null) {
      setChatError('서버 작업지시서 연결을 찾지 못해 직접 편집을 시작할 수 없습니다.')
      return
    }
    setChatError(null)
    setManualTitle(title)
    setManualBody(body)
    setManualNote('운영자 직접 편집')
    setManualEditing(true)
    scrollToSection(documentSectionRef.current)
  }

  const saveManualEdit = async () => {
    if (activeIncidentId == null || activeDocumentVersion == null || activeResult == null || !selectedIsLatest) return
    const nextTitle = manualTitle.trim()
    const nextBody = manualBody.trim()
    if (!nextTitle || !nextBody) {
      setChatError('제목과 본문을 모두 입력해 주세요.')
      return
    }
    if (activeDocumentApproved && !await askConfirm(`승인된 v${activeVersion}은 그대로 보존하고, 편집 내용을 새 초안 버전으로 만들까요?\n새 버전은 다시 승인해야 하며 기존 보고서가 있다면 재생성이 필요합니다.`)) return
    setChatError(null)
    try {
      if (proposal != null) {
        await cancelProposal.mutateAsync({ proposalId: proposal.proposal_id, body: { cancelled_by: 'ops-manager', idempotency_key: requestId(`manual-edit-cancel-${proposal.proposal_id}`) } })
        setProposal(null)
        setPendingInstruction(null)
        setPendingTarget(null)
        setPendingBaseVersion(null)
        setPendingBeforeContent('')
        storeReviewChatProposal(storageRunId, null)
      }
      const document = await editIncidentWorkOrder.mutateAsync({
        incidentId: activeIncidentId,
        version: activeDocumentVersion,
        body: {
          expected_version: activeDocumentVersion,
          edited_by: 'ops-manager',
          idempotency_key: requestId(`manual-edit-${activeDocumentVersionId ?? activeDocumentVersion}`),
          title: nextTitle,
          body: nextBody,
          note: manualNote.trim() || '운영자 직접 편집',
        },
      })
      const editedContentView = legacyViewOfContent(document.content)
      const nextRevision: StoredRevision = {
        version: document.version,
        title: editedContentView.title,
        result: activeResult,
        content: editedContentView.body,
        documentVersionId: document.document_version_id,
        documentVersion: document.version,
        incidentId: document.episode_id,
        approved: false,
        instruction: manualNote.trim() || '운영자 직접 편집',
        target: detectWorkOrderRevisionTarget('작업지시서 전체 수정'),
        createdAt: document.created_at,
      }
      const nextRevisions = [...revisions.filter((revision) => revision.version !== document.version), nextRevision]
        .sort((left, right) => left.version - right.version)
      storeRevisions(storageRunId, nextRevisions)
      setRevisions(nextRevisions)
      setSelectedVersion(document.version)
      setThreadContext((current) => current == null ? current : {
        ...current,
        incident_id: document.episode_id,
        document_version: document.version,
        document_version_id: document.document_version_id,
        document_content: { title: editedContentView.title, body: editedContentView.body, actions: [...editedContentView.actions], evidence: [...editedContentView.evidence], safety_notes: editedContentView.safety_notes },
      })
      setManualEditing(false)
      setContextNotice(`운영자 편집본을 v${document.version} 새 초안으로 저장했습니다. AI 검토 후 운영자 재승인이 필요합니다.`)
      void incidentDocuments.refetch()
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const approveSelectedDocument = async () => {
    if (activeIncidentId == null || activeDocumentVersion == null) return
    if (!await askConfirm(`작업지시서 v${activeVersion}을 현장 조치 기준 문서로 최종 승인할까요?`)) return
    setChatError(null)
    try {
      await approveIncidentWorkOrder.mutateAsync({
        incidentId: activeIncidentId,
        body: {
          expected_version: activeDocumentVersion,
          approved_by: 'ops-manager',
          idempotency_key: requestId(`approve-document-${activeDocumentVersionId ?? activeDocumentVersion}`),
          note: `작업지시서 v${activeVersion} 운영자 최종 승인`,
        },
      })
      setRevisions((current) => {
        const next = current.map((revision) => revision.version === activeVersion ? { ...revision, approved: true } : revision)
        storeRevisions(storageRunId, next)
        return next
      })
      void incidentDocuments.refetch()
    } catch (error: unknown) {
      setChatError(chatErrorMessage(error))
    }
  }

  const preview = mode === 'preview'
  return <>
  {confirmDialog}
  <SurfaceCard action={<Button aria-label={preview ? '미리보기 닫기' : '상세 닫기'} icon="x" onClick={onClose} />} className={`activity-detail${preview ? '' : ' activity-detail-with-footer'}`} title={preview ? '작업지시서 미리보기' : '작업지시서 상세'}>
    <div className="detail-body work-order-detail-body">
      <div className="detail-title"><StatusBadge tone={reviewStatusTone(item.operator_review_status)}>{workOrderStatusLabel(item.operator_review_status)}</StatusBadge><h2>{title}</h2><p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p><span>생성 {formatDateTime(item.created_at)}</span></div>
      {!preview && activeResult && <nav aria-label="작업지시서 상세 바로가기" className="work-order-section-nav"><Button onClick={() => scrollToSection(documentSectionRef.current)}>문서 본문</Button><Button disabled={manualEditing || !selectedIsLatest || activeIncidentId == null || activeDocumentVersion == null} icon="document" onClick={beginManualEdit}>직접 수정</Button><Button icon="activity" onClick={() => scrollToSection(chatSectionRef.current)} tone="primary">AI 수정·질문</Button></nav>}
      <ApiState empty={false} error={result.isError && !resultNotReady} loading={result.isLoading} retry={() => void result.refetch()} />
      {resultNotReady && <p className="activity-empty-note">실행이 완료되면 작업지시서 본문을 준비합니다.</p>}
      {preview && activeResult && <section className="work-order-preview"><h3>조치 요약</h3><ol>{previewActions.map((action, index) => <li key={`${index}-${action}`}><b>{index + 1})</b><span>{action}</span></li>)}</ol><Button icon="arrow" onClick={onOpenDetail} tone="primary">상세 보기</Button></section>}
      {!preview && activeResult && <>
        <article className="work-order-document" ref={documentSectionRef}>
          <header><div><small>현장 작업지시서</small><h3>{manualEditing ? manualTitle || '제목 입력 중' : title}</h3></div><StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge></header>
          {revisions.length > 0 && <div aria-label="작업지시서 버전" className="scenario-version-switch" role="tablist">
            {[1, ...revisions.map((revision) => revision.version)].map((version) => <button aria-selected={version === activeVersion} className={version === activeVersion ? 'active' : ''} key={version} onClick={() => setSelectedVersion(version)} role="tab" type="button">v{version}</button>)}
          </div>}
          <dl><div><dt>문서번호</dt><dd>{number}</dd></div><div><dt>대상 설비</dt><dd>{facilityName(item.substation_id, item.manufacturer_id)}</dd></div><div><dt>생성 시각</dt><dd>{formatDateTime(activeRevision?.createdAt ?? item.created_at)}</dd></div><div><dt>문서 버전</dt><dd>v{activeVersion}</dd></div></dl>
          {manualEditing ? <div className="work-order-manual-editor"><p className="work-order-chat-context-note">현재 v{activeVersion}은 그대로 보존되고, 저장 시 v{activeDocumentVersion == null ? '-' : activeDocumentVersion + 1} 새 초안이 생성됩니다. 새 버전은 AI 검토와 운영자 재승인이 필요합니다.</p><label><span>문서 제목</span><input onChange={(event) => setManualTitle(event.target.value)} value={manualTitle} /></label><label><span>작업지시서 본문</span><textarea className="scenario-document-editor" onChange={(event) => setManualBody(event.target.value)} value={manualBody} /></label><label><span>수정 사유</span><input onChange={(event) => setManualNote(event.target.value)} placeholder="예: 현장 점검 결과 반영" value={manualNote} /></label><div><Button disabled={editIncidentWorkOrder.isPending} onClick={() => setManualEditing(false)}>취소</Button><Button disabled={editIncidentWorkOrder.isPending || !manualTitle.trim() || !manualBody.trim()} icon="check" onClick={() => void saveManualEdit()} tone="primary">{editIncidentWorkOrder.isPending ? '새 버전 저장 중' : '새 버전으로 저장'}</Button></div></div> : <pre className="activity-report-body report-single-body">{body}</pre>}
          {!manualEditing && activeStructuredContent && activeIncidentId != null && (
            <WorkOrderStructuredPanel content={activeStructuredContent} incidentId={activeIncidentId} version={activeVersion} />
          )}
        </article>
        <section className="work-order-review-chat" aria-label="AI 수정 챗봇" ref={chatSectionRef}>
          <header><div><h3>AI 문서 검토 챗봇</h3><p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'} 작업지시서 전용 대화입니다. 선택한 v{activeVersion}을 문맥으로 사용하며 문서 수정은 v3까지 가능합니다.</p></div><StatusBadge tone={revisionLimitReached ? 'neutral' : 'primary'}>수정 {rerunsRemaining}회 남음</StatusBadge></header>
          <div aria-busy={chatHistoryLoading} aria-live="polite" className="work-order-chat-log" ref={chatLogRef}>{chatHistoryLoading ? <p>이 작업지시서의 대화 기록을 불러오는 중입니다.</p> : messages.length === 0 ? <p>AI 검토 대화가 아직 없습니다.</p> : messages.map((chatMessage) => <p className={chatMessage.role} key={chatMessage.message_id}><strong>{chatMessage.role === 'operator' ? '운영자' : chatMessage.role === 'assistant' ? 'AI' : '시스템'}</strong>{visibleMessageContent(chatMessage)}</p>)}</div>
          {proposal && previewData && <div className="work-order-chat-proposal"><header><div><span>확정 전 수정 초안</span><strong>{pendingTarget?.label ?? '작업지시서 전체'}</strong></div><StatusBadge tone="warning">v{pendingBaseVersion ?? activeVersion} → v{Math.min(3, latestVersion + 1)}</StatusBadge></header>{pendingRequirements.length > 0 && <section className="work-order-proposal-requirements"><b>현재 반영할 요구사항</b><ol>{pendingRequirements.map((requirement, index) => <li key={`${index}-${requirement}`}>{requirement.replace(/^추가 요구:\s*/, '')}</li>)}</ol></section>}<p>{previewData.changeSummary}</p><div className="work-order-proposal-diff"><section><b>수정 전</b><pre>{previewData.before || '비교할 기존 문구가 없습니다.'}</pre></section>{previewData.after && <section><b>{previewData.afterLabel}</b><pre>{previewData.after}</pre></section>}</div>{!previewData.after && <p className="work-order-proposal-note">서버가 문안 초안을 제공하지 않아 변경 요약만 표시합니다. 확정 시 선택한 버전을 기준으로 새 문서를 생성합니다.</p>}<dl><div><dt>기준 버전</dt><dd>v{pendingBaseVersion ?? activeVersion}</dd></div><div><dt>유지 범위</dt><dd>{pendingTarget?.section === 'document' ? '전체 문서 재작성' : '지정 부분 외 유지'}</dd></div><div><dt>생성 버전</dt><dd>v{Math.min(3, latestVersion + 1)}</dd></div></dl><div><Button disabled={confirmProposal.isPending || revising} onClick={() => void cancel()}>초안 취소</Button><Button disabled={confirmProposal.isPending || revising || revisionLimitReached} icon="check" onClick={() => void confirm()} tone="primary">{revising ? '새 버전 생성 중' : `초안 확정 · v${Math.min(3, latestVersion + 1)} 생성`}</Button></div></div>}
          {executionState !== 'idle' && <p className={`work-order-chat-execution ${executionState}`} role="status">{executionStateLabel[executionState]}</p>}
          {contextNotice && <p className="work-order-chat-context-note">{contextNotice}</p>}
          {revisionLimitReached && <p className="work-order-chat-context-note">v3 생성이 완료되었습니다. 문서 수정 요청은 마감되었지만 이전 대화 회상과 문서 질문은 계속할 수 있습니다.</p>}
          <label className="work-order-chat-compose"><span>{proposal ? '추가 요구 또는 수정안 확정' : '문서 질문 또는 수정 요청'}</span><textarea aria-describedby="work-order-chat-input-hint" disabled={reviewThread.isPending || postMessage.isPending || revising} onChange={(event) => setDraft(event.target.value)} onKeyDown={submitOnEnter} placeholder={proposal ? "예: 더 강하게 경고해줘 / 둘 다 반영해줘 / 이대로 확정" : revisionLimitReached ? '예: 내가 요청한 수정 내용이 뭐였지?' : '예: 안전 확인 2번째 항목만 최신 보호구 기준으로 수정해 주세요.'} value={draft} /><small id="work-order-chat-input-hint">{proposal ? '추가 요구를 보내면 기존 초안을 대체하며, “이대로 확정”으로 실행할 수 있습니다.' : 'Enter 전송 · Shift+Enter 줄바꿈'}</small><Button disabled={!draft.trim() || reviewThread.isPending || postMessage.isPending || revising || (revisionLimitReached && draftIsRevision && proposal == null)} onClick={() => void sendMessage()} tone="primary">{reviewThread.isPending || postMessage.isPending ? 'AI 검토 중' : draftConfirmsProposal ? '수정안 확정' : proposal ? '추가 요구 반영' : draftIsRevision ? '수정 초안 요청' : '질문 보내기'}</Button></label>
          {chatError && <p className="form-error" role="alert">{chatError}</p>}
        </section>
      </>}
      {downloadState === 'error' && <p className="scenario-document-error" role="alert">PDF를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.</p>}
    </div>
    {!preview && <div className="activity-detail-footer detail-actions"><Button disabled={!body || downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'PDF 생성 중' : 'PDF 다운로드'}</Button>{activeResult && <>{activeIncidentId != null && activeDocumentVersion != null ? <Button disabled={activeDocumentApproved || !selectedIsLatest || approveIncidentWorkOrder.isPending} icon="check" onClick={() => void approveSelectedDocument()} tone="primary">{activeDocumentApproved ? `v${activeVersion} 최종 승인됨` : !selectedIsLatest ? '최신 버전만 최종 승인 가능' : approveIncidentWorkOrder.isPending ? '문서 승인 중' : `v${activeVersion} 문서 최종 승인`}</Button> : <><Button onClick={() => setReviewDecision('correct')}>실행 교정 기록</Button><Button icon="check" onClick={() => setReviewDecision('approve')} tone="primary">v{activeVersion} 실행 검토 승인</Button></>}</>}</div>}
    {reviewDecision && <ReviewActionModal currentOutput={reviewOutput} decision={reviewDecision} onClose={() => setReviewDecision(null)} runId={activeReviewRunId} />}
  </SurfaceCard>
  </>
}
