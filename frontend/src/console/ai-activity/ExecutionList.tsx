import type { KeyboardEvent } from 'react'
import type { AgentRunListItem } from '../../api/contracts'
import { displayAlertReason } from '../../domain/alertReason'
import { StatusBadge } from '../ui'
import {
  executionStatus,
  executionStatusTone,
  facilityName,
  priorityLabel,
  priorityTone,
} from './activityMappers'

interface Props {
  readonly items: readonly AgentRunListItem[]
  readonly selectedId: string | null
  readonly onSelect: (runId: string) => void
}

function rowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, select: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    select()
  }
}

export function ExecutionList({ items, selectedId, onSelect }: Props) {
  return (
    <div className="table-scroll">
      <table className="ops-table activity-table execution-activity-table">
        <thead>
          <tr><th>대상</th><th>연결 알림</th><th>상태</th></tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const status = executionStatus(item)
            const selected = item.run_id === selectedId
            const alertReason = displayAlertReason(item.alert_reason)
            return (
              <tr
                aria-selected={selected}
                className={selected ? 'selected-row' : ''}
                key={item.run_id}
                onClick={() => onSelect(item.run_id)}
                onKeyDown={(event) => rowKeyDown(event, () => onSelect(item.run_id))}
                tabIndex={0}
              >
                <td>
                  <strong title={facilityName(item.substation_id, item.manufacturer_id)}>{facilityName(item.substation_id, item.manufacturer_id)}</strong>
                  <small>기계실 {item.substation_id ?? '-'}</small>
                </td>
                <td className="activity-alert-cell">
                  <StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge>
                  <span className="activity-alert-reason" title={alertReason === '-' ? undefined : alertReason}>{alertReason}</span>
                </td>
                <td><StatusBadge tone={executionStatusTone(status)}>{status}</StatusBadge></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
