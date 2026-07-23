import { useEffect, useRef, useState } from 'react'
import { Icon } from '../console/icons'
import {
  classifyWorkOrderChatIntent,
  isUnsafeWorkOrderChatInput,
  isWorkOrderRevisionRequest,
  workOrderChatNormalizationForms,
} from '../scenario/workOrderRevision'
import { finalTestDemoApi } from './api'
import type {
  FinalTestChatAction,
  FinalTestChatRule,
  FinalTestChatScript,
  FinalTestDocumentType,
} from './contracts'
import { FINAL_TEST_CHAT_STORAGE_KEY } from './session'

interface Props {
  readonly demoId: string
  readonly script: FinalTestChatScript
  readonly sessionKey?: string
  readonly documentType: FinalTestDocumentType
  readonly currentVersion: number
  readonly onPreviewVersion: (version: number) => void
  readonly onApplyVersion: (version: number) => void
  readonly onCancelPreview: () => void
}

type ChatRole = 'assistant' | 'operator' | 'guardrail'
type ActionStatus = 'pending' | 'applied' | 'cancelled'

interface ChatMessage {
  readonly id: number
  readonly role: ChatRole
  readonly content: string
  readonly action?: FinalTestChatAction
  readonly actionStatus?: ActionStatus
}

interface ScriptedReply {
  readonly content: string
  readonly guarded: boolean
  readonly action?: FinalTestChatAction
}

function presentationText(value: string): string {
  return value
    .replaceAll('v1·v2·v3', '원본·수정안·최종안')
    .replace(/\bv[23]\s*변경안/gi, '변경안')
    .replace(/\bv[23]로/gi, '이 변경안으로')
    .replace(/\bv1\b/gi, '원본')
    .replace(/\bv2\b/gi, '수정안')
    .replace(/\bv3\b/gi, '최종안')
    .replaceAll('수정안 변경안', '변경안')
    .replaceAll('최종안 변경안', '변경안')
    .replaceAll('수정안로', '이 변경안으로')
    .replaceAll('최종안로', '이 변경안으로')
    .replaceAll('변경안을 불러왔습니다.', '수정안을 작성했습니다.')
    .replaceAll('이 시연 챗봇', '이 대화')
    .replaceAll('시연 모드의', '현재 화면의')
    .replaceAll('시연 데이터', '운영 데이터')
    .replaceAll('준비 질문', '수정 요청')
    .replaceAll('준비된 문서 변경안', '문서 변경안')
    .replaceAll('최초 사전 승인본', '초기 검토본')
    .replaceAll('사전 승인본', '검토 문서')
    .replaceAll('FINAL TEST', 'HEATGRID OPS')
    .replaceAll('final-test', 'heatgrid-ops')
    .replaceAll('시연', '운영')
}

function isChatAction(value: unknown): value is FinalTestChatAction {
  if (value == null || typeof value !== 'object') return false
  const action = value as Partial<FinalTestChatAction>
  return action.type === 'preview_document_version'
    && (action.document_type === 'work_order' || action.document_type === 'report')
    && typeof action.source_version === 'number'
    && typeof action.target_version === 'number'
    && typeof action.confirmation_message === 'string'
    && typeof action.applied_response === 'string'
    && typeof action.cancelled_response === 'string'
}

function matchesPattern(message: string, pattern: string): boolean {
  const messageForms = workOrderChatNormalizationForms(message)
  const patternForms = workOrderChatNormalizationForms(pattern)
  if (!patternForms.compact) return false
  return messageForms.normalized.includes(patternForms.normalized)
    || messageForms.compact.includes(patternForms.compact)
    || messageForms.skeleton.includes(patternForms.skeleton)
}

function matchesRule(message: string, rules: readonly FinalTestChatRule[]): FinalTestChatRule | null {
  return rules.find((rule) => rule.patterns.some((pattern) => matchesPattern(message, pattern))) ?? null
}

function scriptedReply(message: string, script: FinalTestChatScript): ScriptedReply | null {
  const guardrail = matchesRule(message, script.guardrails)
  if (guardrail) return { content: guardrail.response, guarded: true }

  const unsafe = isUnsafeWorkOrderChatInput(message)
  if (unsafe) {
    return {
      content: '안전 절차 우회, 업무 외 내용 변경, 프롬프트 공격 또는 실행 코드가 포함된 요청은 처리할 수 없습니다.',
      guarded: true,
    }
  }

  const response = matchesRule(message, script.responses)
  if (response) return { content: response.response, guarded: false, action: response.action }

  if (isWorkOrderRevisionRequest(message)) return null

  const intent = classifyWorkOrderChatIntent(message)
  if (intent === 'out_of_scope' || intent === 'ambiguous') {
    return { content: script.fallback_response, guarded: false }
  }
  return null
}

function defaultMessages(greeting: string): readonly ChatMessage[] {
  return [{ id: 1, role: 'assistant', content: presentationText(greeting) }]
}

function loadMessages(sessionKey: string, greeting: string): readonly ChatMessage[] {
  try {
    const stored: unknown = JSON.parse(window.sessionStorage.getItem(FINAL_TEST_CHAT_STORAGE_KEY) ?? '{}')
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return defaultMessages(greeting)
    const messages = (stored as Record<string, unknown>)[sessionKey]
    if (!Array.isArray(messages) || messages.length === 0) return defaultMessages(greeting)
    const valid = messages.filter((message): message is ChatMessage => {
      if (typeof message !== 'object' || message == null) return false
      const candidate = message as Partial<ChatMessage>
      if (typeof candidate.id !== 'number' || typeof candidate.content !== 'string') return false
      if (candidate.role == null || !['assistant', 'operator', 'guardrail'].includes(candidate.role)) return false
      if (candidate.action != null && !isChatAction(candidate.action)) return false
      return candidate.actionStatus == null || ['pending', 'applied', 'cancelled'].includes(candidate.actionStatus)
    })
    if (valid.length === 0) return defaultMessages(greeting)
    return valid.map((message, index) => message.role === 'operator'
      ? message
      : { ...message, content: presentationText(index === 0 ? greeting : message.content) })
  } catch {
    return defaultMessages(greeting)
  }
}

function persistMessages(sessionKey: string, messages: readonly ChatMessage[]): void {
  try {
    const stored: unknown = JSON.parse(window.sessionStorage.getItem(FINAL_TEST_CHAT_STORAGE_KEY) ?? '{}')
    const next = stored && typeof stored === 'object' && !Array.isArray(stored)
      ? { ...(stored as Record<string, unknown>), [sessionKey]: messages }
      : { [sessionKey]: messages }
    window.sessionStorage.setItem(FINAL_TEST_CHAT_STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Chat remains usable when sessionStorage is unavailable.
  }
}

function documentLabel(type: FinalTestDocumentType): string {
  return type === 'work_order' ? '작업지시서' : '보고서'
}

function actionPreviewMessage(type: FinalTestDocumentType): string {
  return `요청하신 내용을 반영해 ${documentLabel(type)} 수정안을 작성했습니다.\n\n변경 내용을 확인한 뒤 적용하시겠습니까?`
}

export function FinalTestProjectChat({
  demoId,
  script,
  sessionKey = 'default',
  documentType,
  currentVersion,
  onPreviewVersion,
  onApplyVersion,
  onCancelPreview,
}: Props) {
  const [messages, setMessages] = useState<readonly ChatMessage[]>(() => loadMessages(sessionKey, script.greeting))
  const [draft, setDraft] = useState('')
  const [composing, setComposing] = useState(false)
  const [pending, setPending] = useState(false)
  const nextId = useRef(Math.max(1, ...messages.map((message) => message.id)) + 1)
  const transcript = useRef<HTMLDivElement>(null)
  useEffect(() => {
    persistMessages(sessionKey, messages)
  }, [messages, sessionKey])

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [messages])

  const submit = async (content = draft) => {
    const value = content.trim()
    if (!value || pending) return
    const reply = scriptedReply(value, script)
    const operatorId = nextId.current++
    setDraft('')

    if (reply == null) {
      setMessages((current) => [...current, { id: operatorId, role: 'operator', content: value }])
      setPending(true)
      try {
        const history = messages
          .filter((message) => message.role === 'operator' || message.role === 'assistant')
          .slice(-12)
          .map((message) => ({
            role: message.role === 'operator' ? 'operator' as const : 'assistant' as const,
            content: message.content,
          }))
        const response = await finalTestDemoApi.chat(demoId, {
          message: value,
          document_type: documentType,
          current_version: currentVersion,
          history,
        })
        setMessages((current) => [
          ...current,
          { id: nextId.current++, role: 'assistant', content: presentationText(response.answer || script.fallback_response) },
        ])
      } catch {
        setMessages((current) => [
          ...current,
          { id: nextId.current++, role: 'assistant', content: presentationText(script.fallback_response) },
        ])
      } finally {
        setPending(false)
      }
      return
    }

    let replyContent = reply.content
    let pendingAction = reply.action

    if (pendingAction != null && pendingAction.document_type !== documentType) {
      replyContent = `${documentLabel(pendingAction.document_type)} 화면에서 해당 수정 요청을 입력해 주세요.`
      pendingAction = undefined
    } else if (pendingAction != null && currentVersion >= pendingAction.target_version) {
      replyContent = `${documentLabel(documentType)}에 해당 변경이 이미 적용되어 있습니다.`
      pendingAction = undefined
    } else if (pendingAction != null && currentVersion !== pendingAction.source_version) {
      replyContent = `먼저 ${documentLabel(documentType)}의 이전 변경안을 적용한 뒤 다음 수정을 요청해 주세요.`
      pendingAction = undefined
    }

    const assistantId = nextId.current++
    if (pendingAction != null) onPreviewVersion(pendingAction.target_version)
    setMessages((current) => [
      ...current,
      { id: operatorId, role: 'operator', content: value },
      {
        id: assistantId,
        role: reply.guarded ? 'guardrail' : 'assistant',
        content: presentationText(pendingAction == null ? replyContent : actionPreviewMessage(pendingAction.document_type)),
        action: pendingAction,
        actionStatus: pendingAction == null ? undefined : 'pending',
      },
    ])
  }

  const decideAction = (message: ChatMessage, apply: boolean) => {
    if (message.action == null || message.actionStatus !== 'pending') return
    const response = presentationText(apply ? message.action.applied_response : message.action.cancelled_response)
    if (apply) onApplyVersion(message.action.target_version)
    else onCancelPreview()
    setMessages((current) => [
      ...current.map((item) => item.id === message.id
        ? { ...item, actionStatus: apply ? 'applied' as const : 'cancelled' as const }
        : item),
      { id: nextId.current++, role: 'assistant', content: response },
    ])
  }

  return <section className="final-test-chat" aria-label="HeatGrid 프로젝트 챗봇">
    <header className="final-test-chat-header">
      <div className="final-test-chat-avatar"><Icon name="activity" /></div>
      <div><strong>HeatGrid 운영 도우미</strong><span><i /> 운영 자료 연계 · AI 답변</span></div>
      <span className="final-test-domain-badge">현재 기계실</span>
    </header>
    <div className="final-test-chat-log" ref={transcript} role="log" aria-live="polite">
      {messages.map((message) => <div className={`final-test-message ${message.role}`} key={message.id}>
        {message.role !== 'operator' && <span className="final-test-message-avatar"><Icon name={message.role === 'guardrail' ? 'shield' : 'activity'} /></span>}
        <div>
          <small>{message.role === 'operator' ? '운영자' : message.role === 'guardrail' ? '안전 가드레일' : 'HeatGrid AI'}</small>
          <p>{message.content}</p>
          {message.action != null && message.action.document_type === documentType && message.actionStatus === 'pending' && <div className="final-test-action-confirmation">
            <button onClick={() => decideAction(message, true)} type="button">변경안 적용</button>
            <button onClick={() => decideAction(message, false)} type="button">취소</button>
          </div>}
          {message.actionStatus === 'applied' && <span className="final-test-action-status is-applied">변경 적용됨</span>}
          {message.actionStatus === 'cancelled' && <span className="final-test-action-status">변경 취소됨</span>}
        </div>
      </div>)}
      {pending && <div className="final-test-message assistant is-pending">
        <span className="final-test-message-avatar"><Icon name="activity" /></span>
        <div><small>HeatGrid AI</small><p>현재 기계실 자료에서 답변을 확인하고 있습니다.</p></div>
      </div>}
    </div>
    <div className="final-test-composer">
      <textarea
        aria-label="HeatGrid 질문 입력"
        onChange={(event) => setDraft(event.target.value)}
        onCompositionEnd={() => setComposing(false)}
        onCompositionStart={() => setComposing(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !composing) {
            event.preventDefault()
            void submit()
          }
        }}
        placeholder="센서, 위험, 작업지시서, 보고서를 질문하세요"
        rows={2}
        value={draft}
      />
      <button aria-label="질문 보내기" disabled={!draft.trim() || pending} onClick={() => void submit()} type="button"><Icon name="arrow" /></button>
      <p>현재 기계실 운영 자료만 답변합니다. Enter 전송 · Shift+Enter 줄바꿈</p>
    </div>
  </section>
}
