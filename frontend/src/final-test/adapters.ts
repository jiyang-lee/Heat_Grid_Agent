import type { AgentRunListItem, AnomalyReportArtifact, WorkOrderStructuredContent } from '../api/contracts'
import type { AgentAnalysisQueueEntry } from '../console/AgentAnalysisProgress'
import type { FinalTestDemoPackage, FinalTestDemoPackageSummary } from './contracts'

function roomLabel(substationId: number): string {
  return `기계실 ${substationId}`
}

function normalizedDate(value: string | undefined): string | null {
  if (value == null || value.trim() === '') return null
  const match = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) KST$/.exec(value)
  const normalized = match == null ? value : `${match[1]}T${match[2]}:00+09:00`
  return Number.isNaN(Date.parse(normalized)) ? null : normalized
}

function dateValue(value: string | undefined, fallback: string): string {
  return normalizedDate(value) ?? normalizedDate(fallback) ?? '2000-01-01T00:00:00+09:00'
}

function dateLabel(value: string | undefined): string {
  return normalizedDate(value) ?? '확인 필요'
}

function workOrderReason(pkg: FinalTestDemoPackage): string {
  return pkg.work_order_document.summary ?? `${pkg.fault_label} 현장 점검이 필요합니다.`
}

export function workOrderContentFor(pkg: FinalTestDemoPackage): WorkOrderStructuredContent {
  const document = pkg.work_order_document
  const steps = document.steps ?? []
  const safety = document.safety ?? []
  const criteria = document.completion_criteria ?? []
  const issueReason = workOrderReason(pkg)
  return {
    work_order_kind: 'site_check',
    header: {
      document_number: document.header?.work_order_number ?? `WO-FINAL-${String(pkg.substation_id).padStart(3, '0')}`,
      issued_at: dateValue(document.header?.issued_at, pkg.fault_payload.captured_at),
      priority: document.header?.priority ?? '긴급',
      assignee: document.approval?.approved_by ?? null,
      target_building: pkg.facility_name,
      mechanical_room: String(pkg.substation_id),
      equipment_type: pkg.fault_label,
      work_type: '고장 현장 점검 및 부하 안정화',
      issue_reason: issueReason,
      status: document.status,
    },
    purpose: issueReason,
    risk_and_evidence: `${pkg.fault_label} · 우선순위 ${pkg.fault_payload.priority.score.toFixed(1)}점 · ${pkg.fault_payload.priority.reason}`,
    restriction_or_prep_checklist: safety.map((item) => ({ label: item, checked: false })),
    checklist: steps.map((step, index) => ({
      seq: step.order,
      instrument_or_target: step.title,
      check_or_task_action: step.detail,
      pass_fail_criteria: criteria[index] ?? criteria.at(-1) ?? null,
      parts_or_tools: null,
      completion_condition: criteria[index] ?? null,
      result: 'pending',
      measured_before: null,
      measured_after: null,
      checked_by: null,
      signature: null,
      note: null,
    })),
    commissioning_checklist: [],
    outcome_and_followup: criteria.length > 0 ? `완료 기준: ${criteria.join(' · ')}` : '현장 점검 결과와 복구 상태를 운영자에게 보고합니다.',
    safety_permit_precheck: {
      questions: safety.map((item) => ({ question: item, applicable: true, required_action: item })),
      permit_required: true,
    },
    disclaimer: '본 시연 산출물은 운영자 검토와 현장 승인 전제의 사전 승인본입니다.',
  }
}

export function reportArtifactFor(pkg: FinalTestDemoPackage): AnomalyReportArtifact {
  const document = pkg.report_document
  const sections = document.sections ?? []
  const sensors = pkg.fault_payload.sensors
  const actions = sections.map((item) => ({
    action: item.body,
    urgency: '즉시',
    owner_hint: '현장 운영자',
  }))
  return {
    report_metadata: {
      report_id: document.header?.report_number ?? document.document_id,
      generated_at: dateLabel(pkg.fault_payload.captured_at),
      source_card_id: pkg.alert_id,
    },
    target_asset: {
      asset_label: pkg.fault_label,
      configuration_type: '열원·순환 계통',
      window_start: dateLabel(pkg.normal_payload.captured_at),
      window_end: dateLabel(pkg.fault_payload.captured_at),
    },
    priority_summary: {
      priority_level: pkg.fault_payload.priority.level,
      priority_score: pkg.fault_payload.priority.score,
      priority_reason: pkg.fault_payload.priority.reason,
      urgency: '즉시',
      operator_review: document.status === 'approved' ? '승인 완료' : '검토 필요',
      confidence: '사전 검증 데이터',
    },
    situation_summary: {
      current_status: pkg.fault_label,
      headline: document.executive_summary ?? pkg.fault_label,
      summary: document.executive_summary ?? pkg.fault_label,
      impact_summary: document.conclusion ?? '완료 기준 확인 전까지 긴급 상태를 유지합니다.',
    },
    key_evidence: sensors.map((sensor) => ({
      label: sensor.label,
      current_value: `${sensor.value}${sensor.unit}`,
      value: sensor.value,
      data_status: sensor.status === 'critical' ? '임계 초과' : sensor.status === 'warning' ? '주의' : '정상',
      judgement: sensor.status === 'critical' ? '즉시 점검' : '추세 확인',
      interpretation: `${sensor.label} ${sensor.value}${sensor.unit}가 시연 고장 묶음에 기록되었습니다.`,
    })),
    risk_analysis: {
      risk_level: pkg.fault_payload.priority.level,
      risk_summary: pkg.fault_payload.priority.reason,
    },
    recommended_actions: actions,
    conclusion: document.conclusion,
  }
}

export function demoMachineRoom(pkg: FinalTestDemoPackage): string {
  return roomLabel(pkg.substation_id)
}

export function finalTestRunItem(summary: FinalTestDemoPackageSummary, entry: AgentAnalysisQueueEntry, now = Date.now()): AgentRunListItem {
  const requestedAt = Date.parse(entry.requestedAt)
  const readyAt = Date.parse(entry.readyAt ?? '') || requestedAt + 5_000
  const completed = now >= readyAt
  const status = completed ? 'completed' : 'running'
  return {
    run_id: entry.runId,
    status,
    alert_id: summary.alert_id,
    card_id: summary.demo_id,
    priority: 'high',
    operator_review_status: 'pending',
    worker_status: completed ? 'completed' : 'running',
    review_snapshot_status: completed ? 'available' : 'pending',
    created_at: entry.requestedAt,
    updated_at: completed ? new Date(readyAt).toISOString() : entry.requestedAt,
    manufacturer_id: null,
    substation_id: summary.substation_id,
    substation_uid: `final-test-${summary.substation_id}`,
    alert_reason: summary.fault_label,
    current_stage: completed ? null : 'fault_analysis',
    has_result: completed,
    report_artifact_count: completed ? 1 : 0,
    latest_report_name: completed ? 'AI 이상 분석 보고서' : null,
  }
}
