/** 실행 활동 목록 — 대상 / 연결 알림 / 시작 시간 / 현재 단계 / 상태 / 결과 */

import type { KeyboardEvent } from 'react'
import type { AgentRunListItem } from '../../api/contracts'
import { StatusBadge } from '../ui'
import {
  USER_STEPS,
  deriveStepper,
  executionStatus,
  executionStatusTone,
  facilityName,
  formatDateTime,
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

function resultText(item: AgentRunListItem): string {
  if (item.status === 'failed') return '원인 확인 필요'
  const parts: string[] = []
  if (item.report_artifact_count > 0) parts.push('보고서 생성됨')
  if (item.has_result) parts.push('작업지시서 생성됨')
  return parts.length > 0 ? parts.join(' · ') : '-'
}

export function ExecutionList({ items, selectedId, onSelect }: Props) {
  return (
    <div className="table-scroll">
      <table className="ops-table activity-table">
        <thead>
          <tr><th>대상</th><th>연결 알림</th><th>시작 시간</th><th>현재 단계</th><th>상태</th><th>결과</th></tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const stepper = deriveStepper({ status: item.status, currentStage: item.current_stage, hasResult: item.has_result })
            const status = executionStatus(item)
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
                <td>
                  <strong title={facilityName(item.substation_id, item.manufacturer_id)}>{facilityName(item.substation_id, item.manufacturer_id)}</strong>
                  <small>기계실 {item.substation_id ?? '-'}</small>
                </td>
                <td className="activity-alert-cell">
                  <StatusBadge tone={priorityTone(item.priority)}>{priorityLabel(item.priority)}</StatusBadge>
                  <span className="activity-alert-reason" title={item.alert_reason ?? undefined}>{item.alert_reason ?? '-'}</span>
                </td>
                <td>{formatDateTime(item.created_at)}</td>
                <td>
                  {item.status === 'failed' && item.current_stage == null ? (
                    <span className="activity-stage-name">실행 실패</span>
                  ) : (
                    <div className="activity-stage-cell">
                      <span className="activity-stage-name">{USER_STEPS[stepper.currentIndex]}</span>
                      <small>{stepper.stepNumber} / {USER_STEPS.length} 단계</small>
                      <div aria-hidden="true" className={`activity-progress ${stepper.failed ? 'failed' : ''} ${item.status === 'completed' ? 'done' : ''}`.trim()}>
                        <i style={{ width: `${(stepper.stepNumber / USER_STEPS.length) * 100}%` }} />
                      </div>
                    </div>
                  )}
                </td>
                <td><StatusBadge tone={executionStatusTone(status)}>{status}</StatusBadge></td>
                <td className="activity-result-cell">{resultText(item)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
