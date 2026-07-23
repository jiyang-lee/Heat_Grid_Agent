import { useEffect, useMemo, useState } from 'react'
import type { AgentAnalysisQueueEntry } from '../console/AgentAnalysisProgress'
import type { AgentRunListItem, AnomalyReportArtifact, WorkOrderStructuredContent } from '../api/contracts'
import { ActivityFilters } from '../console/ai-activity/ActivityFilters'
import { ExecutionList } from '../console/ai-activity/ExecutionList'
import { ReportDocxPreview } from '../console/ai-activity/ReportDocxPreview'
import { WorkOrderActionFooter } from '../console/ai-activity/WorkOrderActionFooter'
import { WorkOrderExcelPreview } from '../console/ai-activity/WorkOrderExcelPreview'
import { WorkOrderHoverRail } from '../console/ai-activity/WorkOrderHoverRail'
import { EXECUTION_STATUS_FILTERS, executionStatus, executionStatusTone, facilityName, type PeriodFilter } from '../console/ai-activity/activityMappers'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { FinalTestProjectChat } from './FinalTestProjectChat'
import { demoMachineRoom, finalTestRunItem } from './adapters'
import type { FinalTestDemoPackage, FinalTestDemoPackageSummary, FinalTestDocumentType } from './contracts'
import { useFinalTestPackage, useFinalTestPackages } from './hooks'
import { finalTestPriorityForRoom, normalizeFinalTestDisplayText } from './policy'
import { downloadFinalTestReport, downloadFinalTestWorkOrder } from './downloads'
import { FinalTestReportEditor, FinalTestWorkOrderEditor } from './FinalTestDocumentEditor'
import { EMPTY_PRESENTATION, loadPresentation, nextVersion, reportVersionsFor, savePresentation, selectedVersion, workOrderVersionsFor, type FinalTestReportVersion, type FinalTestWorkOrderVersion, type PresentationState } from './presentation'
import './final-test.css'

type ActivityTab = 'execution' | 'orders' | 'reports'
type MobileSurface = 'document' | 'chat'

interface Props {
  readonly entries: readonly AgentAnalysisQueueEntry[]
  readonly initialDemoId: string | null
  readonly onConsumeInitialRun: () => void
}

function summaryFor(entries: readonly AgentAnalysisQueueEntry[], summaries: readonly FinalTestDemoPackageSummary[]): readonly { entry: AgentAnalysisQueueEntry; summary: FinalTestDemoPackageSummary }[] {
  const summaryById = new Map(summaries.map((summary) => [summary.demo_id, summary]))
  return entries.flatMap((entry) => {
    const summary = summaryById.get(entry.runId)
    return summary == null ? [] : [{ entry, summary }]
  })
}

function FinalTestExecutionDetail({ item, pkg, onOpenWorkOrder }: { readonly item: AgentRunListItem; readonly pkg: FinalTestDemoPackage | null; readonly onOpenWorkOrder: () => void }) {
  const status = executionStatus(item)
  const isRunning = item.status !== 'completed'
  const priority = finalTestPriorityForRoom(item.substation_id ?? 30)
  return <SurfaceCard action={<div className="activity-detail-header-actions"><Button disabled={isRunning || pkg == null} icon="document" onClick={onOpenWorkOrder} tone="primary">작업지시서 생성</Button></div>} className="activity-detail activity-plan-detail" title="계획서 상세">
    <div className="detail-body">
      <div className="detail-title"><StatusBadge tone={executionStatusTone(status)}>{status}</StatusBadge><h2>{normalizeFinalTestDisplayText(item.alert_reason ?? '현장 대응 계획')}</h2><p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p><span className={`final-test-priority ${priority.tone}`}>{priority.label}</span></div>
      {isRunning ? <section className="activity-plan-section final-test-analysis-wait" aria-live="polite"><header><span>분석 상태</span><h3>AI 조치 분석 중</h3></header><p>사전 적재된 센서·우선순위 근거를 확인하고 산출물을 준비하고 있습니다.</p></section> : pkg != null && <>
        <section className="activity-plan-section activity-stage-timing"><header><span>단계별 소요 시간</span></header><ol className="activity-stage-timing-list"><li><span>이상 감지</span><strong>완료</strong></li><li><span>우선순위 판단</span><strong>완료</strong></li><li><span>현장 조치 계획</span><strong>완료</strong></li></ol></section>
        <section className="activity-plan-section"><header><span>계획 제목</span><h3>{normalizeFinalTestDisplayText(pkg.fault_label)}</h3></header><div className="activity-plan-structured"><article><h4>핵심 근거</h4><ul>{pkg.fault_payload.sensors.map((sensor) => <li key={sensor.key}><strong>{normalizeFinalTestDisplayText(sensor.label)}</strong><span>{sensor.value}{sensor.unit} · {sensor.status === 'critical' ? '임계 초과' : sensor.status === 'warning' ? '주의' : '정상'}</span></li>)}</ul></article><article><h4>현장 영향</h4><p>{normalizeFinalTestDisplayText(pkg.fault_payload.priority.reason)}</p></article><article className="activity-plan-actions"><h4>권장 조치</h4><ol>{(pkg.work_order_document.steps ?? []).map((step) => <li key={step.order}><strong>{normalizeFinalTestDisplayText(step.title)}</strong><span>{normalizeFinalTestDisplayText(step.detail)}</span></li>)}</ol></article></div></section>
      </>}
    </div>
  </SurfaceCard>
}

function FinalTestVersionRail({ label, versions, selected, accepted, onSelect, visibleThrough }: { readonly label: string; readonly versions: readonly { readonly version: number }[]; readonly selected: number; readonly accepted: number | null; readonly onSelect: (version: number) => void; readonly visibleThrough: number }) {
  const suffix = label === '보고서 목록' ? ' · 승인' : ' · 채택'
  return <WorkOrderHoverRail label={label}><div aria-label={label} className="final-test-version-rail" role="tablist">{versions.filter((item) => item.version <= visibleThrough).map((item) => <button aria-selected={item.version === selected} className={item.version === selected ? 'active' : ''} key={item.version} onClick={() => onSelect(item.version)} role="tab" type="button">v{item.version}{accepted === item.version ? suffix : ''}</button>)}</div></WorkOrderHoverRail>
}

function FinalTestChatPanel({ pkg, demoId, documentType, currentVersion, onPreviewVersion, onApplyVersion, onCancelPreview }: { readonly pkg: FinalTestDemoPackage; readonly demoId: string; readonly documentType: FinalTestDocumentType; readonly currentVersion: number; readonly onPreviewVersion: (version: number) => void; readonly onApplyVersion: (version: number) => void; readonly onCancelPreview: () => void }) {
  return <section className="ops-surface work-order-chat-panel final-test-demo-chat-panel"><FinalTestProjectChat currentVersion={currentVersion} demoId={demoId} documentType={documentType} key={demoId} onApplyVersion={onApplyVersion} onCancelPreview={onCancelPreview} onPreviewVersion={onPreviewVersion} script={pkg.chat_script} sessionKey={demoId} /></section>
}

interface WorkOrderProps {
  readonly pkg: FinalTestDemoPackage
  readonly state: PresentationState
  readonly versions: readonly FinalTestWorkOrderVersion[]
  readonly selected: FinalTestWorkOrderVersion
  readonly onSelect: (version: number) => void
  readonly onSave: (content: WorkOrderStructuredContent) => void
  readonly onAccept: () => void
  readonly onCreateReport: () => void
  readonly currentVersion: number
  readonly onPreviewVersion: (version: number) => void
  readonly onApplyVersion: (version: number) => void
  readonly onCancelPreview: () => void
}

function FinalTestWorkOrder({ pkg, state, versions, selected, onSelect, onSave, onAccept, onCreateReport, currentVersion, onPreviewVersion, onApplyVersion, onCancelPreview }: WorkOrderProps) {
  const [editing, setEditing] = useState(false)
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const previewPending = selected.version > currentVersion
  const accepted = state.workOrderAccepted && (state.acceptedWorkOrderVersion ?? 1) === selected.version && currentVersion === selected.version
  const visibleVersions = versions.filter((item) => item.version <= Math.max(currentVersion, selected.version))
  const canEdit = selected.version < 3
  const download = async () => {
    setDownloadState('working')
    try { await downloadFinalTestWorkOrder(selected.content, pkg, selected.version); setDownloadState('idle') } catch { setDownloadState('error') }
  }
  return <div className="scenario-order-layout work-order-unified-layout final-test-document-layout">
    <FinalTestVersionRail accepted={state.acceptedWorkOrderVersion ?? (state.workOrderAccepted ? 1 : null)} label="작업지시서 목록" onSelect={(version) => { setEditing(false); onSelect(version) }} selected={selected.version} versions={versions} visibleThrough={Math.max(currentVersion, selected.version)} />
    <SurfaceCard action={<StatusBadge tone={accepted ? 'success' : 'warning'}>{accepted ? '최종 채택' : previewPending ? '변경안 확인' : '검토 중'}</StatusBadge>} className="scenario-order-document work-order-excel-panel" title="Excel 양식 미리보기">
      <div className="scenario-document-toolbar"><div aria-label="작업지시서 버전" className="scenario-version-switch" role="tablist">{visibleVersions.map((item) => <button aria-selected={item.version === selected.version} className={item.version === selected.version ? 'active' : ''} key={item.version} onClick={() => { setEditing(false); onSelect(item.version) }} role="tab" type="button">v{item.version}{state.acceptedWorkOrderVersion === item.version ? ' · 채택' : ''}</button>)}</div><div className="scenario-document-commands">{editing ? <Button onClick={() => setEditing(false)}>취소</Button> : <Button disabled={!canEdit} icon="document" onClick={() => setEditing(true)} title={!canEdit ? 'v3에서는 더 이상 새 시연 버전을 만들 수 없습니다.' : undefined}>직접 수정</Button>}<Button disabled={downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'Excel 생성 중' : 'Excel 다운로드'}</Button></div></div>
      <article className="scenario-order-body">{editing ? <FinalTestWorkOrderEditor content={selected.content} onCancel={() => setEditing(false)} onSave={(content) => { onSave(content); setEditing(false) }} /> : <WorkOrderExcelPreview content={selected.content} status={accepted ? 'approved' : 'draft'} version={selected.version} />}{downloadState === 'error' && <p className="scenario-document-error" role="alert">Excel 파일을 만들지 못했습니다.</p>}<WorkOrderActionFooter notice={accepted ? '이 버전이 보고서 생성 기준입니다.' : previewPending ? '챗봇에서 변경 적용 여부를 확인해 주세요.' : '현재 버전을 검토한 뒤 최종 채택하세요.'} saveStatus={downloadState === 'error' ? 'error' : 'idle'}><Button disabled={previewPending || accepted} icon="check" onClick={onAccept} tone="primary">{accepted ? '최종 채택됨' : '선택 버전 최종 채택'}</Button><Button disabled={!accepted} icon="document" onClick={onCreateReport} title={!accepted ? '먼저 현재 작업지시서 버전을 최종 채택해야 보고서를 생성할 수 있습니다.' : undefined}>{accepted ? '보고서 생성' : '보고서 생성 잠김'}</Button></WorkOrderActionFooter></article>
    </SurfaceCard>
    <FinalTestChatPanel currentVersion={currentVersion} demoId={pkg.demo_id} documentType="work_order" onApplyVersion={onApplyVersion} onCancelPreview={onCancelPreview} onPreviewVersion={onPreviewVersion} pkg={pkg} />
  </div>
}

interface ReportProps {
  readonly pkg: FinalTestDemoPackage
  readonly state: PresentationState
  readonly versions: readonly FinalTestReportVersion[]
  readonly selected: FinalTestReportVersion
  readonly onSelect: (version: number) => void
  readonly onSave: (report: AnomalyReportArtifact) => void
  readonly onApprove: () => void
  readonly currentVersion: number
  readonly onPreviewVersion: (version: number) => void
  readonly onApplyVersion: (version: number) => void
  readonly onCancelPreview: () => void
}

function FinalTestReport({ pkg, state, versions, selected, onSelect, onSave, onApprove, currentVersion, onPreviewVersion, onApplyVersion, onCancelPreview }: ReportProps) {
  const [editing, setEditing] = useState(false)
  const [downloadState, setDownloadState] = useState<'idle' | 'working' | 'error'>('idle')
  const previewPending = selected.version > currentVersion
  const approved = state.reportApproved && (state.approvedReportVersion ?? 1) === selected.version && currentVersion === selected.version
  const visibleVersions = versions.filter((item) => item.version <= Math.max(currentVersion, selected.version))
  const canEdit = selected.version < 3
  const download = async () => {
    setDownloadState('working')
    try { await downloadFinalTestReport(selected.artifact, pkg, selected.version, approved); setDownloadState('idle') } catch { setDownloadState('error') }
  }
  return <div className="scenario-order-layout work-order-unified-layout report-unified-layout final-test-document-layout">
    <FinalTestVersionRail accepted={state.approvedReportVersion ?? (state.reportApproved ? 1 : null)} label="보고서 목록" onSelect={(version) => { setEditing(false); onSelect(version) }} selected={selected.version} versions={versions} visibleThrough={Math.max(currentVersion, selected.version)} />
    <SurfaceCard action={<StatusBadge tone={approved ? 'success' : 'warning'}>{approved ? '최종 승인' : previewPending ? '변경안 확인' : '검토 중'}</StatusBadge>} className="work-order-excel-panel report-docx-panel" title="DOCX 양식 미리보기">
      <div className="scenario-document-toolbar"><div aria-label="보고서 버전" className="scenario-version-switch" role="tablist">{visibleVersions.map((item) => <button aria-selected={item.version === selected.version} className={item.version === selected.version ? 'active' : ''} key={item.version} onClick={() => { setEditing(false); onSelect(item.version) }} role="tab" type="button">v{item.version}{state.approvedReportVersion === item.version ? ' · 승인' : ''}</button>)}</div><div className="scenario-document-commands">{editing ? <Button onClick={() => setEditing(false)}>취소</Button> : <Button disabled={!canEdit} icon="document" onClick={() => setEditing(true)} title={!canEdit ? 'v3에서는 더 이상 새 시연 버전을 만들 수 없습니다.' : undefined}>직접 수정</Button>}<Button disabled={downloadState === 'working'} icon="download" onClick={() => void download()}>{downloadState === 'working' ? 'DOCX 생성 중' : 'DOCX 다운로드'}</Button></div></div>
      <div className="report-document-body">{editing ? <FinalTestReportEditor report={selected.artifact} onCancel={() => setEditing(false)} onSave={(report) => { onSave(report); setEditing(false) }} /> : <ReportDocxPreview buildingName={pkg.facility_name} machineRoom={demoMachineRoom(pkg)} report={selected.artifact} statusLabel={approved ? '최종 승인' : '검토 중'} version={selected.version} />}{downloadState === 'error' && <p className="scenario-document-error" role="alert">DOCX 파일을 만들지 못했습니다.</p>}<WorkOrderActionFooter notice={approved ? '시연 세션에서 최종 승인된 보고서입니다.' : previewPending ? '챗봇에서 변경 적용 여부를 확인해 주세요.' : '최신 버전을 최종 승인하면 운영 보고서로 확정됩니다.'} saveStatus={downloadState === 'error' ? 'error' : 'idle'}><Button disabled={previewPending || approved} icon="check" onClick={onApprove} tone="primary">{approved ? '최종 승인됨' : '선택 버전 최종 승인'}</Button></WorkOrderActionFooter></div>
    </SurfaceCard>
    <FinalTestChatPanel currentVersion={currentVersion} demoId={pkg.demo_id} documentType="report" onApplyVersion={onApplyVersion} onCancelPreview={onCancelPreview} onPreviewVersion={onPreviewVersion} pkg={pkg} />
  </div>
}

export function FinalTestDemoWorkspace({ entries, initialDemoId, onConsumeInitialRun }: Props) {
  const packageList = useFinalTestPackages(true)
  const generated = useMemo(() => summaryFor(entries, packageList.data?.items ?? []), [entries, packageList.data])
  const [now, setNow] = useState(() => Date.now())
  const [presentation, setPresentation] = useState<Readonly<Record<string, PresentationState>>>(loadPresentation)
  const [tab, setTab] = useState<ActivityTab>(() => presentation[initialDemoId ?? generated[0]?.entry.runId ?? '']?.activeTab ?? 'execution')
  const [selectedDemoId, setSelectedDemoId] = useState<string | null>(initialDemoId ?? generated[0]?.entry.runId ?? null)
  const [restoredDemoId, setRestoredDemoId] = useState<string | null>(initialDemoId)
  const [mobileSurface, setMobileSurface] = useState<MobileSurface>('document')
  const [period, setPeriod] = useState<PeriodFilter>('7d')
  const [facilityId, setFacilityId] = useState<number | null>(null)
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const selectedPackage = useFinalTestPackage(selectedDemoId ?? '', selectedDemoId != null)

  useEffect(() => { if (generated.length === 0) return undefined; const timer = window.setInterval(() => setNow(Date.now()), 250); return () => window.clearInterval(timer) }, [generated.length])
  useEffect(() => { if (initialDemoId == null) return; setSelectedDemoId(initialDemoId); setTab('execution'); onConsumeInitialRun() }, [initialDemoId, onConsumeInitialRun])
  useEffect(() => { if (selectedDemoId != null && generated.some(({ entry }) => entry.runId === selectedDemoId)) return; setSelectedDemoId(generated[0]?.entry.runId ?? null) }, [generated, selectedDemoId])
  useEffect(() => {
    if (selectedDemoId == null || generated.length === 0 || restoredDemoId === selectedDemoId) return
    if (initialDemoId == null) {
      const restoredTab = presentation[selectedDemoId]?.activeTab
      if (restoredTab != null && restoredTab !== tab) setTab(restoredTab)
    }
    setRestoredDemoId(selectedDemoId)
  }, [generated.length, initialDemoId, presentation, restoredDemoId, selectedDemoId, tab])
  useEffect(() => savePresentation(presentation), [presentation])
  useEffect(() => {
    if (selectedDemoId == null || restoredDemoId !== selectedDemoId || presentation[selectedDemoId]?.activeTab === tab) return
    setPresentation((current) => ({ ...current, [selectedDemoId]: { ...(current[selectedDemoId] ?? EMPTY_PRESENTATION), activeTab: tab } }))
  }, [presentation, restoredDemoId, selectedDemoId, tab])

  const rows = useMemo(() => generated.map(({ entry, summary }) => finalTestRunItem(summary, entry, now)).filter((item) => {
    if (facilityId != null && item.substation_id !== facilityId) return false
    if (search.trim() !== '' && !`${item.alert_reason ?? ''} ${facilityName(item.substation_id, item.manufacturer_id)}`.toLowerCase().includes(search.trim().toLowerCase())) return false
    if (status === 'waiting' && item.status === 'completed') return false
    if (status === 'completed' && item.status !== 'completed') return false
    return true
  }), [facilityId, generated, now, search, status])
  const selectedRow = rows.find((item) => item.run_id === selectedDemoId) ?? rows[0] ?? null
  const selectedPackageData = selectedPackage.data ?? null
  const selectedState = selectedDemoId == null ? EMPTY_PRESENTATION : presentation[selectedDemoId] ?? EMPTY_PRESENTATION
  const workOrderVersions = selectedPackageData == null ? [] : workOrderVersionsFor(selectedState, selectedPackageData)
  const reportVersions = selectedPackageData == null ? [] : reportVersionsFor(selectedState, selectedPackageData)
  const selectedWorkOrder = workOrderVersions.length === 0 ? null : selectedVersion(workOrderVersions, selectedState.selectedWorkOrderVersion)
  const selectedReport = reportVersions.length === 0 ? null : selectedVersion(reportVersions, selectedState.selectedReportVersion)
  const currentWorkOrderVersion = selectedState.currentWorkOrderVersion ?? selectedState.acceptedWorkOrderVersion ?? 1
  const currentReportVersion = selectedState.currentReportVersion ?? selectedState.approvedReportVersion ?? 1
  const facilities = [...new Map(generated.map(({ summary }) => [summary.substation_id, { substationId: summary.substation_id, name: summary.facility_name }])).values()]
  const updateState = (patch: Partial<PresentationState>) => { if (selectedDemoId == null) return; setPresentation((current) => ({ ...current, [selectedDemoId]: { ...(current[selectedDemoId] ?? EMPTY_PRESENTATION), ...patch } })) }
  const selectWorkOrder = (version: number) => updateState({ selectedWorkOrderVersion: version })
  const selectReport = (version: number) => updateState({ selectedReportVersion: version })
  const saveWorkOrder = (content: WorkOrderStructuredContent) => {
    if (selectedDemoId == null || selectedPackageData == null) return
    const seededVersions = workOrderVersions.filter((item) => item.version <= (selectedWorkOrder?.version ?? 1))
    const versions = selectedState.workOrderVersions?.length ? selectedState.workOrderVersions : seededVersions
    const version = nextVersion(versions)
    if (version == null) return
    setPresentation((current) => ({ ...current, [selectedDemoId]: { ...(current[selectedDemoId] ?? EMPTY_PRESENTATION), workOrderVersions: [...versions, { version, content }], selectedWorkOrderVersion: version, currentWorkOrderVersion: version, workOrderAccepted: false, acceptedWorkOrderVersion: undefined, reportReady: false, reportApproved: false, approvedReportVersion: undefined, reportVersions: undefined, selectedReportVersion: undefined } }))
  }
  const saveReport = (report: AnomalyReportArtifact) => {
    if (selectedDemoId == null || selectedPackageData == null) return
    const seededVersions = reportVersions.filter((item) => item.version <= (selectedReport?.version ?? 1))
    const versions = selectedState.reportVersions?.length ? selectedState.reportVersions : seededVersions
    const version = nextVersion(versions)
    if (version == null) return
    setPresentation((current) => ({ ...current, [selectedDemoId]: { ...(current[selectedDemoId] ?? EMPTY_PRESENTATION), reportVersions: [...versions, { version, artifact: report }], selectedReportVersion: version, currentReportVersion: version, reportApproved: false, approvedReportVersion: undefined, reportReady: true } }))
  }
  const openWorkOrder = () => { if (selectedRow?.status !== 'completed' || selectedPackageData == null) return; setTab('orders'); setMobileSurface('document') }
  const acceptedWorkOrder = selectedWorkOrder != null && selectedState.workOrderAccepted && (selectedState.acceptedWorkOrderVersion ?? 1) === selectedWorkOrder.version && currentWorkOrderVersion === selectedWorkOrder.version
  const createReport = () => { if (!acceptedWorkOrder) return; updateState({ reportReady: true }); setTab('reports'); setMobileSurface('document') }
  const previewWorkOrderVersion = (version: number) => {
    if (!workOrderVersions.some((item) => item.version === version)) return
    updateState({ selectedWorkOrderVersion: version, workOrderAccepted: false, acceptedWorkOrderVersion: undefined })
  }
  const applyWorkOrderVersion = (version: number) => {
    if (!workOrderVersions.some((item) => item.version === version)) return
    updateState({ currentWorkOrderVersion: version, selectedWorkOrderVersion: version, workOrderAccepted: false, acceptedWorkOrderVersion: undefined, reportReady: false, reportApproved: false, approvedReportVersion: undefined, selectedReportVersion: undefined })
  }
  const cancelWorkOrderPreview = () => updateState({ selectedWorkOrderVersion: currentWorkOrderVersion })
  const previewReportVersion = (version: number) => {
    if (!reportVersions.some((item) => item.version === version)) return
    updateState({ selectedReportVersion: version, reportApproved: false, approvedReportVersion: undefined })
  }
  const applyReportVersion = (version: number) => {
    if (!reportVersions.some((item) => item.version === version)) return
    updateState({ currentReportVersion: version, selectedReportVersion: version, reportApproved: false, approvedReportVersion: undefined })
  }
  const cancelReportPreview = () => updateState({ selectedReportVersion: currentReportVersion })

  if (generated.length === 0) return <div className="activity-page final-test-activity-page"><SurfaceCard title="AI 조치"><p className="activity-empty-note">알림 상세에서 AI 조치 생성을 시작하면 분석 이력이 표시됩니다.</p></SurfaceCard></div>
  const selectedSummary = generated.find(({ entry }) => entry.runId === selectedDemoId)?.summary ?? generated[0].summary
  const workOrderLocked = selectedRow?.status !== 'completed'
  const reportLocked = !selectedState.reportReady
  const changeTab = (next: ActivityTab) => { if (next === 'orders' && workOrderLocked) return; if (next === 'reports' && reportLocked) return; setTab(next); setMobileSurface('document') }
  return <div className="activity-page final-test-activity-page">
    <nav aria-label="AI 조치 단계" className="activity-tabs"><button aria-selected={tab === 'execution'} className={tab === 'execution' ? 'active' : ''} onClick={() => changeTab('execution')} role="tab" type="button">AI 분석 목록</button><button aria-selected={tab === 'orders'} className={tab === 'orders' ? 'active' : ''} disabled={workOrderLocked} onClick={() => changeTab('orders')} role="tab" title={workOrderLocked ? 'AI 조치 분석이 완료되면 열립니다.' : undefined} type="button">작업지시서</button><button aria-selected={tab === 'reports'} className={tab === 'reports' ? 'active' : ''} disabled={reportLocked} onClick={() => changeTab('reports')} role="tab" title={reportLocked ? '작업지시서를 최종 채택하면 열립니다.' : undefined} type="button">보고서</button></nav>
    {tab === 'execution' && <div className="final-test-execution-content"><ActivityFilters facilities={facilities} facilityId={facilityId} onFacilityChange={setFacilityId} onPeriodChange={setPeriod} onSearchChange={setSearch} onStatusChange={setStatus} period={period} search={search} status={status} statusOptions={EXECUTION_STATUS_FILTERS} totalCount={rows.length} /><div className={`activity-workspace ${selectedRow ? 'split' : ''}`.trim()}><SurfaceCard className="activity-list-card" title="AI 분석 목록"><ExecutionList items={rows} onSelect={setSelectedDemoId} priorityDisplay={(item) => finalTestPriorityForRoom(item.substation_id ?? 30)} selectedId={selectedDemoId} /></SurfaceCard>{selectedRow && <FinalTestExecutionDetail item={selectedRow} onOpenWorkOrder={openWorkOrder} pkg={selectedPackageData} />}</div></div>}
    {tab !== 'execution' && <div className={`final-test-mobile-surface mobile-${mobileSurface}`}><div className="final-test-mobile-switch" aria-label="문서와 챗봇 보기"><button aria-pressed={mobileSurface === 'document'} onClick={() => setMobileSurface('document')} type="button">문서 보기</button><button aria-pressed={mobileSurface === 'chat'} onClick={() => setMobileSurface('chat')} type="button">챗봇 보기</button></div>{selectedPackageData == null || selectedWorkOrder == null || selectedReport == null ? <SurfaceCard title="산출물 준비"><p className="activity-empty-note">선택한 분석의 산출물을 준비하고 있습니다.</p></SurfaceCard> : tab === 'orders' ? <FinalTestWorkOrder currentVersion={currentWorkOrderVersion} onAccept={() => updateState({ workOrderAccepted: true, acceptedWorkOrderVersion: selectedWorkOrder.version, currentWorkOrderVersion: selectedWorkOrder.version })} onApplyVersion={applyWorkOrderVersion} onCancelPreview={cancelWorkOrderPreview} onCreateReport={createReport} onPreviewVersion={previewWorkOrderVersion} onSave={saveWorkOrder} onSelect={selectWorkOrder} pkg={selectedPackageData} selected={selectedWorkOrder} state={selectedState} versions={workOrderVersions} /> : <FinalTestReport currentVersion={currentReportVersion} onApplyVersion={applyReportVersion} onApprove={() => updateState({ reportApproved: true, approvedReportVersion: selectedReport.version, currentReportVersion: selectedReport.version })} onCancelPreview={cancelReportPreview} onPreviewVersion={previewReportVersion} onSave={saveReport} onSelect={selectReport} pkg={selectedPackageData} selected={selectedReport} state={selectedState} versions={reportVersions} />}</div>}
    <span className="final-test-selected-case" aria-hidden="true">{normalizeFinalTestDisplayText(selectedSummary.facility_name)} · 기계실 {selectedSummary.substation_id}</span>
  </div>
}
