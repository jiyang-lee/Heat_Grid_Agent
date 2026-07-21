import { useState } from 'react'
import type { ChecklistResult, WorkOrderChecklistItem, WorkOrderPatchSection, WorkOrderStructuredContent } from '../../api/contracts'
import { usePatchWorkOrderField } from '../../api/hooks'
import { activeChecklist } from './workOrderStructuredView'

interface Props {
  readonly incidentId: string
  readonly version: number
  readonly content: WorkOrderStructuredContent
}

const RESULT_LABELS: Record<ChecklistResult, string> = {
  pass: '적합',
  fail: '조치 필요',
  not_applicable: '해당 없음',
  pending: '미점검',
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** 구조화 작업지시서(현장확인/정비)의 체크리스트를 필드 단위로 직접 편집하는 패널. */
export function WorkOrderStructuredPanel({ incidentId, version, content }: Props) {
  const patchField = usePatchWorkOrderField()
  const [pendingKey, setPendingKey] = useState<string | null>(null)
  const [patchError, setPatchError] = useState<string | null>(null)

  const checklistSection = content.checklist.length > 0 ? 'checklist' as const : 'commissioning_checklist' as const
  const checklist = activeChecklist(content)

  const patch = async (
    targetSection: WorkOrderPatchSection,
    targetSeq: number,
    targetField: string,
    newValue: string,
    key: string,
  ) => {
    setPendingKey(key)
    setPatchError(null)
    try {
      await patchField.mutateAsync({
        incidentId,
        version,
        body: {
          expected_version: version,
          edited_by: 'ops-manager',
          idempotency_key: requestId(`work-order-field-${key}`),
          target_section: targetSection,
          target_seq: targetSeq,
          target_field: targetField,
          new_value: newValue,
        },
      })
    } catch {
      setPatchError('필드를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setPendingKey(null)
    }
  }

  return (
    <div className="work-order-structured-panel">
      <p className="work-order-structured-disclaimer">{content.disclaimer}</p>
      {patchError && <p className="form-error" role="alert">{patchError}</p>}

      <section aria-label="작업 목적">
        <h4>작업 목적</h4>
        <WorkOrderTextField
          value={content.purpose}
          disabled={pendingKey === 'purpose'}
          onCommit={(value) => void patch('purpose', 1, 'text', value, 'purpose')}
        />
      </section>

      <section aria-label="위험성 및 근거">
        <h4>위험성 및 근거</h4>
        <WorkOrderTextField
          value={content.risk_and_evidence}
          disabled={pendingKey === 'risk_and_evidence'}
          onCommit={(value) => void patch('risk_and_evidence', 1, 'text', value, 'risk_and_evidence')}
        />
      </section>

      <section aria-label={content.work_order_kind === 'site_check' ? '작업 및 제한사항' : '사전 준비 및 안전조치'}>
        <h4>{content.work_order_kind === 'site_check' ? '작업 및 제한사항' : '사전 준비 및 안전조치'}</h4>
        <ul className="work-order-boolean-checklist">
          {content.restriction_or_prep_checklist.map((item, index) => {
            const key = `prep-${index}`
            return (
              <li key={key}>
                <label>
                  <input
                    type="checkbox"
                    checked={item.checked}
                    disabled={pendingKey === key}
                    onChange={(event) => void patch('restriction_or_prep_checklist', index + 1, 'checked', event.target.checked ? 'true' : 'false', key)}
                  />
                  {item.label}
                </label>
              </li>
            )
          })}
        </ul>
      </section>

      <section aria-label={content.work_order_kind === 'site_check' ? '현장 확인 항목' : '작업 세부 및 시운전 확인'}>
        <h4>{content.work_order_kind === 'site_check' ? '현장 확인 항목' : '작업 세부'}</h4>
        <WorkOrderChecklistTable
          items={checklist}
          onPatch={(seq, field, value, key) => void patch(checklistSection, seq, field, value, key)}
          pendingKey={pendingKey}
        />
      </section>

      <section aria-label="안전작업허가 필요성 사전 확인">
        <h4>안전작업허가 필요성 사전 확인</h4>
        {content.safety_permit_precheck.permit_required && (
          <p className="work-order-permit-banner" role="alert">해당 항목이 있어 별도 안전작업허가서 발급이 필요합니다.</p>
        )}
        <table className="work-order-safety-permit-table">
          <thead>
            <tr>
              <th>판정 질문</th>
              <th>해당 여부</th>
              <th>필요 안전조치</th>
            </tr>
          </thead>
          <tbody>
            {content.safety_permit_precheck.questions.map((question, index) => {
              const key = `permit-${index}`
              return (
                <tr key={key}>
                  <td>{question.question}</td>
                  <td>
                    <label>
                      <input
                        type="checkbox"
                        checked={question.applicable}
                        disabled={pendingKey === key}
                        onChange={(event) => void patch('safety_permit_precheck', index + 1, 'applicable', event.target.checked ? 'true' : 'false', key)}
                      />
                      해당
                    </label>
                  </td>
                  <td>{question.required_action ?? '-'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      <section aria-label="판정 및 후속 조치">
        <h4>판정 및 후속 조치</h4>
        <WorkOrderTextField
          value={content.outcome_and_followup}
          disabled={pendingKey === 'outcome_and_followup'}
          onCommit={(value) => void patch('outcome_and_followup', 1, 'text', value, 'outcome_and_followup')}
        />
      </section>
    </div>
  )
}

function WorkOrderTextField({
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
    <textarea
      className="work-order-text-field"
      value={draft}
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        const trimmed = draft.trim()
        if (trimmed && trimmed !== value) onCommit(trimmed)
      }}
    />
  )
}

function WorkOrderChecklistTable({
  items,
  onPatch,
  pendingKey,
}: {
  readonly items: readonly WorkOrderChecklistItem[]
  readonly onPatch: (seq: number, field: string, value: string, key: string) => void
  readonly pendingKey: string | null
}) {
  return (
    <div className="work-order-checklist-table-wrap">
      <table className="work-order-checklist-table">
        <thead>
          <tr>
            <th>번호</th>
            <th>계기·대상</th>
            <th>확인 작업</th>
            <th>판정기준</th>
            <th>결과</th>
            <th>측정값(전)</th>
            <th>측정값(후)</th>
            <th>점검자</th>
            <th>비고</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const seq = item.seq
            return (
              <tr key={seq}>
                <td>{seq}</td>
                <td>{item.instrument_or_target}</td>
                <td>{item.check_or_task_action}</td>
                <td>{item.pass_fail_criteria ?? item.completion_condition ?? '-'}</td>
                <td>
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
                <td>
                  <ChecklistTextCell
                    value={item.measured_before ?? ''}
                    disabled={pendingKey === `measured_before-${seq}`}
                    onCommit={(value) => onPatch(seq, 'measured_before', value, `measured_before-${seq}`)}
                  />
                </td>
                <td>
                  <ChecklistTextCell
                    value={item.measured_after ?? ''}
                    disabled={pendingKey === `measured_after-${seq}`}
                    onCommit={(value) => onPatch(seq, 'measured_after', value, `measured_after-${seq}`)}
                  />
                </td>
                <td>
                  <ChecklistTextCell
                    value={item.checked_by ?? ''}
                    disabled={pendingKey === `checked_by-${seq}`}
                    onCommit={(value) => onPatch(seq, 'checked_by', value, `checked_by-${seq}`)}
                  />
                </td>
                <td>
                  <ChecklistTextCell
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
  )
}

function ChecklistTextCell({
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
