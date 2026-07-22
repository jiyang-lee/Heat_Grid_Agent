import { useEffect, useMemo, useRef, useState } from 'react'
import type { AgentReportListItem, AnomalyReportArtifact, AnomalyReportSection, IncidentDocumentContent, IncidentDocumentResponse } from '../../api/contracts'
import { ApiError } from '../../api/client'
import { reportDocumentsApi } from '../../api/backend'
import { useAgentReportContent, useApproveIncidentReport, useEditIncidentReport, useGenerateIncidentReport, useIncidentDocuments, useReviewChatThreadOpen } from '../../api/hooks'
import { safeFilePart } from '../../scenario/documentPdf'
import { ApiState, Button, StatusBadge, SurfaceCard } from '../ui'
import { facilityName, formatDateTime, reportStatusLabel, reportTitle, reviewStatusTone } from './activityMappers'
import { ReportDocxPreview } from './ReportDocxPreview'
import { ReportReviewChat } from './ReportReviewChat'

interface Props {
  readonly item: AgentReportListItem
  readonly onClose: () => void
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function section(value: unknown): AnomalyReportSection {
  return value != null && typeof value === 'object' && !Array.isArray(value) ? value as AnomalyReportSection : {}
}

function strings(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.trim() !== '') : []
}

function reportContent(document: IncidentDocumentResponse): IncidentDocumentContent | null {
  return 'body' in document.content ? document.content : null
}

function documentReport(base: AnomalyReportArtifact, document: IncidentDocumentResponse | null): AnomalyReportArtifact {
  const content = document == null ? null : reportContent(document)
  if (content == null) return base
  const situation = section(base.situation_summary)
  const operatorNote = section(base.operator_note)
  return {
    ...base,
    rendering_hints: { ...section(base.rendering_hints), display_title: content.title },
    situation_summary: { ...situation, headline: content.title, summary: content.body },
    recommended_actions: content.actions.map((action) => ({ action, urgency: '현장 일정에 따라', owner_hint: '현장 운영팀' })),
    operator_note: { ...operatorNote, note: content.safety_notes },
  }
}

function draftFromReport(report: AnomalyReportArtifact, title: string): { readonly title: string; readonly body: string; readonly actions: string; readonly safetyNotes: string } {
  const situation = section(report.situation_summary)
  const note = section(report.operator_note)
  const actions = Array.isArray(report.recommended_actions)
    ? report.recommended_actions.flatMap((item) => typeof item === 'object' && item != null && typeof (item as AnomalyReportSection).action === 'string' ? [(item as AnomalyReportSection).action as string] : [])
    : []
  return { title, body: typeof situation.summary === 'string' ? situation.summary : '', actions: actions.join('\n'), safetyNotes: typeof note.note === 'string' ? note.note : '' }
}

function documentStatus(document: IncidentDocumentResponse | null, fallback: string): string {
  if (document == null) return fallback
  return document.status === 'approved' ? '최종 승인' : '검토 중'
}

export function ReportDetail({ item, onClose }: Props) {
  const report = useAgentReportContent(item.run_id, item.artifact_id)
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [editing, setEditing] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const chatRef = useRef<HTMLElement>(null)
  const { data: reportThreadData, isError: reportThreadIsError, isPending: reportThreadIsPending, mutateAsync: openReportThread } = useReviewChatThreadOpen()
  const incidentId = reportThreadData?.incident_id ?? null
  const incidentDocuments = useIncidentDocuments(incidentId)
  const generateReport = useGenerateIncidentReport()
  const editReport = useEditIncidentReport()
  const approveReport = useApproveIncidentReport()
  const renderingHints = section(report.data?.rendering_hints)
  const title = typeof renderingHints.display_title === 'string' ? renderingHints.display_title : reportTitle(item.kind, item.name)
  const facility = facilityName(item.substation_id, item.manufacturer_id)
  const created = new Date(item.created_at)
  const date = Number.isNaN(created.getTime()) ? 'unknown-date' : created.toISOString().slice(0, 10)
  const reportDocuments = useMemo(() => (incidentDocuments.data?.items ?? []).filter((document) => document.document_type === 'incident_report').sort((left, right) => right.version - left.version), [incidentDocuments.data?.items])
  const latest = reportDocuments[0] ?? null
  const selected = reportDocuments.find((document) => document.version === selectedVersion) ?? latest
  const selectedDocumentVersion = selected?.version
  const selectedDocumentId = selected?.document_version_id
  const displayed = report.data == null ? null : documentReport(report.data, selected)
  const displayedTitle = typeof section(displayed?.rendering_hints).display_title === 'string' ? section(displayed?.rendering_hints).display_title as string : title
  const [draft, setDraft] = useState(() => draftFromReport(report.data ?? {}, title))

  useEffect(() => {
    void openReportThread({ runId: item.run_id, created_by: 'ops-manager', idempotency_key: requestId(`report-thread-${item.run_id}`) }).catch((reason: unknown) => {
      if (reason instanceof ApiError) setError(reason.message)
    })
  }, [item.run_id, openReportThread])

  useEffect(() => {
    if (selectedDocumentVersion != null) setSelectedVersion(selectedDocumentVersion)
  }, [selectedDocumentVersion])

  useEffect(() => {
    if (displayed == null) return
    setDraft(draftFromReport(displayed, displayedTitle))
  }, [displayed, displayedTitle, selectedDocumentId])

  const beginEdit = () => {
    if (selected?.status === 'approved') return
    setEditing(true)
  }
  const save = async () => {
    if (incidentId == null || report.data == null) return
    const actions = strings(draft.actions.split('\n').map((value) => value.trim()).filter(Boolean))
    const content = { title: draft.title.trim() || title, body: draft.body.trim() || '보고서 본문을 입력해 주세요.', actions, safety_notes: draft.safetyNotes.trim() }
    setError(null)
    try {
      const next = selected == null
        ? await generateReport.mutateAsync({ incidentId, body: { created_by: 'ops-manager', idempotency_key: requestId(`report-generate-${item.run_id}`), content } })
        : await editReport.mutateAsync({ incidentId, version: selected.version, body: { expected_version: selected.version, edited_by: 'ops-manager', idempotency_key: requestId(`report-edit-${selected.document_version_id}`), ...content } })
      setSelectedVersion(next.version)
      setEditing(false)
    } catch (reason: unknown) {
      if (reason instanceof ApiError) setError(reason.message)
      else throw reason
    }
  }
  const approve = async () => {
    if (incidentId == null || selected == null || selected !== latest) return
    setError(null)
    try {
      await approveReport.mutateAsync({ incidentId, body: { expected_version: selected.version, approved_by: 'ops-manager', idempotency_key: requestId(`report-approve-${selected.document_version_id}`), note: `보고서 v${selected.version} 운영자 최종 승인` } })
    } catch (reason: unknown) {
      if (reason instanceof ApiError) setError(reason.message)
      else throw reason
    }
  }
  const download = async () => {
    if (displayed == null) return
    setDownloadState('working')
    try {
      await reportDocumentsApi.download({ report_context: displayed, building_name: facility, machine_room: `기계실 ${item.substation_id ?? '-'}`, status_label: documentStatus(selected, reportStatusLabel(item.operator_review_status)), document_version: selected?.version ?? 1 }, `heatgrid-ai-report-${safeFilePart(facility)}-v${selected?.version ?? 1}-${date}.docx`)
      setDownloadState('idle')
    } catch {
      setDownloadState('error')
    }
  }

  return <SurfaceCard action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />} className="activity-detail activity-detail-with-footer report-detail-workspace" title="보고서 상세">
    <div className="detail-body report-detail-body">
      <div className="detail-title"><StatusBadge tone={selected?.status === 'approved' ? 'success' : reviewStatusTone(item.operator_review_status)}>{documentStatus(selected, reportStatusLabel(item.operator_review_status))}</StatusBadge><h2>{displayedTitle}</h2><p>{facility} · 기계실 {item.substation_id ?? '-'}</p><span>생성 {formatDateTime(item.created_at)}</span></div>
      <nav aria-label="보고서 문서 도구" className="scenario-document-toolbar report-document-toolbar">
        {reportDocuments.length > 1 ? <div aria-label="보고서 버전" className="scenario-version-switch" role="tablist">{reportDocuments.map((document) => <button aria-selected={document.version === selected?.version} className={document.version === selected?.version ? 'active' : ''} key={document.document_version_id} onClick={() => setSelectedVersion(document.version)} role="tab" type="button">v{document.version}{document.status === 'approved' ? ' · 승인' : ''}</button>)}</div> : <span className="work-order-version-badge">v{selected?.version ?? 1}{selected?.status === 'approved' ? ' · 승인' : ''}</span>}
        <div className="scenario-document-commands"><Button icon="activity" onClick={() => chatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })} tone="primary">AI 수정·질문으로 이동</Button>{editing ? <><Button disabled={generateReport.isPending || editReport.isPending} onClick={() => setEditing(false)}>취소</Button><Button disabled={incidentId == null || generateReport.isPending || editReport.isPending} icon="check" onClick={() => void save()} tone="primary">{generateReport.isPending || editReport.isPending ? '저장 중' : selected == null ? '보고서 저장' : '새 버전으로 저장'}</Button></> : <Button disabled={selected?.status === 'approved' || incidentId == null} icon="document" onClick={beginEdit}>직접 수정</Button>}<Button disabled={displayed == null || downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'DOCX 생성 중' : 'DOCX 다운로드'}</Button></div>
      </nav>
      <ApiState empty={false} error={report.isError || incidentDocuments.isError} loading={report.isLoading || reportThreadIsPending} retry={() => { void report.refetch(); void incidentDocuments.refetch() }} />
      {reportThreadIsError && <p className="form-error" role="alert">보고서 문서 연결을 열지 못했습니다.</p>}
      {displayed && <div className="work-order-detail-split report-detail-split">
        <article className="work-order-document report-document-panel">{editing ? <div className="report-document-editor"><label>보고서 제목<input onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} value={draft.title} /></label><label>관리자 요약<textarea onChange={(event) => setDraft((current) => ({ ...current, body: event.target.value }))} value={draft.body} /></label><label>권고 조치<textarea onChange={(event) => setDraft((current) => ({ ...current, actions: event.target.value }))} value={draft.actions} /></label><label>작업 전 제한 사항<textarea onChange={(event) => setDraft((current) => ({ ...current, safetyNotes: event.target.value }))} value={draft.safetyNotes} /></label></div> : <ReportDocxPreview buildingName={facility} machineRoom={`기계실 ${item.substation_id ?? '-'}`} report={displayed} statusLabel={documentStatus(selected, reportStatusLabel(item.operator_review_status))} version={selected?.version ?? 1} />}</article>
        <section ref={chatRef}><ReportReviewChat contextLabel={`${facility} · 기계실 ${item.substation_id ?? '-'} 이상 분석 보고서 v${selected?.version ?? 1}`} reportContext={displayed} storageKey={`${item.run_id}:${selected?.document_version_id ?? item.artifact_id}`} /></section>
      </div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {downloadState === 'error' && <p className="form-error" role="alert">DOCX 파일을 만들지 못했습니다.</p>}
    </div>
    <div className="activity-detail-footer detail-actions"><Button disabled={selected == null || selected !== latest || selected.status === 'approved' || approveReport.isPending} icon="check" onClick={() => void approve()} tone="primary">{selected?.status === 'approved' ? `v${selected.version} 최종 승인됨` : selected !== latest ? '최신 버전만 최종 승인 가능' : approveReport.isPending ? '보고서 승인 중' : `v${selected?.version ?? 1} 최종 승인`}</Button></div>
  </SurfaceCard>
}
