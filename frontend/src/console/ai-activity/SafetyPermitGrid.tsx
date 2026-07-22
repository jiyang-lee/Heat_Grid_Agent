import type { SafetyPermitPrecheck } from '../../api/contracts'

interface Props {
  readonly precheck: SafetyPermitPrecheck
  readonly pendingIndex: number | null
  readonly onToggleApplicable: (index: number, applicable: boolean) => void
}

function cardTone(applicable: boolean): string {
  return applicable ? 'is-applicable' : 'is-not-applicable'
}

/** 안전작업허가 필요성 사전 확인을 2열 카드 그리드로 보여준다. */
export function SafetyPermitGrid({ precheck, pendingIndex, onToggleApplicable }: Props) {
  return (
    <section className="work-order-card" aria-label="안전작업허가 사전 확인">
      <h4>안전작업허가 사전 확인</h4>
      {precheck.permit_required && (
        <p className="work-order-permit-banner" role="alert">해당 항목이 있어 별도 안전작업허가서 발급이 필요합니다.</p>
      )}
      <div className="work-order-safety-permit-grid">
        {precheck.questions.map((question, index) => (
          <label key={`${index}-${question.question}`} className={`work-order-safety-permit-card ${cardTone(question.applicable)}`}>
            <div className="work-order-safety-permit-card-head">
              <input
                type="checkbox"
                checked={question.applicable}
                disabled={pendingIndex === index}
                onChange={(event) => onToggleApplicable(index, event.target.checked)}
              />
              <span>{question.applicable ? '해당' : '해당 없음'}</span>
            </div>
            <p className="work-order-safety-permit-question">{question.question}</p>
            <p className="work-order-safety-permit-action">필요 안전조치: {question.required_action ?? '-'}</p>
          </label>
        ))}
      </div>
    </section>
  )
}
