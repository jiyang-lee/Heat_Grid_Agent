import type { IncidentDocumentContent, WorkOrderChecklistItem, WorkOrderStructuredContent } from '../../api/contracts'
import { isWorkOrderStructuredContent } from '../../api/contracts'

/** 구조화 작업지시서를 기존 제목/본문 뷰(legacy IncidentDocumentContent 형태)로 변환한다. */
export function legacyViewOfContent(
  content: IncidentDocumentContent | WorkOrderStructuredContent,
): IncidentDocumentContent {
  if (!isWorkOrderStructuredContent(content)) return content
  return {
    title: `${content.header.work_type} 작업지시서 · ${content.header.equipment_type}`,
    body: renderWorkOrderMarkdown(content),
    actions: activeChecklist(content).map((item) => item.check_or_task_action),
    evidence: [],
    safety_notes: content.restriction_or_prep_checklist.map((item) => item.label).join('\n'),
  }
}

export function activeChecklist(content: WorkOrderStructuredContent): readonly WorkOrderChecklistItem[] {
  return content.checklist.length > 0 ? content.checklist : content.commissioning_checklist
}

export function renderWorkOrderMarkdown(content: WorkOrderStructuredContent): string {
  const checklist = activeChecklist(content)
  const evidenceDetailLines = checklist.map((item) => `- ${item.instrument_or_target}: ${item.pass_fail_criteria ?? item.completion_condition ?? ''}`.replace(/:\s*$/, ''))
  const actionLines = checklist.length > 0
    ? checklist.map((item, index) => `${index + 1}. ${item.check_or_task_action}${item.pass_fail_criteria ? ` (판정기준: ${item.pass_fail_criteria})` : ''}`)
    : ['1. 현장 확인이 필요합니다.']
  const safetyLines = content.restriction_or_prep_checklist.length > 0
    ? content.restriction_or_prep_checklist.map((item, index) => `${index + 1}. ${item.label}`)
    : ['1. 현장 안전 절차를 준수합니다.']
  return [
    `${content.header.work_type} 작업지시서 · ${content.header.equipment_type}`,
    '',
    '작업 목적',
    content.purpose,
    '',
    '위험성 및 근거',
    content.risk_and_evidence,
    ...(evidenceDetailLines.length > 0 ? ['', ...evidenceDetailLines] : []),
    '',
    '작업 절차',
    ...actionLines,
    '',
    '안전 확인',
    ...safetyLines,
    '',
    '판정 및 후속 조치',
    content.outcome_and_followup,
  ].join('\n')
}
