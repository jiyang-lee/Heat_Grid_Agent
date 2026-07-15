/**
 * AI 활동 페이지 — 실행 활동 / 작업지시서 / 보고서 3탭.
 *
 * 기본은 목록 전용(자동 선택 없음)이고, 행을 선택하면 오른쪽에 상세가 열린다.
 * 탭 전환·닫기·선택 항목 소실 시 선택을 해제하고 목록 전체 폭으로 복원한다.
 * localStorage의 과거 run을 자동 복원하지 않으며, 알림에서 실행을 새로 만든
 * 명시적 딥링크(initialRunId)만 실행 활동 상세를 바로 연다.
 */

import { useEffect, useMemo, useState } from 'react'
import type { ActivityProjectionQuery, AgentRunListQuery } from '../../api/contracts'
import { useAgentReports, useAgentRuns, useWorkOrders } from '../../api/hooks'
import { ApiState, SurfaceCard } from '../ui'
import { ActivityFilters, type FacilityOption } from './ActivityFilters'
import {
  EXECUTION_STATUS_FILTERS,
  REVIEW_STATUS_FILTERS,
  type ExecutionStatusFilter,
  type PeriodFilter,
  type ReviewStatusFilter,
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

const PAGE_SIZE = 10

interface TabFilterState {
  readonly period: PeriodFilter
  readonly facilityId: number | null
  readonly status: string
  readonly searchInput: string
  readonly search: string
}

const initialFilters: TabFilterState = {
  period: '7d',
  facilityId: null,
  status: 'all',
  searchInput: '',
  search: '',
}

interface Props {
  /** 알림에서 실행 생성 직후에만 전달되는 명시적 딥링크 */
  readonly initialRunId: string | null
  readonly onConsumeInitialRun: () => void
}

export function AiActivityPage({ initialRunId, onConsumeInitialRun }: Props) {
  const [tab, setTab] = useState<ActivityTab>('execution')
  const [filters, setFilters] = useState<Record<ActivityTab, TabFilterState>>({
    execution: initialFilters,
    orders: initialFilters,
    reports: initialFilters,
  })
  const [selected, setSelected] = useState<Record<ActivityTab, string | null>>({
    execution: null,
    orders: null,
    reports: null,
  })

  // 알림 → "AI 분석 시작" 딥링크: 실행 활동 탭에서 해당 실행을 바로 연다(1회 소비).
  useEffect(() => {
    if (initialRunId == null) return
    setTab('execution')
    setSelected((current) => ({ ...current, execution: initialRunId }))
    onConsumeInitialRun()
  }, [initialRunId, onConsumeInitialRun])

  const active = filters[tab]

  // 검색 debounce(300ms) — 입력마다 서버 조회하지 않는다.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) =>
        current[tab].search === current[tab].searchInput
          ? current
          : { ...current, [tab]: { ...current[tab], search: current[tab].searchInput } },
      )
    }, 300)
    return () => window.clearTimeout(timer)
  }, [tab, active.searchInput])

  const updateFilter = (patch: Partial<TabFilterState>) => {
    setFilters((current) => ({ ...current, [tab]: { ...current[tab], ...patch } }))
    // 필터가 바뀌면 선택을 유지할 근거가 없어질 수 있어 상세를 닫는다.
    setSelected((current) => ({ ...current, [tab]: null }))
  }

  const baseQuery = useMemo(() => {
    const created_from = periodToCreatedFrom(active.period)
    return {
      ...(created_from ? { created_from } : {}),
      ...(active.facilityId != null ? { substation_id: active.facilityId } : {}),
      ...(active.search ? { search: active.search } : {}),
      limit: PAGE_SIZE,
    }
  }, [active.period, active.facilityId, active.search])

  const executionQuery: AgentRunListQuery = useMemo(() => {
    const status = active.status as ExecutionStatusFilter
    return {
      ...baseQuery,
      ...(status === 'review_pending'
        ? { status: 'completed', operator_review_status: 'pending' }
        : status !== 'all'
          ? { status: status as 'queued' | 'running' | 'completed' | 'failed' }
          : {}),
    }
  }, [baseQuery, active.status])

  const projectionQuery: ActivityProjectionQuery = useMemo(() => {
    const status = active.status as ReviewStatusFilter
    return {
      ...baseQuery,
      ...(status !== 'all' ? { operator_review_status: status } : {}),
    }
  }, [baseQuery, active.status])

  const runs = useAgentRuns(tab === 'execution' ? executionQuery : undefined)
  const orders = useWorkOrders(tab === 'orders' ? projectionQuery : undefined)
  const reports = useAgentReports(tab === 'reports' ? projectionQuery : undefined)

  const executionItems = useMemo(() => (tab === 'execution' ? (runs.data?.items ?? []) : []), [tab, runs.data])
  const orderItems = useMemo(() => (tab === 'orders' ? (orders.data?.items ?? []) : []), [tab, orders.data])
  const reportItems = useMemo(() => (tab === 'reports' ? (reports.data?.items ?? []) : []), [tab, reports.data])

  const activeQueryState = tab === 'execution' ? runs : tab === 'orders' ? orders : reports
  const totalCount =
    tab === 'execution' ? (runs.data?.total_count ?? null)
    : tab === 'orders' ? (orders.data?.total_count ?? null)
    : (reports.data?.total_count ?? null)

  // 데이터 갱신으로 선택 항목이 목록에서 사라지면 상세를 닫는다.
  const selectedExecution = executionItems.find((item) => item.run_id === selected.execution) ?? null
  const selectedOrder = orderItems.find((item) => item.run_id === selected.orders) ?? null
  const selectedReport = reportItems.find((item) => item.artifact_id === selected.reports) ?? null
  useEffect(() => {
    if (tab === 'execution' && selected.execution && !runs.isLoading && !selectedExecution) {
      setSelected((current) => ({ ...current, execution: null }))
    }
    if (tab === 'orders' && selected.orders && !orders.isLoading && !selectedOrder) {
      setSelected((current) => ({ ...current, orders: null }))
    }
    if (tab === 'reports' && selected.reports && !reports.isLoading && !selectedReport) {
      setSelected((current) => ({ ...current, reports: null }))
    }
  }, [tab, selected, selectedExecution, selectedOrder, selectedReport, runs.isLoading, orders.isLoading, reports.isLoading])

  // 건물/기계실 옵션 — 현재 탭 실데이터의 substation_id를 단지명으로 매핑(하드코딩 금지).
  const facilities: FacilityOption[] = useMemo(() => {
    const ids = new Map<number, string>()
    const collect = (substationId: number | null, manufacturerId: string | null) => {
      if (substationId == null || ids.has(substationId)) return
      ids.set(substationId, facilityName(substationId, manufacturerId))
    }
    executionItems.forEach((item) => collect(item.substation_id, item.manufacturer_id))
    orderItems.forEach((item) => collect(item.substation_id, item.manufacturer_id))
    reportItems.forEach((item) => collect(item.substation_id, item.manufacturer_id))
    if (active.facilityId != null && !ids.has(active.facilityId)) {
      ids.set(active.facilityId, facilityName(active.facilityId, null))
    }
    return [...ids.entries()]
      .map(([substationId, name]) => ({ substationId, name }))
      .sort((a, b) => a.substationId - b.substationId)
  }, [executionItems, orderItems, reportItems, active.facilityId])

  const statusOptions = tab === 'execution' ? EXECUTION_STATUS_FILTERS : REVIEW_STATUS_FILTERS
  const detailOpen =
    (tab === 'execution' && selectedExecution != null) ||
    (tab === 'orders' && selectedOrder != null) ||
    (tab === 'reports' && selectedReport != null)

  const changeTab = (next: ActivityTab) => {
    setTab(next)
    // 탭을 바꾸면 해당 탭도 목록 전용 상태로 시작한다.
    setSelected((current) => ({ ...current, [next]: null }))
  }

  const openReportFromOrder = (artifactId: string) => {
    setTab('reports')
    setSelected((current) => ({ ...current, reports: artifactId }))
  }

  const isEmpty =
    (tab === 'execution' && executionItems.length === 0) ||
    (tab === 'orders' && orderItems.length === 0) ||
    (tab === 'reports' && reportItems.length === 0)

  return (
    <div className="page-stack activity-page">
      <header className="page-title">
        <div>
          <h1>AI 활동</h1>
          <p>AI가 알림을 분석하고 진단 근거와 실행 결과·작업지시서·보고서를 한곳에서 검토합니다.</p>
        </div>
      </header>

      <div className="activity-tabs" role="tablist">
        {([['execution', '실행 활동'], ['orders', '작업지시서'], ['reports', '보고서']] as const).map(([key, label]) => (
          <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => changeTab(key)} role="tab" type="button">{label}</button>
        ))}
      </div>

      <div className={`activity-workspace${detailOpen ? ' split' : ''}`}>
        <div className="activity-main">
          <SurfaceCard className="activity-list-card">
            <ActivityFilters
              facilities={facilities}
              facilityId={active.facilityId}
              onFacilityChange={(value) => updateFilter({ facilityId: value })}
              onPeriodChange={(value) => updateFilter({ period: value })}
              onRefresh={() => void activeQueryState.refetch()}
              onSearchChange={(value) => setFilters((current) => ({ ...current, [tab]: { ...current[tab], searchInput: value } }))}
              onStatusChange={(value) => updateFilter({ status: value })}
              pageSize={PAGE_SIZE}
              period={active.period}
              search={active.searchInput}
              status={active.status}
              statusOptions={statusOptions}
              totalCount={totalCount}
            />
            <ApiState
              empty={!activeQueryState.isLoading && !activeQueryState.isError && isEmpty}
              error={activeQueryState.isError}
              loading={activeQueryState.isLoading}
              retry={() => void activeQueryState.refetch()}
            />
            {tab === 'execution' && executionItems.length > 0 && (
              <ExecutionList
                items={executionItems}
                onSelect={(runId) => setSelected((current) => ({ ...current, execution: runId }))}
                selectedId={selected.execution}
              />
            )}
            {tab === 'orders' && orderItems.length > 0 && (
              <WorkOrderList
                items={orderItems}
                onSelect={(runId) => setSelected((current) => ({ ...current, orders: runId }))}
                selectedId={selected.orders}
              />
            )}
            {tab === 'reports' && reportItems.length > 0 && (
              <ReportList
                items={reportItems}
                onSelect={(artifactId) => setSelected((current) => ({ ...current, reports: artifactId }))}
                selectedId={selected.reports}
              />
            )}
          </SurfaceCard>
        </div>

        {tab === 'execution' && selectedExecution && (
          <aside className="activity-detail-pane">
            <ExecutionDetail item={selectedExecution} onClose={() => setSelected((current) => ({ ...current, execution: null }))} />
          </aside>
        )}
        {tab === 'orders' && selectedOrder && (
          <aside className="activity-detail-pane">
            <WorkOrderDetail item={selectedOrder} onClose={() => setSelected((current) => ({ ...current, orders: null }))} onOpenReport={openReportFromOrder} />
          </aside>
        )}
        {tab === 'reports' && selectedReport && (
          <aside className="activity-detail-pane">
            <ReportDetail item={selectedReport} onClose={() => setSelected((current) => ({ ...current, reports: null }))} />
          </aside>
        )}
      </div>
    </div>
  )
}
