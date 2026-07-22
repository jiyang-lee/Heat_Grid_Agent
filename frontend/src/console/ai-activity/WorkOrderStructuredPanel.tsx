import { useEffect, useState } from 'react'
import type { WorkOrderPatchSection, WorkOrderStructuredContent } from '../../api/contracts'
import { usePatchWorkOrderField } from '../../api/hooks'
import { activeChecklist } from './workOrderStructuredView'
import { RestrictionChecklist } from './RestrictionChecklist'
import { InspectionTable } from './InspectionTable'
import { SafetyPermitGrid } from './SafetyPermitGrid'
import type { SaveStatus } from './WorkOrderActionFooter'

interface Props {
  readonly incidentId: string
  readonly version: number
  readonly content: WorkOrderStructuredContent
  readonly onSaveStatusChange?: (status: SaveStatus, errorDetail: string | null) => void
}

function requestId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** 구조화 작업지시서(현장확인/정비)를 섹션 카드로 렌더링하고 필드 단위 직접 편집을 지원하는 패널. */
export function WorkOrderStructuredPanel({ incidentId, version, content, onSaveStatusChange }: Props) {
  const patchField = usePatchWorkOrderField()
  const [pendingKey, setPendingKey] = useState<string | null>(null)

  useEffect(() => () => onSaveStatusChange?.('idle', null), [onSaveStatusChange])

  const checklistSection = content.checklist.length > 0 ? 'checklist' as const : 'commissioning_checklist' as const
  const checklist = activeChecklist(content)
  const inspectionTitle = content.work_order_kind === 'site_check' ? '현장 확인 항목' : '작업 세부 항목'
  const restrictionTitle = content.work_order_kind === 'site_check' ? '작업 범위 및 제한사항' : '사전 준비 및 안전조치'

  const patch = async (
    targetSection: WorkOrderPatchSection,
    targetSeq: number,
    targetField: string,
    newValue: string,
    key: string,
  ) => {
    setPendingKey(key)
    onSaveStatusChange?.('saving', null)
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
      onSaveStatusChange?.('saved', null)
    } catch {
      onSaveStatusChange?.('error', '필드를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setPendingKey(null)
    }
  }

  return (
    <div className="work-order-structured-panel">
      <p className="work-order-structured-disclaimer">{content.disclaimer}</p>

      <section className="work-order-card" aria-label="상황 요약">
        <h4>상황 요약</h4>
        <WorkOrderTextField
          value={content.purpose}
          disabled={pendingKey === 'purpose'}
          onCommit={(value) => void patch('purpose', 1, 'text', value, 'purpose')}
        />
      </section>

      <section className="work-order-card" aria-label="위험성 및 근거">
        <h4>위험성 및 근거</h4>
        <WorkOrderTextField
          value={content.risk_and_evidence}
          disabled={pendingKey === 'risk_and_evidence'}
          onCommit={(value) => void patch('risk_and_evidence', 1, 'text', value, 'risk_and_evidence')}
        />
        {checklist.length > 0 && (
          <dl className="work-order-evidence-list">
            {checklist.map((item) => (
              <div key={item.seq}>
                <dt>{item.instrument_or_target}</dt>
                <dd>{item.pass_fail_criteria ?? item.completion_condition ?? '-'}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <RestrictionChecklist
        title={restrictionTitle}
        items={content.restriction_or_prep_checklist}
        pendingIndex={pendingKey?.startsWith('prep-') ? Number(pendingKey.slice(5)) : null}
        onToggle={(index, checked) => void patch('restriction_or_prep_checklist', index + 1, 'checked', checked ? 'true' : 'false', `prep-${index}`)}
      />

      <InspectionTable
        title={inspectionTitle}
        items={checklist}
        pendingKey={pendingKey}
        onPatch={(seq, field, value, key) => void patch(checklistSection, seq, field, value, key)}
      />

      <SafetyPermitGrid
        precheck={content.safety_permit_precheck}
        pendingIndex={pendingKey?.startsWith('permit-') ? Number(pendingKey.slice(7)) : null}
        onToggleApplicable={(index, applicable) => void patch('safety_permit_precheck', index + 1, 'applicable', applicable ? 'true' : 'false', `permit-${index}`)}
      />

      <section className="work-order-card" aria-label="현장 판정 및 후속 조치">
        <h4>현장 판정 및 후속 조치</h4>
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
