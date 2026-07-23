import { useEffect, useRef, useState } from 'react'
import { Icon } from '../console/icons'
import type { FinalTestChatRule, FinalTestChatScript } from './contracts'
import { FINAL_TEST_CHAT_STORAGE_KEY } from './session'

interface Props {
  readonly script: FinalTestChatScript
  readonly sessionKey?: string
}

interface ChatMessage {
  readonly id: number
  readonly role: 'assistant' | 'operator' | 'guardrail'
  readonly content: string
}

function matchesRule(message: string, rules: readonly FinalTestChatRule[]): FinalTestChatRule | null {
  const normalized = message.trim().toLocaleLowerCase('ko-KR')
  return rules.find((rule) => rule.patterns.some((pattern) => normalized.includes(pattern.toLocaleLowerCase('ko-KR')))) ?? null
}

function scriptedReply(message: string, script: FinalTestChatScript): { readonly content: string; readonly guarded: boolean } {
  const guardrail = matchesRule(message, script.guardrails)
  if (guardrail) return { content: guardrail.response, guarded: true }
  const response = matchesRule(message, script.responses)
  return { content: response?.response ?? script.fallback_response, guarded: false }
}

function loadMessages(sessionKey: string, greeting: string): readonly ChatMessage[] {
  try {
    const stored: unknown = JSON.parse(window.sessionStorage.getItem(FINAL_TEST_CHAT_STORAGE_KEY) ?? '{}')
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return [{ id: 1, role: 'assistant', content: greeting }]
    const messages = (stored as Record<string, unknown>)[sessionKey]
    if (!Array.isArray(messages) || messages.length === 0) return [{ id: 1, role: 'assistant', content: greeting }]
    return messages.filter((message): message is ChatMessage => (
      typeof message === 'object'
      && message != null
      && typeof (message as ChatMessage).id === 'number'
      && (message as ChatMessage).role !== undefined
      && ['assistant', 'operator', 'guardrail'].includes((message as ChatMessage).role)
      && typeof (message as ChatMessage).content === 'string'
    ))
  } catch {
    return [{ id: 1, role: 'assistant', content: greeting }]
  }
}

function persistMessages(sessionKey: string, messages: readonly ChatMessage[]): void {
  try {
    const stored: unknown = JSON.parse(window.sessionStorage.getItem(FINAL_TEST_CHAT_STORAGE_KEY) ?? '{}')
    const next = stored && typeof stored === 'object' && !Array.isArray(stored) ? { ...(stored as Record<string, unknown>), [sessionKey]: messages } : { [sessionKey]: messages }
    window.sessionStorage.setItem(FINAL_TEST_CHAT_STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Chat remains usable when sessionStorage is unavailable.
  }
}

export function FinalTestProjectChat({ script, sessionKey = 'default' }: Props) {
  const [messages, setMessages] = useState<readonly ChatMessage[]>(() => loadMessages(sessionKey, script.greeting))
  const [draft, setDraft] = useState('')
  const [composing, setComposing] = useState(false)
  const nextId = useRef(Math.max(1, ...messages.map((message) => message.id)) + 1)
  const transcript = useRef<HTMLDivElement>(null)

  useEffect(() => {
    persistMessages(sessionKey, messages)
  }, [messages, sessionKey])

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [messages])

  const submit = (content = draft) => {
    const value = content.trim()
    if (!value) return
    const reply = scriptedReply(value, script)
    const operatorId = nextId.current++
    const assistantId = nextId.current++
    setMessages((current) => [
      ...current,
      { id: operatorId, role: 'operator', content: value },
      { id: assistantId, role: reply.guarded ? 'guardrail' : 'assistant', content: reply.content },
    ])
    setDraft('')
  }

  return <section className="final-test-chat" aria-label="HeatGrid 프로젝트 챗봇">
    <header className="final-test-chat-header">
      <div className="final-test-chat-avatar"><Icon name="activity" /></div>
      <div><strong>HeatGrid 운영 도우미</strong><span><i /> 사전 대본 응답 · 모델 호출 없음</span></div>
      <span className="final-test-domain-badge">프로젝트 전용</span>
    </header>
    <div className="final-test-chat-log" ref={transcript} role="log" aria-live="polite">
      {messages.map((message) => <div className={`final-test-message ${message.role}`} key={message.id}>
        {message.role !== 'operator' && <span className="final-test-message-avatar"><Icon name={message.role === 'guardrail' ? 'shield' : 'activity'} /></span>}
        <div><small>{message.role === 'operator' ? '운영자' : message.role === 'guardrail' ? '안전 가드레일' : 'HeatGrid AI'}</small><p>{message.content}</p></div>
      </div>)}
    </div>
    <div className="final-test-suggestions" aria-label="추천 질문">{script.suggested_prompts.map((prompt) => <button key={prompt} onClick={() => submit(prompt)} type="button">{prompt}</button>)}</div>
    <div className="final-test-composer">
      <textarea
        aria-label="HeatGrid 질문 입력"
        onChange={(event) => setDraft(event.target.value)}
        onCompositionEnd={() => setComposing(false)}
        onCompositionStart={() => setComposing(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !composing) {
            event.preventDefault()
            submit()
          }
        }}
        placeholder="센서, 위험, 작업지시서, 보고서를 질문하세요"
        rows={2}
        value={draft}
      />
      <button aria-label="질문 보내기" disabled={!draft.trim()} onClick={() => submit()} type="button"><Icon name="arrow" /></button>
      <p>HeatGrid 시연 데이터만 답변합니다. Enter 전송 · Shift+Enter 줄바꿈</p>
    </div>
  </section>
}
