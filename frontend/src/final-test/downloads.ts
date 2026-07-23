import type { AnomalyReportArtifact, WorkOrderStructuredContent } from '../api/contracts'
import { reportDocumentsApi } from '../api/backend'
import type { FinalTestDemoPackage } from './contracts'
import { demoMachineRoom } from './adapters'
import { normalizeFinalTestDisplayText } from './policy'

function filePart(value: string): string {
  return normalizeFinalTestDisplayText(value).replace(/[^\p{L}\p{N}._-]+/gu, '-').replace(/^-+|-+$/g, '') || 'heatgrid'
}

function saveBrowserFile(data: BlobPart, type: string, fileName: string): void {
  const url = URL.createObjectURL(new Blob([data], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function downloadFinalTestWorkOrder(content: WorkOrderStructuredContent, pkg: FinalTestDemoPackage, version: number): Promise<void> {
  const ExcelJS = await import('exceljs')
  const workbook = new ExcelJS.Workbook()
  const sheet = workbook.addWorksheet('작업지시서')
  sheet.columns = [{ width: 22 }, { width: 72 }]
  sheet.addRows([
    ['문서번호', content.header.document_number],
    ['발행일시', content.header.issued_at],
    ['상태', content.header.status ?? '검토 중'],
    ['우선순위', content.header.priority],
    ['대상건물', content.header.target_building],
    ['기계실', `기계실 ${content.header.mechanical_room ?? pkg.substation_id}`],
    ['대상설비', content.header.equipment_type],
    ['작업 유형', content.header.work_type],
    [],
    ['작업 목적', content.purpose],
    ['위험성·근거', content.risk_and_evidence],
    ['작업 전 확인사항', content.restriction_or_prep_checklist.map((item) => item.label).join('\n')],
    ['후속 조치', content.outcome_and_followup],
    [],
    ['순번', '현장 확인 절차'],
    ...content.checklist.map((item) => [item.seq, `${item.instrument_or_target}: ${item.check_or_task_action} / ${item.pass_fail_criteria ?? item.completion_condition ?? ''}`]),
  ])
  const buffer = await workbook.xlsx.writeBuffer()
  saveBrowserFile(buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', `heatgrid-work-order-${filePart(demoMachineRoom(pkg))}-v${version}.xlsx`)
}

export async function downloadFinalTestReport(report: AnomalyReportArtifact, pkg: FinalTestDemoPackage, version: number, approved: boolean): Promise<void> {
  await reportDocumentsApi.download({
    report_context: report,
    alert_id: null,
    building_name: normalizeFinalTestDisplayText(pkg.facility_name),
    machine_room: demoMachineRoom(pkg),
    status_label: approved ? '최종 승인' : '검토 중',
    document_version: version,
  }, `heatgrid-ai-report-${filePart(demoMachineRoom(pkg))}-v${version}.docx`)
}
