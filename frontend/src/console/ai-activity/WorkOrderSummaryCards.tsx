interface Props {
  readonly targetFacility: string
  readonly actionCriteria: string
  readonly assignee: string
}

/** 대상 설비 · 조치 기준 · 담당을 동일 크기 카드로 보여주는 요약 영역. */
export function WorkOrderSummaryCards({ targetFacility, actionCriteria, assignee }: Props) {
  return (
    <div className="work-order-summary-cards">
      <div className="work-order-summary-card work-order-summary-card-facility">
        <span>대상 설비</span>
        <strong>{targetFacility}</strong>
      </div>
      <div className="work-order-summary-card work-order-summary-card-criteria">
        <span>조치 기준</span>
        <strong>{actionCriteria}</strong>
      </div>
      <div className="work-order-summary-card work-order-summary-card-assignee">
        <span>담당</span>
        <strong>{assignee}</strong>
      </div>
    </div>
  )
}
