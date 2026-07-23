import { useEffect, useMemo, useState } from 'react'
import type { AgentAnalysisQueueEntry } from '../console/AgentAnalysisProgress'
import type { AgentRunListItem } from '../api/contracts'
import { ActivityFilters } from '../console/ai-activity/ActivityFilters'
import { ExecutionList } from '../console/ai-activity/ExecutionList'
import { ReportDocxPreview } from '../console/ai-activity/ReportDocxPreview'
import { WorkOrderActionFooter } from '../console/ai-activity/WorkOrderActionFooter'
import { WorkOrderExcelPreview } from '../console/ai-activity/WorkOrderExcelPreview'
import { WorkOrderHoverRail } from '../console/ai-activity/WorkOrderHoverRail'
import { EXECUTION_STATUS_FILTERS, executionStatus, executionStatusTone, facilityName, type PeriodFilter } from '../console/ai-activity/activityMappers'
import { Button, StatusBadge, SurfaceCard } from '../console/ui'
import { FinalTestProjectChat } from './FinalTestProjectChat'
import { demoMachineRoom, finalTestRunItem, reportArtifactFor, workOrderContentFor } from './adapters'
import type { FinalTestDemoPackage, FinalTestDemoPackageSummary } from './contracts'
import { useFinalTestPackage, useFinalTestPackages } from './hooks'
import { FINAL_TEST_PRESENTATION_STORAGE_KEY } from './session'
import './final-test.css'

type ActivityTab = 'execution' | 'orders' | 'reports'
type MobileSurface = 'document' | 'chat'

interface PresentationState {
  readonly workOrderAccepted: boolean
  readonly reportReady: boolean
  readonly reportApproved: boolean
}

interface Props {
  readonly entries: readonly AgentAnalysisQueueEntry[]
  readonly initialDemoId: string | null
  readonly onConsumeInitialRun: () => void
}

const EMPTY_PRESENTATION: PresentationState = { workOrderAccepted: false, reportReady: false, reportApproved: false }

function loadPresentation(): Readonly<Record<string, PresentationState>> {
  try {
    const parsed: unknown = JSON.parse(window.sessionStorage.getItem(FINAL_TEST_PRESENTATION_STORAGE_KEY) ?? '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Readonly<Record<string, PresentationState>>
  } catch {
    return {}
  }
}

function savePresentation(value: Readonly<Record<string, PresentationState>>): void {
  try {
    window.sessionStorage.setItem(FINAL_TEST_PRESENTATION_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // The workflow remains usable without session persistence.
  }
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
  return <SurfaceCard action={<div className="activity-detail-header-actions"><Button disabled={isRunning || pkg == null} icon="document" onClick={onOpenWorkOrder} tone="primary">작업지시서 생성</Button></div>} className="activity-detail activity-plan-detail" title="계획서 상세">
    <div className="detail-body">
      <div className="detail-title">
        <StatusBadge tone={executionStatusTone(status)}>{status}</StatusBadge>
        <h2>{item.alert_reason ?? '현장 대응 계획'}</h2>
        <p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p>
        <span>긴급</span>
      </div>
      {isRunning ? <section className="activity-plan-section final-test-analysis-wait" aria-live="polite"><header><span>시연 분석 상태</span><h3>AI 조치 분석 중</h3></header><p>사전 적재된 센서·우선순위 근거를 확인하고 산출물을 준비하고 있습니다.</p></section> : pkg != null && <>
        <section className="activity-plan-section activity-stage-timing"><header><span>단계별 소요 시간</span><h3>시연 데이터 준비 완료</h3></header><ol className="activity-stage-timing-list"><li><span>이상 감지</span><strong>완료</strong></li><li><span>우선순위 판단</span><strong>완료</strong></li><li><span>현장 조치 계획</span><strong>완료</strong></li></ol></section>
        <section className="activity-plan-section"><header><span>계획 제목</span><h3>{pkg.fault_label}</h3></header><div className="activity-plan-structured"><article><h4>핵심 근거</h4><ul>{pkg.fault_payload.sensors.map((sensor) => <li key={sensor.key}><strong>{sensor.label}</strong><span>{sensor.value}{sensor.unit} · {sensor.status === 'critical' ? '임계 초과' : sensor.status === 'warning' ? '주의' : '정상'}</span></li>)}</ul></article><article><h4>현장 영향</h4><p>{pkg.fault_payload.priority.reason}</p></article><article className="activity-plan-actions"><h4>권장 조치</h4><ol>{(pkg.work_order_document.steps ?? []).map((step) => <li key={step.order}><strong>{step.title}</strong><span>{step.detail}</span></li>)}</ol></article></div></section>
      </>}
    </div>
  </SurfaceCard>
}

function FinalTestVersionRail({ label }: { readonly label: string }) {
  return <WorkOrderHoverRail label={label}><div className="final-test-version-rail"><button aria-selected="true" className="active" role="tab" type="button">v1</button></div></WorkOrderHoverRail>
}

function FinalTestChatPanel({ pkg, demoId }: { readonly pkg: FinalTestDemoPackage; readonly demoId: string }) {
  return <section className="ops-surface work-order-chat-panel final-test-demo-chat-panel"><FinalTestProjectChat key={demoId} script={pkg.chat_script} sessionKey={demoId} /></section>
}

function FinalTestWorkOrder({ pkg, state, onAccept, onCreateReport, onMobileSurface }: { readonly pkg: FinalTestDemoPackage; readonly state: PresentationState; readonly onAccept: () => void; readonly onCreateReport: () => void; readonly onMobileSurface: (surface: MobileSurface) => void }) {
  return <div className="scenario-order-layout work-order-unified-layout final-test-document-layout">
    <FinalTestVersionRail label="작업지시서 목록" />
    <SurfaceCard action={<StatusBadge tone={state.workOrderAccepted ? 'success' : 'warning'}>{state.workOrderAccepted ? '최종 채택' : '검토 중'}</StatusBadge>} className="scenario-order-document work-order-excel-panel" title="Excel 양식 미리보기">
      <div className="scenario-document-toolbar"><span className="work-order-version-badge">v1{state.workOrderAccepted ? ' · 채택' : ''}</span><div className="scenario-document-commands"><Button icon="activity" onClick={() => onMobileSurface('chat')} tone="primary">AI 수정·질문으로 이동</Button><Button disabled title="시연 사전 적재본은 직접 수정할 수 없습니다.">직접 수정</Button><Button disabled icon="download" title="시연 문서는 다운로드 대상이 아닙니다.">Excel 다운로드</Button></div></div>
      <article className="scenario-order-body"><WorkOrderExcelPreview content={workOrderContentFor(pkg)} status={state.workOrderAccepted ? 'approved' : 'draft'} version={1} /><WorkOrderActionFooter notice={state.workOrderAccepted ? '이 버전이 보고서 생성 기준입니다.' : '사전 적재된 v1을 검토한 뒤 최종 채택하세요.'} saveStatus="idle"><Button icon="check" onClick={onAccept} tone="primary">{state.workOrderAccepted ? '최종 채택됨' : '선택 버전 최종 채택'}</Button><Button disabled={!state.workOrderAccepted} icon="document" onClick={onCreateReport} title={!state.workOrderAccepted ? '먼저 작업지시서를 최종 채택해야 보고서를 생성할 수 있습니다.' : undefined}>{state.workOrderAccepted ? '보고서 생성' : '보고서 생성 잠김'}</Button></WorkOrderActionFooter></article>
    </SurfaceCard>
    <FinalTestChatPanel demoId={pkg.demo_id} pkg={pkg} />
  </div>
}

function FinalTestReport({ pkg, state, onApprove, onMobileSurface }: { readonly pkg: FinalTestDemoPackage; readonly state: PresentationState; readonly onApprove: () => void; readonly onMobileSurface: (surface: MobileSurface) => void }) {
  return <div className="scenario-order-layout work-order-unified-layout report-unified-layout final-test-document-layout">
    <FinalTestVersionRail label="보고서 목록" />
    <SurfaceCard action={<StatusBadge tone={state.reportApproved ? 'success' : 'warning'}>{state.reportApproved ? '최종 승인' : '검토 중'}</StatusBadge>} className="work-order-excel-panel report-docx-panel" title="DOCX 양식 미리보기">
      <div className="scenario-document-toolbar"><span className="work-order-version-badge">v1{state.reportApproved ? ' · 승인' : ''}</span><div className="scenario-document-commands"><Button icon="activity" onClick={() => onMobileSurface('chat')} tone="primary">AI 수정·질문으로 이동</Button><Button disabled title="시연 사전 적재본은 직접 수정할 수 없습니다.">직접 수정</Button><Button disabled icon="download" title="시연 문서는 다운로드 대상이 아닙니다.">DOCX 다운로드</Button></div></div>
      <div className="report-document-body"><ReportDocxPreview buildingName={pkg.facility_name} machineRoom={demoMachineRoom(pkg)} report={reportArtifactFor(pkg)} statusLabel={state.reportApproved ? '최종 승인' : '검토 중'} version={1} /><WorkOrderActionFooter notice={state.reportApproved ? '시연 세션에서 최종 승인된 보고서입니다.' : '최신 버전을 최종 승인하면 운영 보고서로 확정됩니다.'} saveStatus="idle"><Button disabled={state.reportApproved} icon="check" onClick={onApprove} tone="primary">{state.reportApproved ? '최종 승인됨' : '선택 버전 최종 승인'}</Button></WorkOrderActionFooter></div>
    </SurfaceCard>
    <FinalTestChatPanel demoId={pkg.demo_id} pkg={pkg} />
  </div>
}

export function FinalTestDemoWorkspace({ entries, initialDemoId, onConsumeInitialRun }: Props) {
  const packageList = useFinalTestPackages(true)
  const generated = useMemo(() => summaryFor(entries, packageList.data?.items ?? []), [entries, packageList.data])
  const [now, setNow] = useState(() => Date.now())
  const [tab, setTab] = useState<ActivityTab>('execution')
  const [selectedDemoId, setSelectedDemoId] = useState<string | null>(initialDemoId ?? generated[0]?.entry.runId ?? null)
  const [mobileSurface, setMobileSurface] = useState<MobileSurface>('document')
  const [period, setPeriod] = useState<PeriodFilter>('7d')
  const [facilityId, setFacilityId] = useState<number | null>(null)
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const [presentation, setPresentation] = useState<Readonly<Record<string, PresentationState>>>(loadPresentation)
  const selectedPackage = useFinalTestPackage(selectedDemoId ?? '', selectedDemoId != null)

  useEffect(() => {
    if (generated.length === 0) return undefined
    const timer = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(timer)
  }, [generated.length])

  useEffect(() => {
    if (initialDemoId == null) return
    setSelectedDemoId(initialDemoId)
    setTab('execution')
    onConsumeInitialRun()
  }, [initialDemoId, onConsumeInitialRun])

  useEffect(() => {
    if (selectedDemoId != null && generated.some(({ entry }) => entry.runId === selectedDemoId)) return
    setSelectedDemoId(generated[0]?.entry.runId ?? null)
  }, [generated, selectedDemoId])

  useEffect(() => savePresentation(presentation), [presentation])

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
  const facilities = [...new Map(generated.map(({ summary }) => [summary.substation_id, { substationId: summary.substation_id, name: summary.facility_name }])).values()]
  const updateState = (patch: Partial<PresentationState>) => {
    if (selectedDemoId == null) return
    setPresentation((current) => ({ ...current, [selectedDemoId]: { ...(current[selectedDemoId] ?? EMPTY_PRESENTATION), ...patch } }))
  }
  const openWorkOrder = () => {
    if (selectedRow?.status !== 'completed' || selectedPackageData == null) return
    setTab('orders')
    setMobileSurface('document')
  }
  const createReport = () => {
    if (!selectedState.workOrderAccepted) return
    updateState({ reportReady: true })
    setTab('reports')
    setMobileSurface('document')
  }

  if (generated.length === 0) return <div className="activity-page final-test-activity-page"><SurfaceCard title="AI 조치"><p className="activity-empty-note">알림 상세에서 시연 AI 조치를 생성하면 분석 이력이 표시됩니다.</p></SurfaceCard></div>

  const selectedSummary = generated.find(({ entry }) => entry.runId === selectedDemoId)?.summary ?? generated[0]!.summary
  const isCompleted = selectedRow?.status === 'completed'
  const workOrderLocked = !isCompleted
  const reportLocked = !selectedState.reportReady
  const changeTab = (next: ActivityTab) => {
    if (next === 'orders' && workOrderLocked) return
    if (next === 'reports' && reportLocked) return
    setTab(next)
    setMobileSurface('document')
  }

  return <div className="activity-page final-test-activity-page">
    <nav aria-label="AI 조치 단계" className="activity-tabs"><button aria-selected={tab === 'execution'} className={tab === 'execution' ? 'active' : ''} onClick={() => changeTab('execution')} role="tab" type="button">AI 분석 목록</button><button aria-selected={tab === 'orders'} className={tab === 'orders' ? 'active' : ''} disabled={workOrderLocked} onClick={() => changeTab('orders')} role="tab" title={workOrderLocked ? 'AI 조치 분석이 완료되면 열립니다.' : undefined} type="button">작업지시서</button><button aria-selected={tab === 'reports'} className={tab === 'reports' ? 'active' : ''} disabled={reportLocked} onClick={() => changeTab('reports')} role="tab" title={reportLocked ? '작업지시서를 최종 채택하면 열립니다.' : undefined} type="button">보고서</button></nav>
    {tab === 'execution' && <div className="final-test-execution-content"><ActivityFilters facilities={facilities} facilityId={facilityId} onFacilityChange={setFacilityId} onPeriodChange={setPeriod} onSearchChange={setSearch} onStatusChange={setStatus} period={period} search={search} status={status} statusOptions={EXECUTION_STATUS_FILTERS} totalCount={rows.length} /><div className={`activity-workspace ${selectedRow ? 'split' : ''}`.trim()}><SurfaceCard className="activity-list-card" title="AI 분석 목록"><ExecutionList items={rows} onSelect={setSelectedDemoId} selectedId={selectedDemoId} /></SurfaceCard>{selectedRow && <FinalTestExecutionDetail item={selectedRow} onOpenWorkOrder={openWorkOrder} pkg={selectedPackageData} />}</div></div>}
    {tab !== 'execution' && <div className={`final-test-mobile-surface mobile-${mobileSurface}`}><div className="final-test-mobile-switch" aria-label="문서와 챗봇 보기"><button aria-pressed={mobileSurface === 'document'} onClick={() => setMobileSurface('document')} type="button">문서 보기</button><button aria-pressed={mobileSurface === 'chat'} onClick={() => setMobileSurface('chat')} type="button">챗봇 보기</button></div>{selectedPackageData == null ? <SurfaceCard title="시연 자료"><p className="activity-empty-note">시연 산출물을 불러오는 중입니다.</p></SurfaceCard> : tab === 'orders' ? <FinalTestWorkOrder onAccept={() => updateState({ workOrderAccepted: true })} onCreateReport={createReport} onMobileSurface={setMobileSurface} pkg={selectedPackageData} state={selectedState} /> : <FinalTestReport onApprove={() => updateState({ reportApproved: true })} onMobileSurface={setMobileSurface} pkg={selectedPackageData} state={selectedState} />}</div>}
    <span className="final-test-selected-case" aria-hidden="true">{selectedSummary.facility_name} · 기계실 {selectedSummary.substation_id}</span>
  </div>
}
