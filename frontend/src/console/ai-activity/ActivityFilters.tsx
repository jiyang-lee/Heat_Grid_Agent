/**
 * AI 활동 공통 필터 바 — 기간 / 건물·기계실 / 처리 상태 / 검색 / 총 건수 / 새로고침.
 * 옵션 목록과 상태는 상위(AiActivityPage)가 소유하고, 여기는 표시만 담당한다.
 */

import { Icon } from '../icons'
import { PERIOD_FILTERS, type PeriodFilter } from './activityMappers'

export interface FacilityOption {
  readonly substationId: number
  readonly name: string
}

interface StatusOption {
  readonly value: string
  readonly label: string
}

interface Props {
  readonly period: PeriodFilter
  readonly onPeriodChange: (value: PeriodFilter) => void
  readonly facilities: readonly FacilityOption[]
  readonly facilityId: number | null
  readonly onFacilityChange: (value: number | null) => void
  readonly statusOptions: readonly StatusOption[]
  readonly status: string
  readonly onStatusChange: (value: string) => void
  readonly search: string
  readonly onSearchChange: (value: string) => void
  readonly totalCount: number | null
}

export function ActivityFilters({
  period,
  onPeriodChange,
  facilities,
  facilityId,
  onFacilityChange,
  statusOptions,
  status,
  onStatusChange,
  search,
  onSearchChange,
  totalCount,
}: Props) {
  return (
    <div className="activity-filter-bar">
      <label>
        <span>기간</span>
        <select onChange={(event) => onPeriodChange(event.target.value as PeriodFilter)} value={period}>
          {PERIOD_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>
        <span>건물 / 기계실</span>
        <select
          onChange={(event) => onFacilityChange(event.target.value === 'all' ? null : Number(event.target.value))}
          value={facilityId == null ? 'all' : String(facilityId)}
        >
          <option value="all">전체</option>
          {facilities.map((facility) => (
            <option key={facility.substationId} value={String(facility.substationId)}>
              {facility.name} (기계실 {facility.substationId})
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>처리 상태</span>
        <select onChange={(event) => onStatusChange(event.target.value)} value={status}>
          {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label className="activity-search">
        <span>검색</span>
        <div className="activity-search-box">
          <Icon name="search" />
          <input
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="건물명, 알림 내용, 보고서명"
            value={search}
          />
        </div>
      </label>
      <div className="activity-filter-side">
        <span className="activity-total">총 {totalCount ?? '-'}건</span>
      </div>
    </div>
  )
}
