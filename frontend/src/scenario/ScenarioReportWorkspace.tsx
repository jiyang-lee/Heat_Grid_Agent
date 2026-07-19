import { useEffect, useState, type KeyboardEvent } from 'react'
import { ApiError } from '../api/client'
import { usePostReviewChatMessage, useReviewChatThreadOpen } from '../api/hooks'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { downloadDocumentPdf, safeFilePart } from './documentPdf'
import type { ScenarioAlert, ScenarioReport, ScenarioReportMessage, WorkOrderVersion } from './types'

interface Props {
  readonly alert: ScenarioAlert
  readonly runId: string | null
  readonly messages: readonly ScenarioReportMessage[]
  readonly order: WorkOrderVersion | undefined
  readonly report: ScenarioReport
  readonly onComplete: () => void
  readonly onCreateDraft: () => void
  readonly onPostMessage: (content: string) => void
  readonly onSave: (content: string) => void
}

function reportDate(alert: ScenarioAlert): string {
  const date = new Date(alert.detectedAt)
  if (Number.isNaN(date.getTime())) return '2020-01-13'
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function ScenarioReportWorkspace({ alert, runId, messages, order, report, onComplete, onCreateDraft, onPostMessage, onSave }: Props) {
  const [draft, setDraft] = useState(report.content)
  const [message, setMessage] = useState('')
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const reviewThread = useReviewChatThreadOpen()
  const postMessage = usePostReviewChatMessage()
  useEffect(() => setDraft(report.content), [report.content])

  if (!order) return <SurfaceCard title="보고서 상세"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 채택 대기</StatusBadge><p>작업지시서 v1-v3 중 하나를 최종 채택한 뒤 보고서를 생성할 수 있습니다.</p></div></SurfaceCard>
  if (report.status === 'idle') return <SurfaceCard title="보고서 상세"><div className="scenario-report-empty"><StatusBadge tone="neutral">보고서 미생성</StatusBadge><p>최종 채택한 작업지시서 v{order.version}을 기준으로 공문서형 보고서 초안을 생성합니다.</p><Button icon="document" onClick={onCreateDraft} tone="primary">보고서 생성</Button></div></SurfaceCard>

  const title = `${alert.title} ${alert.facility} 조치 결과 보고서`
  const sendMessage = async () => {
    if (!message.trim()) return
    setApiError(null)
    try {
      if (runId != null) {
        let activeThreadId = threadId
        if (activeThreadId == null) {
          const thread = await reviewThread.mutateAsync({ runId, created_by: 'ops-manager', idempotency_key: requestId(`report-thread-${runId}`) })
          activeThreadId = thread.thread_id
          setThreadId(activeThreadId)
        }
        await postMessage.mutateAsync({ threadId: activeThreadId, body: { content: message.trim(), created_by: 'ops-manager', idempotency_key: requestId(`report-message-${runId}`) } })
      }
      onPostMessage(message)
      setMessage('')
    } catch (error: unknown) {
      setApiError(error instanceof ApiError && error.status === 409 ? '다른 검토 변경과 충돌했습니다. 보고서 본문과 질문은 유지됩니다.' : '참고 의견을 불러오지 못했습니다. 질문 내용은 유지됩니다.')
    }
  }
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }
  const complete = () => {
    onSave(draft)
    if (!window.confirm('현재 보고서 본문을 완료 처리할까요?\n완료 후에는 PDF 저장만 가능합니다.')) return
    onComplete()
  }
  const download = async () => {
    setDownloadState('working')
    try {
      await downloadDocumentPdf({
        title,
        fileName: `heatgrid-report-${safeFilePart(alert.title)}-${safeFilePart(alert.facility)}-${reportDate(alert)}.pdf`,
        metadata: [`대상 설비 ${alert.facility}`, `기준 작업지시서 v${order.version}`, `완료 ${report.completedAt ? new Date(report.completedAt).toLocaleString('ko-KR') : '-'}`],
        content: report.content,
      })
      setDownloadState('idle')
    } catch {
      setDownloadState('error')
    }
  }

  return <div className="scenario-document-workspace scenario-report-workspace">
    <SurfaceCard action={<StatusBadge tone={report.status === 'completed' ? 'success' : 'notice'}>{report.status === 'completed' ? '완료' : '초안'}</StatusBadge>} className="scenario-report-card" title="보고서 상세">
      <article className="scenario-report-document">
        <header><div><span>사고 조치 결과 보고서</span><h2>{title}</h2></div><span>{reportDate(alert)}</span></header>
        <dl className="scenario-report-meta"><div><dt>대상 설비</dt><dd>{alert.facility}</dd></div><div><dt>기준 문서</dt><dd>작업지시서 v{order.version}</dd></div><div><dt>상태</dt><dd>{report.status === 'completed' ? '완료' : '운영자 편집 중'}</dd></div></dl>
        {report.status === 'draft' ? <textarea aria-label="보고서 본문 편집" className="scenario-document-editor scenario-report-editor" onChange={(event) => setDraft(event.target.value)} value={draft} /> : <pre className="scenario-document-content scenario-report-content">{report.content}</pre>}
        {downloadState === 'error' && <p className="scenario-document-error" role="alert">PDF를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.</p>}
        <footer className="scenario-report-actions">
          {report.status === 'draft' && <><Button icon="document" onClick={() => onSave(draft)}>임시 저장</Button><Button icon="check" onClick={complete} tone="primary">완료</Button></>}
          <Button disabled={report.status !== 'completed' || downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'PDF 생성 중' : 'PDF 저장'}</Button>
          {report.savedAt && <span>마지막 저장 {new Date(report.savedAt).toLocaleString('ko-KR')}</span>}
        </footer>
      </article>
    </SurfaceCard>

    <SurfaceCard action={<StatusBadge tone="neutral">참고 전용</StatusBadge>} className="scenario-chat-card" title="보고서 검토 챗봇">
      <div className="scenario-chat">
        <div className="scenario-chat-source"><StatusBadge tone="neutral">본문 변경 없음</StatusBadge><span>질문과 검토 의견만 제공합니다. 보고서 본문 반영은 왼쪽에서 운영자가 직접 수행합니다.</span></div>
        <div className="scenario-chat-messages">{messages.length === 0 && <p>표현의 명확성, 누락된 확인 항목, 인계 내용 등을 질문할 수 있습니다.</p>}{messages.map((item) => <article className={item.role} key={item.id}><strong>{item.role === 'operator' ? '운영자' : 'AI 참고 의견'}</strong><span>{item.content}</span></article>)}</div>
        <div className="scenario-chat-input"><label htmlFor="scenario-report-chat">검토 질문</label><textarea id="scenario-report-chat" onChange={(event) => setMessage(event.target.value)} onKeyDown={submitOnEnter} placeholder="예: 현장 인계 전에 확인할 항목이 빠졌는지 검토해줘." value={message} /><span>Enter 전송 · Shift+Enter 줄바꿈</span><Button disabled={!message.trim() || reviewThread.isPending || postMessage.isPending} onClick={() => void sendMessage()} tone="primary">{reviewThread.isPending || postMessage.isPending ? '검토 중' : '질문'}</Button></div>
        {apiError && <p className="scenario-analysis-error" role="alert">{apiError}</p>}
      </div>
    </SurfaceCard>
  </div>
}
