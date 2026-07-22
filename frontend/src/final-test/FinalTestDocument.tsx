import type { FinalTestDocument } from './contracts'

interface Props {
  readonly document: FinalTestDocument
}

function ListSection({ items, title }: { readonly items: readonly string[]; readonly title: string }) {
  return <section className="final-test-document-section"><h3>{title}</h3><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></section>
}

export function FinalTestDocumentView({ document }: Props) {
  return <article className="final-test-document" aria-label={`${document.title} 미리보기`}>
    <header>
      <div><span className="final-test-eyebrow">FINAL TEST · 사전 승인본</span><h2>{document.title}</h2></div>
      <span className="final-test-approved">승인 완료</span>
    </header>
    {document.header && <dl className="final-test-document-meta">{Object.entries(document.header).map(([key, value]) => <div className={`meta-${key}`} key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value}</dd></div>)}</dl>}
    {(document.summary ?? document.executive_summary) && <section className="final-test-document-lead"><h3>요약</h3><p>{document.summary ?? document.executive_summary}</p></section>}
    {document.risk && <ListSection items={document.risk} title="위험성 평가" />}
    {document.safety && <ListSection items={document.safety} title="필수 안전 절차" />}
    {document.steps && <section className="final-test-document-section"><h3>작업 절차</h3><ol className="final-test-step-list">{document.steps.map((step) => <li key={step.order}><span>{step.order}</span><div><strong>{step.title}</strong><p>{step.detail}</p></div></li>)}</ol></section>}
    {document.sections?.map((section) => <section className="final-test-document-section" key={section.heading}><h3>{section.heading}</h3><p>{section.body}</p></section>)}
    {document.completion_criteria && <ListSection items={document.completion_criteria} title="완료 기준" />}
    {document.conclusion && <section className="final-test-document-lead"><h3>결론</h3><p>{document.conclusion}</p></section>}
    {document.approval && <footer className="final-test-approval">{Object.entries(document.approval).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</footer>}
  </article>
}
