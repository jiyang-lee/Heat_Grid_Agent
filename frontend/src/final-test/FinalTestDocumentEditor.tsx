import { useState } from 'react'
import type { AnomalyReportArtifact, WorkOrderStructuredContent } from '../api/contracts'
import { Button } from '../console/ui'

interface WorkOrderEditorProps {
  readonly content: WorkOrderStructuredContent
  readonly onCancel: () => void
  readonly onSave: (content: WorkOrderStructuredContent) => void
}

export function FinalTestWorkOrderEditor({ content, onCancel, onSave }: WorkOrderEditorProps) {
  const [purpose, setPurpose] = useState(content.purpose)
  const [riskAndEvidence, setRiskAndEvidence] = useState(content.risk_and_evidence)
  const [outcome, setOutcome] = useState(content.outcome_and_followup)
  const [editNote, setEditNote] = useState('운영자 직접 편집')
  const canSave = purpose.trim() !== '' && riskAndEvidence.trim() !== '' && outcome.trim() !== '' && editNote.trim() !== ''
  const save = () => {
    if (!canSave) return
    onSave({
      ...content,
      purpose: purpose.trim(),
      risk_and_evidence: riskAndEvidence.trim(),
      outcome_and_followup: `${outcome.trim()}\n\n수정 사유: ${editNote.trim()}`,
    })
  }
  return <div className="work-order-manual-editor final-test-document-editor">
    <p className="work-order-chat-context-note">원본 v1은 보존되고 저장 시 시연 세션 전용 새 버전이 생성됩니다.</p>
    <label><span>작업 목적</span><textarea aria-label="작업 목적 편집" className="scenario-document-editor" onChange={(event) => setPurpose(event.target.value)} value={purpose} /></label>
    <label><span>위험성·근거</span><textarea aria-label="위험성·근거 편집" className="scenario-document-editor" onChange={(event) => setRiskAndEvidence(event.target.value)} value={riskAndEvidence} /></label>
    <label><span>후속 조치</span><textarea aria-label="후속 조치 편집" className="scenario-document-editor" onChange={(event) => setOutcome(event.target.value)} value={outcome} /></label>
    <label><span>수정 사유</span><input aria-label="수정 사유 편집" onChange={(event) => setEditNote(event.target.value)} value={editNote} /></label>
    <div className="final-test-editor-actions"><Button onClick={onCancel}>취소</Button><Button disabled={!canSave} icon="check" onClick={save} tone="primary">새 버전으로 저장</Button></div>
  </div>
}

interface ReportEditorProps {
  readonly report: AnomalyReportArtifact
  readonly onCancel: () => void
  readonly onSave: (report: AnomalyReportArtifact) => void
}

function reportSummary(report: AnomalyReportArtifact): string {
  const summary = report.situation_summary
  if (summary == null || typeof summary.summary !== 'string') return ''
  return summary.summary
}

export function FinalTestReportEditor({ report, onCancel, onSave }: ReportEditorProps) {
  const [summary, setSummary] = useState(reportSummary(report))
  const save = () => {
    if (!summary.trim()) return
    onSave({ ...report, situation_summary: { ...(report.situation_summary ?? {}), summary: summary.trim() } })
  }
  return <div className="work-order-manual-editor final-test-document-editor">
    <p className="work-order-chat-context-note">보고서 원본은 보존되고 저장 시 시연 세션 전용 새 버전이 생성됩니다.</p>
    <label><span>보고서 요약 본문</span><textarea aria-label="보고서 본문 편집" className="scenario-document-editor scenario-report-editor" onChange={(event) => setSummary(event.target.value)} value={summary} /></label>
    <div className="final-test-editor-actions"><Button onClick={onCancel}>취소</Button><Button disabled={!summary.trim()} icon="check" onClick={save} tone="primary">새 버전으로 저장</Button></div>
  </div>
}
