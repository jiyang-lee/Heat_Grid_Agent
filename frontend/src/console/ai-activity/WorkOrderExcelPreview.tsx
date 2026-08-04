import { useState } from 'react'
import type { DocumentStatus, WorkOrderStructuredContent } from '../../api/contracts'
import { Icon } from '../icons'

interface Props {
  readonly content: WorkOrderStructuredContent
  readonly version: number
  readonly status?: DocumentStatus
}

const zoomLevels = [75, 90, 100, 110, 125] as const

const statusLabels: Record<DocumentStatus, string> = {
  draft: '검토 중',
  ai_reviewed: 'AI 검토 완료',
  approved: '최종 승인',
  failed: '생성 실패',
}

function roomLabel(value: string | null): string {
  if (value == null || value.trim() === '') return '기계실'
  return value.startsWith('기계실') ? value : `기계실 ${value}`
}

export function WorkOrderExcelPreview({ content, status, version }: Props) {
  const [zoomIndex, setZoomIndex] = useState(2)
  const room = roomLabel(content.header.mechanical_room)
  const checklist = content.checklist.length > 0 ? content.checklist : content.commissioning_checklist
  const issueReason = content.header.issue_reason ?? content.risk_and_evidence
  const statusLabel = status == null ? content.header.status ?? '검토 중' : statusLabels[status]
  const zoom = zoomLevels[zoomIndex]
  return <div className="work-order-document-viewer">
    <div className="work-order-viewer-toolbar" role="toolbar" aria-label="문서 보기 도구">
      <button aria-label="축소" disabled={zoomIndex === 0} onClick={() => setZoomIndex((current) => Math.max(0, current - 1))} title="축소" type="button"><Icon name="minus" /></button>
      <output aria-label="확대 비율">{zoom}%</output>
      <button aria-label="확대" disabled={zoomIndex === zoomLevels.length - 1} onClick={() => setZoomIndex((current) => Math.min(zoomLevels.length - 1, current + 1))} title="확대" type="button"><Icon name="plus" /></button>
      <button aria-label="너비 맞춤" onClick={() => setZoomIndex(2)} title="너비 맞춤" type="button"><Icon name="expand" /></button>
      <span>1 / 1</span>
    </div>
    <div className="work-order-viewer-viewport">
    <article className={`work-order-excel-preview work-order-zoom-${zoom}`} aria-label="Excel 양식 작업지시서 미리보기">
    <header className="work-order-excel-heading">
      <div><span>현장 확인 작업지시서</span><h2>{content.header.equipment_type}</h2></div>
      <strong>v{version}</strong>
    </header>
    <dl className="work-order-excel-meta">
      <div><dt>문서번호</dt><dd>{content.header.document_number}</dd></div>
      <div><dt>발행일시</dt><dd>{new Date(content.header.issued_at).toLocaleString('ko-KR')}</dd></div>
      <div><dt>상태</dt><dd>{statusLabel}</dd></div>
      <div><dt>대상건물</dt><dd>{content.header.target_building}</dd></div>
      <div><dt>기계실</dt><dd>{room}</dd></div>
      <div><dt>대상설비</dt><dd>{content.header.equipment_type}</dd></div>
      <div className="work-order-excel-meta-wide"><dt>발행 사유</dt><dd>{issueReason}</dd></div>
      <div><dt>작업 유형</dt><dd>{content.header.work_type}</dd></div>
    </dl>
    <section>
      <h3>1. 작업 목적</h3>
      <p>{content.purpose}{'\n\n'}{content.risk_and_evidence}</p>
    </section>
    <section>
      <h3>2. 작업 전 확인사항</h3>
      <ul className="work-order-excel-safety">
        {content.restriction_or_prep_checklist.map((item) => <li key={item.label}>{item.label}</li>)}
      </ul>
    </section>
    <section className="work-order-excel-checks">
      <h3>3. 현장 확인 절차</h3>
      <div className="work-order-excel-table-wrap">
        <table>
          <thead><tr><th>번호</th><th>대상</th><th>확인 작업</th><th>판정 기준</th><th>결과</th><th>측정값/현상</th><th>비고</th></tr></thead>
          <tbody>{checklist.map((item) => <tr key={item.seq}><td>{item.seq}</td><td>{item.instrument_or_target}</td><td>{item.check_or_task_action}</td><td>{item.pass_fail_criteria ?? item.completion_condition ?? ''}</td><td /><td /><td /></tr>)}</tbody>
        </table>
      </div>
    </section>
    <footer>{content.outcome_and_followup}</footer>
  </article>
  </div>
  </div>
}
