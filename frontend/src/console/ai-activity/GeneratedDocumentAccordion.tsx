import { useState } from 'react'

interface Props {
  readonly body: string
}

/** AI가 생성한 원문 전체를 기본적으로 숨기고, 펼쳤을 때만 보여준다. */
export function GeneratedDocumentAccordion({ body }: Props) {
  const [expanded, setExpanded] = useState(false)
  return (
    <section className="work-order-raw-accordion" aria-label="AI 생성 원문">
      <button
        type="button"
        className="work-order-raw-accordion-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span>AI 생성 원문 보기</span>
        <span className="work-order-raw-accordion-caret" aria-hidden="true">{expanded ? '▴' : '▾'}</span>
      </button>
      {expanded && <pre className="work-order-raw-accordion-body">{body}</pre>}
    </section>
  )
}
