import { useEffect, useState, type KeyboardEvent } from 'react'
import type { AnomalyReportArtifact, ReportReviewMessage } from '../../api/contracts'
import { reportDocumentsApi } from '../../api/backend'
import { Button, StatusBadge } from '../ui'

interface Props {
  readonly contextLabel: string
  readonly reportContext: AnomalyReportArtifact | string
  readonly storageKey: string
}

function loadMessages(key: string): readonly ReportReviewMessage[] {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(key) ?? '[]') as unknown
    return Array.isArray(parsed) ? parsed.filter((item): item is ReportReviewMessage => item != null && typeof item === 'object' && ((item as ReportReviewMessage).role === 'operator' || (item as ReportReviewMessage).role === 'assistant') && typeof (item as ReportReviewMessage).content === 'string') : []
  } catch {
    return []
  }
}

export function ReportReviewChat({ contextLabel, reportContext, storageKey }: Props) {
  const key = `heatgrid:report-review:${storageKey}`
  const [messages, setMessages] = useState<readonly ReportReviewMessage[]>(() => loadMessages(key))
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => setMessages(loadMessages(key)), [key])

  const send = async () => {
    const content = draft.trim()
    if (!content || pending != null) return
    setDraft('')
    setPending(content)
    setError(null)
    try {
      const response = await reportDocumentsApi.review({ message: content, report_context: reportContext, history: messages })
      const next: readonly ReportReviewMessage[] = [...messages, { role: 'operator', content }, { role: 'assistant', content: response.answer }]
      setMessages(next)
      sessionStorage.setItem(key, JSON.stringify(next))
    } catch {
      setError('보고서 검토 답변을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setPending(null)
    }
  }
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void send()
  }

  return <div className="work-order-review-chat report-review-chat">
    <header><div><h3>AI 보고서 검토 챗봇</h3><p>{contextLabel}</p></div><StatusBadge tone="primary">보고서 전용</StatusBadge></header>
    <div aria-busy={pending != null} aria-live="polite" className="work-order-chat-log">
      {messages.length === 0 && pending == null && <p>검토 대화가 아직 없습니다.</p>}
      {messages.map((message, index) => <article className={`work-order-chat-message ${message.role}`} key={`${index}-${message.content.slice(0, 20)}`}><strong>{message.role === 'operator' ? '운영자' : 'AI 검토'}</strong><span>{message.content}</span></article>)}
      {pending != null && <><article className="work-order-chat-message operator is-pending"><strong>운영자</strong><span>{pending}</span></article><article aria-label="AI가 답변을 준비 중" className="work-order-chat-message assistant is-thinking"><strong>AI 검토</strong><span className="work-order-thinking-dots"><i /><i /><i /></span><small>보고서와 근거를 확인하고 있습니다.</small></article></>}
    </div>
    <label className="work-order-chat-compose"><span>보고서 질문 또는 검토 요청</span><textarea disabled={pending != null} onChange={(event) => setDraft(event.target.value)} onKeyDown={submitOnEnter} placeholder="예: 관리자 요약에서 근거가 약한 문장을 찾아줘." value={draft} /><small>Enter 전송 · Shift+Enter 줄바꿈</small><Button disabled={!draft.trim() || pending != null} onClick={() => void send()} tone="primary">{pending != null ? '검토 중' : '질문 보내기'}</Button></label>
    {error && <p className="form-error" role="alert">{error}</p>}
  </div>
}
