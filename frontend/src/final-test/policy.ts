import type { AgentRunListItem, AnomalyReportArtifact, WorkOrderStructuredContent } from '../api/contracts'

export const FINAL_TEST_ANALYSIS_DELAY_MS = 3_000

export function finalTestCompletionAt(requestedAt: string): number {
  return Date.parse(requestedAt) + FINAL_TEST_ANALYSIS_DELAY_MS
}

export function finalTestReadyAt(requestedAt: string): string {
  return new Date(finalTestCompletionAt(requestedAt)).toISOString()
}

export interface FinalTestPriorityView {
  readonly level: 'urgent' | 'high'
  readonly label: '긴급' | '경고'
  readonly tone: 'critical' | 'warning'
}

export function finalTestPriorityForRoom(substationId: number): FinalTestPriorityView {
  return substationId === 1 || substationId === 10
    ? { level: 'urgent', label: '긴급', tone: 'critical' }
    : { level: 'high', label: '경고', tone: 'warning' }
}

export function normalizeFinalTestDisplayText(value: string): string {
  return value.replaceAll('변전소', '기계실')
}

export function normalizeFinalTestChatText(value: string): string {
  return normalizeFinalTestDisplayText(value)
    .replaceAll('시연 데이터', '데이터')
    .replaceAll('시연 챗봇', '챗봇')
    .replaceAll('시연 자료', '자료')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function withFinalTestDisplayText(content: WorkOrderStructuredContent): WorkOrderStructuredContent {
  return {
    ...content,
    header: {
      ...content.header,
      priority: content.header.priority,
      target_building: normalizeFinalTestDisplayText(content.header.target_building),
      equipment_type: normalizeFinalTestDisplayText(content.header.equipment_type),
      work_type: normalizeFinalTestDisplayText(content.header.work_type),
      issue_reason: content.header.issue_reason == null ? undefined : normalizeFinalTestDisplayText(content.header.issue_reason),
    },
    purpose: normalizeFinalTestDisplayText(content.purpose),
    risk_and_evidence: normalizeFinalTestDisplayText(content.risk_and_evidence),
    restriction_or_prep_checklist: content.restriction_or_prep_checklist.map((item) => ({ ...item, label: normalizeFinalTestDisplayText(item.label) })),
    checklist: content.checklist.map((item) => ({
      ...item,
      instrument_or_target: normalizeFinalTestDisplayText(item.instrument_or_target),
      check_or_task_action: normalizeFinalTestDisplayText(item.check_or_task_action),
      pass_fail_criteria: item.pass_fail_criteria == null ? null : normalizeFinalTestDisplayText(item.pass_fail_criteria),
      completion_condition: item.completion_condition == null ? null : normalizeFinalTestDisplayText(item.completion_condition),
    })),
    outcome_and_followup: normalizeFinalTestDisplayText(content.outcome_and_followup),
    safety_permit_precheck: {
      ...content.safety_permit_precheck,
      questions: content.safety_permit_precheck.questions.map((item) => ({ ...item, question: normalizeFinalTestDisplayText(item.question), required_action: item.required_action == null ? null : normalizeFinalTestDisplayText(item.required_action) })),
    },
    disclaimer: normalizeFinalTestDisplayText(content.disclaimer),
  }
}

function objectRecord(value: unknown): Readonly<Record<string, unknown>> | null {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return null
  return Object.fromEntries(Object.entries(value))
}

function normalizeReportSection(section: Readonly<Record<string, unknown>>): Readonly<Record<string, unknown>> {
  return Object.fromEntries(Object.entries(section).map(([key, value]) => [key, typeof value === 'string' ? normalizeFinalTestDisplayText(value) : value]))
}

export function withFinalTestReportDisplayText(report: AnomalyReportArtifact): AnomalyReportArtifact {
  const next: Record<string, unknown> = {}
  Object.entries(report).forEach(([key, value]) => {
    const record = objectRecord(value)
    if (record != null) next[key] = normalizeReportSection(record)
    else if (Array.isArray(value)) next[key] = value.map((item) => {
      const itemRecord = objectRecord(item)
      return itemRecord == null ? item : normalizeReportSection(itemRecord)
    })
    else next[key] = typeof value === 'string' ? normalizeFinalTestDisplayText(value) : value
  })
  return next
}

export function finalTestRunPriority(item: AgentRunListItem): FinalTestPriorityView {
  return finalTestPriorityForRoom(item.substation_id ?? 30)
}
