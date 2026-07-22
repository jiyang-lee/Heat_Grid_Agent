import { useState, type ReactNode } from 'react'
import { Icon } from '../icons'

interface Props {
  readonly children: ReactNode
  readonly label?: string
}

export function WorkOrderHoverRail({ children, label = '작업지시서 목록' }: Props) {
  const [open, setOpen] = useState(false)

  return <aside className={`work-order-hover-rail${open ? ' is-open' : ''}`}>
    <button aria-expanded={open} aria-label={label} className="work-order-hover-rail-trigger" onClick={() => setOpen(true)} onFocus={() => setOpen(true)} type="button">
      <Icon name="menu" />
      <span>목록</span>
    </button>
    <div className="work-order-hover-rail-panel" onClick={() => setOpen(false)} tabIndex={-1}>
      <h2>{label}</h2>
      {children}
    </div>
  </aside>
}
