import type { AnomalyReportArtifact, WorkOrderStructuredContent } from '../api/contracts'
import type { FinalTestDemoPackage } from './contracts'
import { reportArtifactFor, workOrderContentFor } from './adapters'
import { FINAL_TEST_PRESENTATION_STORAGE_KEY } from './session'

export interface FinalTestWorkOrderVersion {
  readonly version: number
  readonly content: WorkOrderStructuredContent
}

export interface FinalTestReportVersion {
  readonly version: number
  readonly artifact: AnomalyReportArtifact
}

export interface PresentationState {
  readonly workOrderAccepted: boolean
  readonly reportReady: boolean
  readonly reportApproved: boolean
  readonly acceptedWorkOrderVersion?: number
  readonly currentWorkOrderVersion?: number
  readonly approvedReportVersion?: number
  readonly currentReportVersion?: number
  readonly workOrderVersions?: readonly FinalTestWorkOrderVersion[]
  readonly selectedWorkOrderVersion?: number
  readonly reportVersions?: readonly FinalTestReportVersion[]
  readonly selectedReportVersion?: number
  readonly activeTab?: 'execution' | 'orders' | 'reports'
}

export const EMPTY_PRESENTATION: PresentationState = { workOrderAccepted: false, reportReady: false, reportApproved: false }

function record(value: unknown): Readonly<Record<string, unknown>> | null {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return null
  return Object.fromEntries(Object.entries(value))
}

function numberValue(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0
}

function isWorkOrderVersion(value: unknown): value is FinalTestWorkOrderVersion {
  const item = record(value)
  const content = record(item?.content)
  return item != null && numberValue(item.version) && content != null && typeof content.work_order_kind === 'string' && record(content.header) != null && typeof content.purpose === 'string' && typeof content.risk_and_evidence === 'string' && Array.isArray(content.checklist)
}

function isReportVersion(value: unknown): value is FinalTestReportVersion {
  const item = record(value)
  return item != null && numberValue(item.version) && record(item.artifact) != null
}

function isPresentationState(value: unknown): value is PresentationState {
  const item = record(value)
  return item != null
    && typeof item.workOrderAccepted === 'boolean'
    && typeof item.reportReady === 'boolean'
    && typeof item.reportApproved === 'boolean'
    && (item.acceptedWorkOrderVersion == null || numberValue(item.acceptedWorkOrderVersion))
    && (item.currentWorkOrderVersion == null || numberValue(item.currentWorkOrderVersion))
    && (item.approvedReportVersion == null || numberValue(item.approvedReportVersion))
    && (item.currentReportVersion == null || numberValue(item.currentReportVersion))
    && (item.activeTab == null || item.activeTab === 'execution' || item.activeTab === 'orders' || item.activeTab === 'reports')
    && (item.workOrderVersions == null || Array.isArray(item.workOrderVersions) && item.workOrderVersions.every(isWorkOrderVersion))
    && (item.reportVersions == null || Array.isArray(item.reportVersions) && item.reportVersions.every(isReportVersion))
}

export function loadPresentation(): Readonly<Record<string, PresentationState>> {
  try {
    const parsed: unknown = JSON.parse(window.sessionStorage.getItem(FINAL_TEST_PRESENTATION_STORAGE_KEY) ?? '{}')
    const root = record(parsed)
    if (root == null) return {}
    return Object.fromEntries(Object.entries(root).filter((entry): entry is [string, PresentationState] => isPresentationState(entry[1])))
  } catch {
    return {}
  }
}

export function savePresentation(value: Readonly<Record<string, PresentationState>>): void {
  try {
    window.sessionStorage.setItem(FINAL_TEST_PRESENTATION_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // The workflow remains usable without session persistence.
  }
}

export function workOrderVersionsFor(state: PresentationState, pkg: FinalTestDemoPackage): readonly FinalTestWorkOrderVersion[] {
  if (state.workOrderVersions?.length) return state.workOrderVersions
  return pkg.work_order_versions?.length
    ? pkg.work_order_versions.map((item) => ({ version: item.version, content: workOrderContentFor(pkg, item.document) }))
    : [{ version: 1, content: workOrderContentFor(pkg) }]
}

export function reportVersionsFor(state: PresentationState, pkg: FinalTestDemoPackage): readonly FinalTestReportVersion[] {
  if (state.reportVersions?.length) return state.reportVersions
  return pkg.report_versions?.length
    ? pkg.report_versions.map((item) => ({ version: item.version, artifact: reportArtifactFor(pkg, item.document) }))
    : [{ version: 1, artifact: reportArtifactFor(pkg) }]
}

export function selectedVersion<T extends { readonly version: number }>(versions: readonly T[], requested: number | undefined): T {
  const selected = versions.find((item) => item.version === requested)
  return selected ?? versions[0]
}

export function nextVersion<T extends { readonly version: number }>(versions: readonly T[]): number | null {
  const latest = versions[versions.length - 1]?.version ?? 1
  return latest >= 3 ? null : latest + 1
}
