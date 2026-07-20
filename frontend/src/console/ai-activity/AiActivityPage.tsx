import { useEffect, useMemo, useState } from 'react'
import type { ActivityProjectionQuery, AgentRunListQuery, OpsAgentResultV4 } from '../../api/contracts'
import { useAgentReports, useAgentRuns, useWorkOrders } from '../../api/hooks'
import { ScenarioReportWorkspace } from '../../scenario/ScenarioReportWorkspace'
import { ScenarioWorkOrderWorkspace } from '../../scenario/ScenarioWorkOrderWorkspace'
import { SCENARIO_ALERTS } from '../../scenario/scenarioData'
import type { EntryMode } from '../../scenario/types'
import { useScenario } from '../../scenario/useScenario'
import { ApiState, SurfaceCard } from '../ui'
import { ActivityFilters, type FacilityOption } from './ActivityFilters'
import {
  EXECUTION_STATUS_FILTERS,
  REVIEW_STATUS_FILTERS,
  type ExecutionStatusFilter,
  type PeriodFilter,
  type ReviewStatusFilter,
  executionStatus,
  facilityName,
  periodToCreatedFrom,
} from './activityMappers'
import { ExecutionDetail } from './ExecutionDetail'
import { ExecutionList } from './ExecutionList'
import { ReportDetail } from './ReportDetail'
import { ReportList } from './ReportList'
import { WorkOrderDetail } from './WorkOrderDetail'
import { WorkOrderList } from './WorkOrderList'

type ActivityTab = 'execution' | 'orders' | 'reports'

const PAGE_SIZE = 100

interface TabFilterState {
  readonly period: PeriodFilter
  readonly facilityId: number | null
  readonly status: string
  readonly searchInput: string
  readonly search: string
}

const initialFilters: TabFilterState = { period: '7d', facilityId: null, status: 'all', searchInput: '', search: '' }

interface Props {
  readonly entryMode: EntryMode | null
  readonly incidentAlertId: string | null
  readonly initialRunId: string | null
  readonly onConsumeInitialRun: () => void
}

export function AiActivityPage({ entryMode, incidentAlertId, initialRunId, onConsumeInitialRun }: Props) {
  const scenario = useScenario()
  const [tab, setTab] = useState<ActivityTab>('execution')
  const [filters, setFilters] = useState<Record<ActivityTab, TabFilterState>>({ execution: initialFilters, orders: initialFilters, reports: initialFilters })
  const [selected, setSelected] = useState<Record<ActivityTab, string | null>>({ execution: null, orders: null, reports: null })
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null)
  const [focusedIncidentAlertId, setFocusedIncidentAlertId] = useState<string | null>(null)
  const faultScenario = entryMode === 'fault'
  const incidentEntry = faultScenario
  const [openedWorkOrderId, setOpenedWorkOrderId] = useState<string | null>(null)

  useEffect(() => {
    if (initialRunId == null) return
    setTab('execution')
    setSelected((current) => ({ ...current, execution: null }))
    setFocusedRunId(initialRunId)
    setFocusedIncidentAlertId(faultScenario ? incidentAlertId : null)
    onConsumeInitialRun()
  }, [faultScenario, incidentAlertId, initialRunId, onConsumeInitialRun])

  const active = filters[tab]
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => current[tab].search === current[tab].searchInput ? current : { ...current, [tab]: { ...current[tab], search: current[tab].searchInput } })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [tab, active.searchInput])

  const updateFilter = (patch: Partial<TabFilterState>) => {
    setFilters((current) => ({ ...current, [tab]: { ...current[tab], ...patch } }))
    setSelected((current) => ({ ...current, [tab]: null }))
    if (tab === 'orders') setOpenedWorkOrderId(null)
    if (tab === 'execution') setFocusedRunId(null)
  }

  const baseQuery = useMemo(() => {
    const created_from = periodToCreatedFrom(active.period)
    return { ...(created_from ? { created_from } : {}), ...(active.facilityId != null ? { substation_id: active.facilityId } : {}), ...(active.search ? { search: active.search } : {}), limit: PAGE_SIZE }
  }, [active.period, active.facilityId, active.search])

  const executionQuery: AgentRunListQuery = useMemo(() => ({ ...baseQuery }), [baseQuery])
  const projectionQuery: ActivityProjectionQuery = useMemo(() => {
    const status = active.status as ReviewStatusFilter
    return { ...baseQuery, ...(status !== 'all' ? { operator_review_status: status } : {}) }
  }, [baseQuery, active.status])

  const runs = useAgentRuns(tab === 'execution' ? executionQuery : undefined)
  const orders = useWorkOrders(tab === 'orders' && !incidentEntry ? projectionQuery : undefined)
  const reports = useAgentReports(tab === 'reports' && !incidentEntry ? projectionQuery : undefined)
  const allExecutionItems = useMemo(() => tab === 'execution' ? (runs.data?.items ?? []) : [], [tab, runs.data])
  const executionItems = useMemo(() => {
    const filter = active.status as ExecutionStatusFilter
    if (filter === 'all') return allExecutionItems
    return allExecutionItems.filter((item) => {
      const label = executionStatus(item)
      if (filter === 'waiting') return label === '대기'
      if (filter === 'approved') return label === '승인'
      return label === '문서 완료'
    })
  }, [active.status, allExecutionItems])
  const orderItems = useMemo(() => tab === 'orders' ? (orders.data?.items ?? []) : [], [tab, orders.data])
  const reportItems = useMemo(() => tab === 'reports' ? (reports.data?.items ?? []) : [], [tab, reports.data])
  const activeQueryState = tab === 'execution' ? runs : tab === 'orders' ? orders : reports
  const totalCount = tab === 'execution'
    ? (active.status === 'all' ? (runs.data?.total_count ?? executionItems.length) : executionItems.length)
    : tab === 'orders' ? (orders.data?.total_count ?? null) : (reports.data?.total_count ?? null)

  const selectedExecution = executionItems.find((item) => item.run_id === selected.execution) ?? null
  const selectedOrder = orderItems.find((item) => item.run_id === selected.orders) ?? null
  const selectedReport = reportItems.find((item) => item.artifact_id === selected.reports) ?? null
  useEffect(() => {
    if (tab === 'execution' && selected.execution && !runs.isLoading && !selectedExecution) {
      setSelected((current) => ({ ...current, execution: null }))
      setFocusedRunId(null)
    }
    if (!incidentEntry && tab === 'orders' && selected.orders && orders.data && !orders.isLoading && !selectedOrder) setSelected((current) => ({ ...current, orders: null }))
    if (!incidentEntry && tab === 'reports' && selected.reports && reports.data && !reports.isLoading && !selectedReport) setSelected((current) => ({ ...current, reports: null }))
  }, [incidentEntry, orders.data, orders.isLoading, reports.data, reports.isLoading, runs.isLoading, selected, selectedExecution, selectedOrder, selectedReport, tab])

  const facilities: FacilityOption[] = useMemo(() => {
    const ids = new Map<number, string>()
    const collect = (substationId: number | null, manufacturerId: string | null) => {
      if (substationId == null || ids.has(substationId)) return
      ids.set(substationId, facilityName(substationId, manufacturerId))
    }
    allExecutionItems.forEach((item) => collect(item.substation_id, item.manufacturer_id))
    orderItems.forEach((item) => collect(item.substation_id, item.manufacturer_id))
    reportItems.forEach((item) => collect(item.substation_id, item.manufacturer_id))
    if (active.facilityId != null && !ids.has(active.facilityId)) ids.set(active.facilityId, facilityName(active.facilityId, null))
    return [...ids.entries()].map(([substationId, name]) => ({ substationId, name })).sort((a, b) => a.substationId - b.substationId)
  }, [active.facilityId, allExecutionItems, orderItems, reportItems])

  const scenarioAlertId = focusedIncidentAlertId ?? scenario.state.documentAlertId ?? scenario.state.selectedAlertId
  const incidentAlert = faultScenario ? SCENARIO_ALERTS.find((alert) => alert.id === scenarioAlertId) ?? null : null
  const statusOptions = tab === 'execution' ? EXECUTION_STATUS_FILTERS : REVIEW_STATUS_FILTERS
  const incidentWorkspace = incidentEntry && incidentAlert != null && (tab === 'orders' || tab === 'reports')
  const selectedDetail = (tab === 'execution' && selectedExecution != null) || (!incidentEntry && tab === 'orders' && selectedOrder != null) || (!incidentEntry && tab === 'reports' && selectedReport != null)
  const showList = !incidentWorkspace
  const split = showList && selectedDetail
  const isEmpty = tab === 'execution' ? executionItems.length === 0 : tab === 'orders' ? orderItems.length === 0 : reportItems.length === 0

  const changeTab = (next: ActivityTab) => {
    setTab(next)
    if (!incidentEntry) {
      setFocusedRunId(null)
      setSelected((current) => ({ ...current, [next]: null }))
    }
  }
  const closePlan = () => {
    setFocusedRunId(null)
    setSelected((current) => ({ ...current, execution: null }))
  }
  const openWorkOrderFromExecution = (runId: string, result: OpsAgentResultV4) => {
    if (incidentEntry && incidentAlert != null) {
      scenario.selectAlert(incidentAlert.id)
      scenario.createWorkOrder(runId, result)
      setTab('orders')
      return
    }
    setFocusedRunId(null)
    setTab('orders')
    setSelected((current) => ({ ...current, execution: null, orders: runId }))
  }
  const createIncidentReport = () => {
    scenario.createReportDraft()
    setTab('reports')
  }

  return <div className="page-stack activity-page">
    <div className="activity-tabs" role="tablist">{([['execution', 'AI 분석 목록'], ['orders', '작업지시서']] as const).map(([key, label]) => <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => changeTab(key)} role="tab" type="button">{label}</button>)}</div>
    <div className={`activity-workspace${split ? ' split' : ''}${showList ? '' : ' focused'}`}>
      {showList && <div className="activity-main"><SurfaceCard className="activity-list-card">
        <ActivityFilters facilities={facilities} facilityId={active.facilityId} onFacilityChange={(value) => updateFilter({ facilityId: value })} onPeriodChange={(value) => updateFilter({ period: value })} onSearchChange={(value) => setFilters((current) => ({ ...current, [tab]: { ...current[tab], searchInput: value } }))} onStatusChange={(value) => updateFilter({ status: value })} period={active.period} search={active.searchInput} status={active.status} statusOptions={statusOptions} totalCount={totalCount} />
        <ApiState empty={!activeQueryState.isLoading && !activeQueryState.isError && isEmpty} error={activeQueryState.isError} loading={activeQueryState.isLoading} retry={() => void activeQueryState.refetch()} />
        {tab === 'execution' && executionItems.length > 0 && <ExecutionList items={executionItems} onSelect={(runId) => setSelected((current) => ({ ...current, execution: runId }))} selectedId={selected.execution} />}
        {tab === 'orders' && orderItems.length > 0 && <WorkOrderList items={orderItems} onSelect={(runId) => { setOpenedWorkOrderId(null); setSelected((current) => ({ ...current, orders: runId })) }} selectedId={selected.orders} />}
        {tab === 'reports' && reportItems.length > 0 && <ReportList items={reportItems} onSelect={(artifactId) => setSelected((current) => ({ ...current, reports: artifactId }))} selectedId={selected.reports} />}
      </SurfaceCard></div>}

      {tab === 'execution' && selectedExecution && <div className="activity-detail-pane"><ExecutionDetail item={selectedExecution} onClose={closePlan} onOpenWorkOrder={openWorkOrderFromExecution} /></div>}
      {!incidentEntry && tab === 'orders' && selectedOrder && <div className="activity-detail-pane"><WorkOrderDetail item={selectedOrder} mode={openedWorkOrderId === selectedOrder.run_id ? 'detail' : 'preview'} onClose={() => openedWorkOrderId === selectedOrder.run_id ? setOpenedWorkOrderId(null) : setSelected((current) => ({ ...current, orders: null }))} onOpenDetail={() => setOpenedWorkOrderId(selectedOrder.run_id)} /></div>}
      {!incidentEntry && tab === 'reports' && selectedReport && <div className="activity-detail-pane"><ReportDetail item={selectedReport} onClose={() => setSelected((current) => ({ ...current, reports: null }))} /></div>}
      {incidentEntry && tab === 'orders' && incidentAlert && <ScenarioWorkOrderWorkspace alert={incidentAlert} runId={scenario.state.workOrders.at(-1)?.sourceRunId ?? focusedRunId} onAccept={scenario.acceptWorkOrder} onAppendMessages={scenario.appendWorkOrderMessages} onAppendRevision={scenario.appendWorkOrderRevision} onCreateReport={createIncidentReport} onSelectVersion={scenario.selectWorkOrderVersion} onUpdateContent={scenario.updateWorkOrderContent} state={scenario.state} />}
      {incidentEntry && tab === 'reports' && incidentAlert && <ScenarioReportWorkspace alert={incidentAlert} runId={focusedRunId} messages={scenario.state.reportMessages} onComplete={scenario.completeReport} onCreateDraft={scenario.createReportDraft} onPostMessage={scenario.postReportMessage} onSave={scenario.saveReportDraft} order={scenario.state.workOrders.find((order) => order.version === scenario.state.acceptedWorkOrderVersion)} report={scenario.state.report} />}
    </div>
  </div>
}
