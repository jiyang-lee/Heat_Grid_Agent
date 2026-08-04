import { useState } from 'react'
import type { ChecklistResult, WorkOrderChecklistItem } from '../../api/contracts'

const RESULT_LABELS: Record<ChecklistResult, string> = {
  pass: '적합',
  fail: '조치 필요',
  not_applicable: '해당 없음',
  pending: '미점검',
}

interface Props {
  readonly title: string
  readonly items: readonly WorkOrderChecklistItem[]
  readonly pendingKey: string | null
  readonly onPatch: (seq: number, field: string, value: string, key: string) => void
}

/** 현장 확인/작업 세부 항목 표. 카드 너비 전체를 쓰고 필요 시 가로 스크롤한다. */
export function InspectionTable({ title, items, pendingKey, onPatch }: Props) {
  return (
    <section className="work-order-card" aria-label={title}>
      <h4>{title}</h4>
      <div className="table-wrapper">
        <table className="work-order-checklist-table">
          <thead>
            <tr>
              <th className="col-seq">번호</th>
              <th className="col-target">계기·대상</th>
              <th className="col-action">확인 작업</th>
              <th className="col-criteria">판정기준</th>
              <th className="col-result">결과</th>
              <th className="col-value">측정값(전)</th>
              <th className="col-value">측정값(후)</th>
              <th className="col-inspector">점검자</th>
              <th className="col-note">비고</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const seq = item.seq
              return (
                <tr key={seq}>
                  <td className="col-seq">{seq}</td>
                  <td className="col-target text-cell">{item.instrument_or_target}</td>
                  <td className="col-action text-cell">{item.check_or_task_action}</td>
                  <td className="col-criteria text-cell">{item.pass_fail_criteria ?? item.completion_condition ?? '-'}</td>
                  <td className="col-result">
                    <select
                      value={item.result}
                      disabled={pendingKey === `result-${seq}`}
                      onChange={(event) => onPatch(seq, 'result', event.target.value, `result-${seq}`)}
                    >
                      {(Object.keys(RESULT_LABELS) as ChecklistResult[]).map((value) => (
                        <option key={value} value={value}>{RESULT_LABELS[value]}</option>
                      ))}
                    </select>
                  </td>
                  <td className="col-value">
                    <InspectionTextCell
                      value={item.measured_before ?? ''}
                      disabled={pendingKey === `measured_before-${seq}`}
                      onCommit={(value) => onPatch(seq, 'measured_before', value, `measured_before-${seq}`)}
                    />
                  </td>
                  <td className="col-value">
                    <InspectionTextCell
                      value={item.measured_after ?? ''}
                      disabled={pendingKey === `measured_after-${seq}`}
                      onCommit={(value) => onPatch(seq, 'measured_after', value, `measured_after-${seq}`)}
                    />
                  </td>
                  <td className="col-inspector">
                    <InspectionTextCell
                      value={item.checked_by ?? ''}
                      disabled={pendingKey === `checked_by-${seq}`}
                      onCommit={(value) => onPatch(seq, 'checked_by', value, `checked_by-${seq}`)}
                    />
                  </td>
                  <td className="col-note">
                    <InspectionTextCell
                      value={item.note ?? ''}
                      disabled={pendingKey === `note-${seq}`}
                      onCommit={(value) => onPatch(seq, 'note', value, `note-${seq}`)}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function InspectionTextCell({
  value,
  disabled,
  onCommit,
}: {
  readonly value: string
  readonly disabled: boolean
  readonly onCommit: (value: string) => void
}) {
  const [draft, setDraft] = useState(value)
  return (
    <input
      type="text"
      value={draft}
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        if (draft !== value) onCommit(draft)
      }}
    />
  )
}
