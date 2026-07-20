import { useEffect, useState, type KeyboardEvent } from 'react'
import { useConfirmDialog } from '../console/ConfirmDialog'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { downloadDocumentPdf, safeFilePart } from './documentPdf'
import { ScenarioReportRail } from './ScenarioReportRail'
import type { ScenarioAlert, ScenarioDocumentGroup, ScenarioReport, ScenarioReportMessage, WorkOrderVersion } from './types'

interface Props {
  readonly alert: ScenarioAlert
  readonly activeGroupId: string | null
  readonly groups: readonly ScenarioDocumentGroup[]
  readonly messages: readonly ScenarioReportMessage[]
  readonly order: WorkOrderVersion | undefined
  readonly report: ScenarioReport
  readonly onComplete: () => void
  readonly onCreateDraft: () => void
  readonly onOpenWorkOrders: () => void
  readonly onPostMessage: (content: string) => void
  readonly onSave: (content: string) => void
  readonly onSelectDocumentGroup: (groupId: string) => void
}

function reportDate(alert: ScenarioAlert): string {
  const date = new Date(alert.detectedAt)
  if (Number.isNaN(date.getTime())) return '2020-01-13'
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function ScenarioReportWorkspace({ activeGroupId, alert, groups, messages, order, report, onComplete, onCreateDraft, onOpenWorkOrders, onPostMessage, onSave, onSelectDocumentGroup }: Props) {
  const [draft, setDraft] = useState(report.content)
  const [message, setMessage] = useState('')
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const { confirm, dialog: confirmDialog } = useConfirmDialog()
  useEffect(() => setDraft(report.content), [report.content])

  const reportRail = <SurfaceCard className="scenario-version-rail-card" title="보고서 목록"><ScenarioReportRail activeGroupId={activeGroupId} groups={groups} onSelect={onSelectDocumentGroup} /></SurfaceCard>
  if (!order) return <>{confirmDialog}<div className="scenario-report-list-layout">{reportRail}<SurfaceCard title="보고서 상세"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 채택 대기</StatusBadge><p>작업지시서 v1-v3 중 하나를 최종 채택한 뒤 보고서를 생성할 수 있습니다.</p><Button icon="arrow" onClick={onOpenWorkOrders}>작업지시서에서 버전 채택하기</Button></div></SurfaceCard></div></>
  if (report.status === 'idle') return <>{confirmDialog}<div className="scenario-report-list-layout">{reportRail}<SurfaceCard title="보고서 상세"><div className="scenario-report-empty"><StatusBadge tone="neutral">보고서 미생성</StatusBadge><p>최종 채택한 작업지시서 v{order.version}을 기준으로 공문서형 보고서 초안을 생성합니다.</p><Button icon="document" onClick={onCreateDraft} tone="primary">보고서 생성</Button></div></SurfaceCard></div></>

  const title = `${alert.title} ${alert.facility} 조치 결과 보고서`
  const sendMessage = () => {
    const content = message.trim()
    if (!content) return
    onPostMessage(content)
    setMessage((current) => current.trim() === content ? '' : current)
  }
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }
  const complete = async () => {
    if (!await confirm('현재 보고서 본문을 완료 처리할까요?\n완료 후에는 PDF 저장만 가능합니다.')) return
    onSave(draft)
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

  return <>
  {confirmDialog}
  <div className="scenario-report-list-layout">
    {reportRail}
    <div className="scenario-document-workspace scenario-report-workspace">
    <SurfaceCard action={<StatusBadge tone={report.status === 'completed' ? 'success' : 'notice'}>{report.status === 'completed' ? '완료' : '초안'}</StatusBadge>} className="scenario-report-card" title="보고서 상세">
      <article className="scenario-report-document">
        <header><div><span>사고 조치 결과 보고서</span><h2>{title}</h2></div><span>{reportDate(alert)}</span></header>
        <dl className="scenario-report-meta"><div><dt>대상 설비</dt><dd>{alert.facility}</dd></div><div><dt>기준 문서</dt><dd>작업지시서 v{order.version}</dd></div><div><dt>상태</dt><dd>{report.status === 'completed' ? '완료' : '운영자 편집 중'}</dd></div></dl>
        {report.status === 'draft' ? <textarea aria-label="보고서 본문 편집" className="scenario-document-editor scenario-report-editor" onChange={(event) => setDraft(event.target.value)} value={draft} /> : <pre className="scenario-document-content scenario-report-content">{report.content}</pre>}
        {downloadState === 'error' && <p className="scenario-document-error" role="alert">PDF를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.</p>}
        <footer className="scenario-report-actions">
          {report.status === 'draft' && <><Button icon="document" onClick={() => onSave(draft)}>임시 저장</Button><Button icon="check" onClick={() => void complete()} tone="primary">완료</Button></>}
          <Button disabled={report.status !== 'completed' || downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'PDF 생성 중' : 'PDF 저장'}</Button>
          {report.savedAt && <span>마지막 저장 {new Date(report.savedAt).toLocaleString('ko-KR')}</span>}
        </footer>
      </article>
    </SurfaceCard>

    <SurfaceCard action={<StatusBadge tone="neutral">보고서 전용</StatusBadge>} className="scenario-chat-card" title="보고서 검토 메모">
      <div className="scenario-chat">
        <div className="scenario-chat-source"><StatusBadge tone="neutral">작업지시서 대화와 분리</StatusBadge><span>이 보고서의 검토 메모만 저장합니다. 작업지시서 AI 수정 대화에는 섞이지 않으며 본문 반영은 운영자가 직접 수행합니다.</span></div>
        <div className="scenario-chat-messages">{messages.length === 0 && <p>표현의 명확성, 누락된 확인 항목, 인계 내용 등을 질문할 수 있습니다.</p>}{messages.map((item) => <article className={item.role} key={item.id}><strong>{item.role === 'operator' ? '운영자' : 'AI 참고 의견'}</strong><span>{item.content}</span></article>)}</div>
        <div className="scenario-chat-input"><label htmlFor="scenario-report-chat">검토 메모</label><textarea id="scenario-report-chat" onChange={(event) => setMessage(event.target.value)} onKeyDown={submitOnEnter} placeholder="예: 현장 인계 전에 확인할 항목이 빠졌는지 기록해줘." value={message} /><span>Enter 저장 · Shift+Enter 줄바꿈</span><Button disabled={!message.trim()} onClick={sendMessage} tone="primary">메모 저장</Button></div>
      </div>
    </SurfaceCard>
    </div>
  </div>
  </>
}
