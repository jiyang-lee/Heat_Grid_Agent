/** 작업지시서 목록 — 우선순위 / 이상 징후 / 대상 설비 / 생성 시간 / 상태 */

import type { KeyboardEvent } from 'react'
import type { WorkOrderListItem } from '../../api/contracts'
import { StatusBadge } from '../ui'
import {
  RAW_REVIEW_STATUS_LABELS,
  facilityName,
  formatDateTime,
  priorityLabel,
  priorityTone,
  reviewStatusTone,
  workOrderStatusLabel,
} from './activityMappers'

interface Props {
  readonly items: readonly WorkOrderListItem[]
  readonly selectedId: string | null
  readonly onSelect: (runId: string) => void
}

function rowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, select: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    select()
  }
}

export function WorkOrderList({ items, selectedId, onSelect }: Props) {
  return (
    <div className="table-scroll">
      <table className="ops-table activity-table">
        <thead>
          <tr><th>우선순위</th><th>이상 징후</th><th>대상 설비</th><th>생성 시간</th><th>상태</th></tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const selected = item.run_id === selectedId
            return (
              <tr
                aria-selected={selected}
                className={selected ? 'selected-row' : ''}
                key={item.run_id}
                onClick={() => onSelect(item.run_id)}
                onKeyDown={(event) => rowKeyDown(event, () => onSelect(item.run_id))}
                tabIndex={0}
              >
                <td><StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge></td>
                <td className="activity-reason-cell"><span title={item.alert_reason ?? undefined}>{item.alert_reason ?? '-'}</span></td>
                <td>
                  <strong>{facilityName(item.substation_id, item.manufacturer_id)}</strong>
                  <small>기계실 {item.substation_id ?? '-'}</small>
                </td>
                <td>{formatDateTime(item.created_at)}</td>
                <td>
                  <span title={RAW_REVIEW_STATUS_LABELS[item.operator_review_status]}>
                    <StatusBadge tone={reviewStatusTone(item.operator_review_status)}>
                      {workOrderStatusLabel(item.operator_review_status)}
                    </StatusBadge>
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
