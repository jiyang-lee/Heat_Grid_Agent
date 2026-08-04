import { useEffect, useMemo, useState } from 'react'
import type { AnomalyReportArtifact, IncidentDocumentResponse } from '../api/contracts'
import { ApiError } from '../api/client'
import { reportDocumentsApi } from '../api/backend'
import { useApproveIncidentReport, useEditIncidentReport, useGenerateIncidentReport, useIncidentDocuments, useReviewChatThreadOpen } from '../api/hooks'
import { useConfirmDialog } from '../console/ConfirmDialog'
import { ReportDocxPreview } from '../console/ai-activity/ReportDocxPreview'
import { ReportReviewChat } from '../console/ai-activity/ReportReviewChat'
import { WorkOrderHoverRail } from '../console/ai-activity/WorkOrderHoverRail'
import { WorkOrderActionFooter } from '../console/ai-activity/WorkOrderActionFooter'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { ScenarioReportRail } from './ScenarioReportRail'
import { SCENARIO_INCIDENT_AT } from './scenarioData'
import type { ScenarioAlert, ScenarioDocumentGroup, ScenarioReport, WorkOrderVersion } from './types'

interface Props {
  readonly alert: ScenarioAlert
  readonly activeGroupId: string | null
  readonly groups: readonly ScenarioDocumentGroup[]
  readonly order: WorkOrderVersion | undefined
  readonly report: ScenarioReport
  readonly onComplete: () => void
  readonly onCreateDraft: () => void
  readonly onOpenWorkOrders: () => void
  readonly onSave: (content: string) => void
  readonly onSelectDocumentGroup: (groupId: string) => void
}

function reportDate(alert: ScenarioAlert): string {
  const date = new Date(alert.detectedAt)
  if (Number.isNaN(date.getTime())) return SCENARIO_INCIDENT_AT.slice(0, 10)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function scenarioReportContext(alert: ScenarioAlert, order: WorkOrderVersion, report: ScenarioReport): AnomalyReportArtifact {
  const currentEvidence = alert.evidence.find((item) => item.includes('→'))
  const currentValue = currentEvidence?.split('→').at(-1)?.trim() ?? ''
  const measurementLabel = alert.affectedMetric === 'supply' ? '공급 온도' : alert.affectedMetric === 'flow' ? '유량' : '환수 온도'
  return {
    report_metadata: { report_id: `HG-${alert.substationId}-${reportDate(alert)}`, generated_at: report.createdAt ?? alert.detectedAt, source_card_id: '' },
    target_asset: { asset_label: alert.facility, configuration_type: alert.facility, window_start: alert.detectedAt, window_end: report.completedAt ?? report.savedAt ?? report.createdAt ?? alert.detectedAt },
    priority_summary: { priority_level: alert.priority, priority_score: alert.modelResult.priorityScore, operator_review: 'Required', confidence: '현장 검토 필요', urgency: `${alert.leadTimeHours}시간 이내`, priority_reason: alert.modelResult.rationale },
    situation_summary: { headline: alert.title, summary: report.content || alert.summary, current_status: report.status === 'completed' ? '조치 보고 완료' : '운영자 검토 중', impact_summary: alert.summary },
    sensor_measurements: [{ label: measurementLabel, current_value: currentValue, data_status: '고장 시나리오 측정값 확인됨', judgement: alert.summary }],
    model_judgment: { anomaly_score: alert.modelResult.anomalyScore, anomaly_label: alert.title, m1_specialist_priority_score: alert.modelResult.priorityScore, agreement: '시나리오 모델 산출', reason: alert.modelResult.rationale },
    key_evidence: alert.evidence.map((item, index) => ({ label: `근거 ${index + 1}`, value: item, interpretation: item, confidence: 'scenario', evidence_ref_ids: [] })),
    risk_analysis: { risk_level: alert.priority, risk_summary: alert.summary, operational_impact: alert.modelResult.rationale },
    recommended_actions: order.sections.flatMap((section) => section.items).slice(0, 5).map((action) => ({ action, urgency: `${alert.leadTimeHours}시간 이내`, owner_hint: '현장 운영팀' })),
    evidence_references: alert.evidence.map((item, index) => ({ ref_id: `scenario-${index + 1}`, source_type: 'scenario_evidence', title: `시나리오 근거 ${index + 1}`, excerpt: item })),
    operator_note: { note: report.content, review_reasons: [alert.title, `기준 작업지시서 v${order.version}`] },
  }
}

function contextWithDocument(context: AnomalyReportArtifact, document: IncidentDocumentResponse | null): AnomalyReportArtifact {
  if (document == null || !('body' in document.content)) return context
  return {
    ...context,
    situation_summary: { ...(context.situation_summary ?? {}), headline: document.content.title, summary: document.content.body },
    recommended_actions: document.content.actions.map((action) => ({ action, urgency: '현장 일정에 따라', owner_hint: '현장 운영팀' })),
    operator_note: { ...(context.operator_note ?? {}), note: document.content.safety_notes },
  }
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function ScenarioReportWorkspace({ activeGroupId, alert, groups, order, report, onComplete, onCreateDraft, onOpenWorkOrders, onSave, onSelectDocumentGroup }: Props) {
  const [draft, setDraft] = useState(report.content)
  const [editing, setEditing] = useState(false)
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const { confirm, dialog: confirmDialog } = useConfirmDialog()
  const { data: reportThreadData, mutateAsync: openReportThread } = useReviewChatThreadOpen()
  const incidentId = reportThreadData?.incident_id ?? null
  const incidentDocuments = useIncidentDocuments(incidentId)
  const generateReport = useGenerateIncidentReport()
  const editReport = useEditIncidentReport()
  const approveReport = useApproveIncidentReport()
  useEffect(() => setDraft(report.content), [report.content])
  const context = useMemo(() => order ? scenarioReportContext(alert, order, { ...report, content: draft }) : null, [alert, draft, order, report])
  const documents = useMemo(() => (incidentDocuments.data?.items ?? []).filter((document) => document.document_type === 'incident_report').sort((left, right) => right.version - left.version), [incidentDocuments.data?.items])
  const latest = documents[0] ?? null
  const selected = documents.find((document) => document.version === selectedVersion) ?? latest
  const selectedDocumentVersion = selected?.version
  const selectedDocumentId = selected?.document_version_id
  const selectedDocumentBody = selected != null && 'body' in selected.content ? selected.content.body : null
  const displayedContext = context == null ? null : contextWithDocument(context, selected)

  useEffect(() => {
    if (order?.sourceRunId == null) return
    void openReportThread({ runId: order.sourceRunId, created_by: 'ops-manager', idempotency_key: requestId(`scenario-report-thread-${order.sourceRunId}`) }).catch((reason: unknown) => {
      if (reason instanceof ApiError) setApiError(reason.message)
    })
  }, [openReportThread, order?.sourceRunId])

  useEffect(() => {
    if (selectedDocumentVersion != null) setSelectedVersion(selectedDocumentVersion)
  }, [selectedDocumentVersion])

  useEffect(() => {
    if (selectedDocumentBody != null) setDraft(selectedDocumentBody)
  }, [selectedDocumentBody, selectedDocumentId])
  const reportRail = <ScenarioReportRail activeGroupId={activeGroupId} groups={groups} onSelect={onSelectDocumentGroup} />
  const hoverRail = <WorkOrderHoverRail label="보고서 목록">{reportRail}</WorkOrderHoverRail>

  if (!order) return <>{confirmDialog}<div className="scenario-report-list-layout report-unified-empty">{hoverRail}<SurfaceCard title="보고서 상세"><div className="scenario-report-empty"><StatusBadge tone="neutral">작업지시서 채택 대기</StatusBadge><p>작업지시서 v1-v3 중 하나를 최종 채택한 뒤 보고서를 생성할 수 있습니다.</p><Button icon="arrow" onClick={onOpenWorkOrders}>작업지시서에서 버전 채택하기</Button></div></SurfaceCard></div></>
  if (report.status === 'idle') return <>{confirmDialog}<div className="scenario-report-list-layout report-unified-empty">{hoverRail}<SurfaceCard title="보고서 상세"><div className="scenario-report-empty"><StatusBadge tone="neutral">보고서 미생성</StatusBadge><p>최종 채택한 작업지시서 v{order.version}을 기준으로 보고서 초안을 생성합니다.</p><Button icon="document" onClick={onCreateDraft} tone="primary">보고서 생성</Button></div></SurfaceCard></div></>

  const complete = async () => {
    if (incidentId == null || selected == null || selected !== latest) return
    if (!await confirm('현재 보고서를 최종 승인할까요?')) return
    setApiError(null)
    try {
      await approveReport.mutateAsync({ incidentId, body: { expected_version: selected.version, approved_by: 'ops-manager', idempotency_key: requestId(`scenario-report-approve-${selected.document_version_id}`), note: `보고서 v${selected.version} 운영자 최종 승인` } })
      onSave(draft)
      onComplete()
      setEditing(false)
    } catch (reason: unknown) {
      if (reason instanceof ApiError) setApiError(reason.message)
      else throw reason
    }
  }
  const save = async () => {
    if (incidentId == null || context == null || order == null) return
    const actions = order.sections.flatMap((section) => section.items)
    const title = `${alert.title} ${alert.facility} 조치 결과 보고서`
    const content = { title, body: draft.trim() || context.situation_summary?.summary?.toString() || '보고서 본문을 입력해 주세요.', actions, safety_notes: context.operator_note?.note?.toString() ?? '' }
    setApiError(null)
    try {
      const next = selected == null
        ? await generateReport.mutateAsync({ incidentId, body: { created_by: 'ops-manager', idempotency_key: requestId(`scenario-report-generate-${alert.id}`), content } })
        : await editReport.mutateAsync({ incidentId, version: selected.version, body: { expected_version: selected.version, edited_by: 'ops-manager', idempotency_key: requestId(`scenario-report-edit-${selected.document_version_id}`), ...content } })
      setSelectedVersion(next.version)
      onSave(draft)
      setEditing(false)
    } catch (reason: unknown) {
      if (reason instanceof ApiError) setApiError(reason.message)
      else throw reason
    }
  }
  const download = async () => {
    if (displayedContext == null) return
    setDownloadState('working')
    try {
      await reportDocumentsApi.download({ report_context: displayedContext, alert_id: alert.id, building_name: alert.facility, machine_room: `기계실 ${alert.substationId}`, status_label: selected?.status === 'approved' ? '최종 승인' : '검토 중', document_version: selected?.version ?? 1 }, `heatgrid-ai-report-${alert.substationId}-v${selected?.version ?? 1}-${reportDate(alert)}.docx`)
      setDownloadState('idle')
    } catch {
      setDownloadState('error')
    }
  }

  return <>{confirmDialog}<div className="scenario-order-layout work-order-unified-layout report-unified-layout">
    {hoverRail}
    <SurfaceCard action={<StatusBadge tone={selected?.status === 'approved' ? 'success' : 'notice'}>{selected?.status === 'approved' ? '최종 승인' : '검토 중'}</StatusBadge>} className="work-order-excel-panel report-docx-panel" title="DOCX 양식 미리보기">
      <div className="scenario-document-toolbar">
        {documents.length > 1 ? <div aria-label="보고서 버전" className="scenario-version-switch" role="tablist">{documents.map((document) => <button aria-selected={document.version === selected?.version} className={document.version === selected?.version ? 'active' : ''} key={document.document_version_id} onClick={() => setSelectedVersion(document.version)} role="tab" type="button">v{document.version}{document.status === 'approved' ? ' · 승인' : ''}</button>)}</div> : <span className="work-order-version-badge">v{selected?.version ?? 1}{selected?.status === 'approved' ? ' · 승인' : ''}</span>}
        <div className="scenario-document-commands">
          <Button icon="activity" onClick={() => document.querySelector('.report-review-chat')?.scrollIntoView({ behavior: 'smooth', block: 'start' })} tone="primary">AI 수정·질문으로 이동</Button>
          {editing ? <><Button disabled={generateReport.isPending || editReport.isPending} onClick={() => setEditing(false)}>취소</Button><Button disabled={incidentId == null || generateReport.isPending || editReport.isPending} icon="check" onClick={() => void save()} tone="primary">{generateReport.isPending || editReport.isPending ? '저장 중' : selected == null ? '보고서 저장' : '새 버전으로 저장'}</Button></> : <Button disabled={selected?.status === 'approved' || incidentId == null} icon="document" onClick={() => setEditing(true)}>직접 수정</Button>}
          <Button disabled={downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'DOCX 생성 중' : 'DOCX 다운로드'}</Button>
        </div>
      </div>
      <div className="report-document-body">
        {editing ? <textarea aria-label="보고서 본문 편집" className="scenario-document-editor scenario-report-editor" onChange={(event) => setDraft(event.target.value)} value={draft} /> : displayedContext && <ReportDocxPreview buildingName={alert.facility} machineRoom={`기계실 ${alert.substationId}`} report={displayedContext} statusLabel={selected?.status === 'approved' ? '최종 승인' : '검토 중'} version={selected?.version ?? 1} />}
        {downloadState === 'error' && <p className="scenario-document-error" role="alert">DOCX 파일을 만들지 못했습니다.</p>}
        {apiError && <p className="form-error" role="alert">{apiError}</p>}
        <WorkOrderActionFooter notice={selected?.status === 'approved' ? `v${selected.version}이 최종 승인된 보고서입니다.` : '최신 버전을 최종 승인하면 운영 보고서로 확정됩니다.'} saveStatus={generateReport.isPending || editReport.isPending ? 'saving' : 'idle'}>
          <Button disabled={selected == null || selected !== latest || selected.status === 'approved' || approveReport.isPending} icon="check" onClick={() => void complete()} tone="primary">{selected?.status === 'approved' ? '최종 승인됨' : approveReport.isPending ? '승인 중' : '선택 버전 최종 승인'}</Button>
        </WorkOrderActionFooter>
      </div>
    </SurfaceCard>
    {displayedContext && <ReportReviewChat contextLabel={`${alert.facility} · 기계실 ${alert.substationId} 이상 분석 보고서 v${selected?.version ?? 1}`} reportContext={displayedContext} storageKey={`scenario:${activeGroupId ?? alert.id}:${selected?.document_version_id ?? 'draft'}`} />}
  </div></>
}
