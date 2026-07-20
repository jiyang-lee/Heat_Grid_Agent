import type { KeyboardEvent } from 'react'
import type { AgentReportListItem } from '../../api/contracts'
import { StatusBadge } from '../ui'
import {
  RAW_REVIEW_STATUS_LABELS,
  facilityName,
  reportStatusLabel,
  reportTitle,
  reviewStatusTone,
} from './activityMappers'

interface Props {
  readonly items: readonly AgentReportListItem[]
  readonly selectedId: string | null
  readonly onSelect: (artifactId: string) => void
}

function rowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, select: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    select()
  }
}

export function ReportList({ items, selectedId, onSelect }: Props) {
  return (
    <div className="table-scroll">
      <table className="ops-table activity-table report-activity-table">
        <thead>
          <tr><th>상태</th><th>보고서명</th><th>대상 설비</th></tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const selected = item.artifact_id === selectedId
            return (
              <tr
                aria-selected={selected}
                className={selected ? 'selected-row' : ''}
                key={item.artifact_id}
                onClick={() => onSelect(item.artifact_id)}
                onKeyDown={(event) => rowKeyDown(event, () => onSelect(item.artifact_id))}
                tabIndex={0}
              >
                <td>
                  <span title={RAW_REVIEW_STATUS_LABELS[item.operator_review_status]}>
                    <StatusBadge tone={reviewStatusTone(item.operator_review_status)}>
                      {reportStatusLabel(item.operator_review_status)}
                    </StatusBadge>
                  </span>
                </td>
                <td>
                  <strong>{reportTitle(item.kind, item.name)} · {facilityName(item.substation_id, item.manufacturer_id)}</strong>
                </td>
                <td>
                  <strong>{facilityName(item.substation_id, item.manufacturer_id)}</strong>
                  <small>기계실 {item.substation_id ?? '-'}</small>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
