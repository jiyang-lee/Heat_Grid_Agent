import type { BooleanChecklistItem } from '../../api/contracts'

interface Props {
  readonly title: string
  readonly items: readonly BooleanChecklistItem[]
  readonly pendingIndex: number | null
  readonly onToggle: (index: number, checked: boolean) => void
}

/** 작업 범위 및 제한사항을 체크형 목록으로 보여준다. */
export function RestrictionChecklist({ title, items, pendingIndex, onToggle }: Props) {
  return (
    <section className="work-order-card" aria-label={title}>
      <h4>{title}</h4>
      <ul className="work-order-boolean-checklist">
        {items.map((item, index) => (
          <li key={`${index}-${item.label}`}>
            <label>
              <input
                type="checkbox"
                checked={item.checked}
                disabled={pendingIndex === index}
                onChange={(event) => onToggle(index, event.target.checked)}
              />
              <span>{item.label}</span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}
