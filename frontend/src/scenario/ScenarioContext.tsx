import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ACTIVE_SCENARIO_ID, IMPROVEMENT_LABELS, SCENARIO_ALERTS, SCENARIO_INCIDENT_AT, scenarioAlertsAt, workOrderVersion } from './scenarioData'
import { ScenarioContext, type ScenarioContextValue } from './ScenarioContextDefinition'
import type {
  EntryMode,
  EvaluationCategory,
  ScenarioAiEntry,
  ScenarioAlert,
  ScenarioChatMessage,
  ScenarioDocumentGroup,
  ScenarioReportMessage,
  ScenarioReportStatus,
  ScenarioState,
  SensorPoint,
  WorkOrderSection,
  WorkOrderVersion,
} from './types'
import { useSensorStream } from './useSensorStream'
import type { OpsAgentResultV4 } from '../api/contracts'
import { clearStoredAiDocumentDrafts, mergeScenarioWorkOrder, type WorkOrderRevisionTarget } from './workOrderRevision'

export const SESSION_KEY = 'heatgrid:scenario-session'

export function clearScenarioSession(): void {
  window.sessionStorage.removeItem(SESSION_KEY)
  window.localStorage.removeItem('heatgrid:last-agent-run')
}
const DEFAULT_ALERT = SCENARIO_ALERTS[0]

function emptyReport(): ScenarioState['report'] {
  return { status: 'idle', createdAt: null, savedAt: null, completedAt: null, content: '' }
}

const initialState: ScenarioState = {
  entryStep: 'console',
  mode: 'normal',
  scenarioId: null,
  selectedAlertId: DEFAULT_ALERT?.id ?? '',
  selectedSubstationId: DEFAULT_ALERT?.substationId ?? 1,
  incidentState: 'monitoring',
  analysisState: 'idle',
  analysisAlertId: null,
  analyzedAlertIds: [],
  analysisToastVisible: false,
  incidentPopupVisible: false,
  dismissedIncidentAlertIds: [],
  resolvedAlertTimes: {},
  alertSensorSnapshots: {},
  aiEntry: 'overview',
  documentGroups: [],
  activeDocumentGroupId: null,
  documentAlertId: null,
  workOrders: [],
  selectedWorkOrderVersion: null,
  acceptedWorkOrderVersion: null,
  workOrderRerunCount: 0,
  messages: [],
  proposal: null,
  evaluationRequired: false,
  improvementCandidate: null,
  report: emptyReport(),
  reportMessages: [],
}

function alertFor(id: string): ScenarioAlert {
  const fallback = DEFAULT_ALERT
  if (!fallback) throw new Error('시나리오 경보 데이터가 필요합니다.')
  return SCENARIO_ALERTS.find((alert) => alert.id === id) ?? fallback
}

function reportState(status: ScenarioReportStatus, content = ''): ScenarioState['report'] {
  const now = new Date().toISOString()
  if (status === 'completed') return { status, createdAt: now, savedAt: now, completedAt: now, content }
  if (status === 'draft') return { status, createdAt: now, savedAt: null, completedAt: null, content }
  return emptyReport()
}

function reportContent(alert: ScenarioAlert, order: WorkOrderVersion): string {
  return [
    `${alert.facility} 사고 조치 결과 보고서`,
    '',
    '1. 사고 개요',
    `대상 설비: ${alert.facility} (기계실 ${alert.substationId})`,
    `사건명: ${alert.title}`,
    `발생 시각: ${new Date(alert.detectedAt).toLocaleString('ko-KR')}`,
    `기준 작업지시서: v${order.version}`,
    '',
    '2. 조치 경과',
    'AI 조치 분석을 통해 위험도와 현장 영향을 검토하고 작업지시서를 생성했습니다.',
    `운영자가 작업지시서 v${order.version}을 최종 채택해 현장 조치 기준으로 확정했습니다.`,
    '',
    '3. 현장 조치 및 확인',
    order.content,
    '',
    '4. 결과 및 인계',
    '안전 절차와 설비 복구 확인을 완료한 뒤 센서 값의 정상 범위 복귀 여부를 기록합니다.',
    '미완료 항목과 후속 점검 일정은 운영자가 최종 검토하여 아래 본문에 보완합니다.',
  ].join('\n')
}

function workOrderFromResult(alert: ScenarioAlert, version: 1 | 2 | 3, runId: string, result: OpsAgentResultV4, instruction: string | null, baseVersion: 1 | 2 | 3 | null): WorkOrderVersion {
  const sections = [
    { title: '위험성 및 근거', items: [result.situation, ...result.evidence.map((item) => `${item.label}: ${item.content}`)] },
    { title: '작업 절차', items: result.actions.map((item) => `${item.priority}. ${item.title} - ${item.detail}`) },
    { title: '안전 확인', items: result.cautions },
  ]
  const title = `${alert.facility} 작업지시서 v${version}`
  return { version, createdAt: new Date().toISOString(), title, changeSummary: instruction ?? 'AI 초안 생성', instructions: sections.flatMap((section) => section.items), sections, sourceRunId: runId, revisionInstruction: instruction, baseVersion, content: [title, '', ...sections.flatMap((section) => [section.title, ...section.items, ''])].join('\n').trim() }
}

function storedIds(value: Record<string, unknown>, key: string): readonly string[] {
  const candidate = value[key]
  return Array.isArray(candidate) ? candidate.filter((item): item is string => typeof item === 'string') : []
}

function storedStringRecord(value: Record<string, unknown>, key: string): Readonly<Record<string, string>> {
  const candidate = value[key]
  if (typeof candidate !== 'object' || candidate == null || Array.isArray(candidate)) return {}
  return Object.fromEntries(Object.entries(candidate).filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
}

function isVersion(value: unknown): value is 1 | 2 | 3 {
  return value === 1 || value === 2 || value === 3
}

function storedWorkOrders(value: Record<string, unknown>, alert: ScenarioAlert): readonly WorkOrderVersion[] {
  if (Array.isArray(value.workOrders)) {
    return value.workOrders.flatMap((candidate) => {
      if (typeof candidate !== 'object' || candidate == null || !('version' in candidate) || !isVersion(candidate.version)) return []
      const base = workOrderVersion(alert, candidate.version, typeof candidate.changeSummary === 'string' ? candidate.changeSummary : '세션에서 복원된 수정본')
      const storedSections: readonly unknown[] = Array.isArray(candidate.sections) ? candidate.sections : []
      const sections: readonly WorkOrderSection[] = storedSections.length > 0 ? storedSections.flatMap((section) => {
        if (typeof section !== 'object' || section == null || !('title' in section) || typeof section.title !== 'string' || !('items' in section) || !Array.isArray(section.items)) return []
        const items: readonly unknown[] = section.items
        return [{ title: section.title, items: items.filter((item): item is string => typeof item === 'string') }]
      }) : base.sections
      return [{
        ...base,
        createdAt: typeof candidate.createdAt === 'string' ? candidate.createdAt : base.createdAt,
        title: typeof candidate.title === 'string' ? candidate.title : base.title,
        changeSummary: typeof candidate.changeSummary === 'string' ? candidate.changeSummary : base.changeSummary,
        instructions: sections.flatMap((section) => section.items),
        sections,
        content: typeof candidate.content === 'string' ? candidate.content : base.content,
        sourceRunId: typeof candidate.sourceRunId === 'string' ? candidate.sourceRunId : null,
        revisionInstruction: typeof candidate.revisionInstruction === 'string' ? candidate.revisionInstruction : null,
        baseVersion: isVersion(candidate.baseVersion) ? candidate.baseVersion : null,
      }]
    }).sort((a, b) => a.version - b.version)
  }
  const count = typeof value.workOrderCount === 'number' ? Math.min(3, Math.max(0, Math.floor(value.workOrderCount))) : 0
  return Array.from({ length: count }, (_, index) => workOrderVersion(alert, (index + 1) as 1 | 2 | 3, index === 0 ? 'AI 초안 생성' : '세션에서 복원된 수정본'))
}

function storedMessages(value: Record<string, unknown>, key: 'messages' | 'reportMessages'): readonly (ScenarioChatMessage | ScenarioReportMessage)[] {
  const candidate = value[key]
  if (!Array.isArray(candidate)) return []
  return candidate.filter((message): message is ScenarioChatMessage | ScenarioReportMessage => (
    typeof message === 'object' && message != null &&
    'id' in message && typeof message.id === 'string' &&
    'role' in message && (message.role === 'operator' || message.role === 'assistant' || message.role === 'system') &&
    'content' in message && typeof message.content === 'string' &&
    'createdAt' in message && typeof message.createdAt === 'string'
  ))
}

function storedReport(value: Record<string, unknown>): ScenarioState['report'] {
  const candidate = typeof value.report === 'object' && value.report != null && !Array.isArray(value.report)
    ? value.report as Record<string, unknown>
    : null
  const status = candidate?.status === 'draft' || candidate?.status === 'completed' ? candidate.status : 'idle'
  if (status === 'idle') return emptyReport()
  return {
    status,
    createdAt: typeof candidate?.createdAt === 'string' ? candidate.createdAt : new Date().toISOString(),
    savedAt: typeof candidate?.savedAt === 'string' ? candidate.savedAt : null,
    completedAt: typeof candidate?.completedAt === 'string' ? candidate.completedAt : null,
    content: typeof candidate?.content === 'string' ? candidate.content : '',
  }
}

function storedImprovementCandidate(value: Record<string, unknown>): ScenarioState['improvementCandidate'] {
  const candidate = typeof value.improvementCandidate === 'object' && value.improvementCandidate != null && !Array.isArray(value.improvementCandidate)
    ? value.improvementCandidate as Record<string, unknown>
    : null
  const categoryValue = candidate?.category ?? value.evaluationCategory
  const category = categoryValue === 'model' || categoryValue === 'external-data' || categoryValue === 'rag' || categoryValue === 'work-order'
    ? categoryValue
    : null
  if (category == null) return null
  return {
    category,
    label: typeof candidate?.label === 'string' ? candidate.label : IMPROVEMENT_LABELS[category],
    status: 'approval-pending',
    createdAt: typeof candidate?.createdAt === 'string' ? candidate.createdAt : new Date().toISOString(),
  }
}

function storedDocumentGroups(value: Record<string, unknown>): readonly ScenarioDocumentGroup[] {
  if (!Array.isArray(value.documentGroups)) return []
  return value.documentGroups.flatMap((candidate): readonly ScenarioDocumentGroup[] => {
    if (typeof candidate !== 'object' || candidate == null || Array.isArray(candidate)) return []
    const record = candidate as Record<string, unknown>
    const alertId = typeof record.alertId === 'string' ? record.alertId : null
    if (alertId == null) return []
    const alert = alertFor(alertId)
    const workOrders = storedWorkOrders(record, alert)
    const root = workOrders[0]
    if (root == null) return []
    const rootRunId = typeof record.rootRunId === 'string' ? record.rootRunId : root.sourceRunId
    if (rootRunId == null) return []
    const id = typeof record.id === 'string' ? record.id : rootRunId
    const selectedWorkOrderVersion = isVersion(record.selectedWorkOrderVersion) && workOrders.some((order) => order.version === record.selectedWorkOrderVersion)
      ? record.selectedWorkOrderVersion
      : workOrders.at(-1)?.version ?? null
    const acceptedWorkOrderVersion = isVersion(record.acceptedWorkOrderVersion) && workOrders.some((order) => order.version === record.acceptedWorkOrderVersion)
      ? record.acceptedWorkOrderVersion
      : null
    const workOrderRerunCount = typeof record.workOrderRerunCount === 'number'
      ? Math.min(2, Math.max(0, Math.floor(record.workOrderRerunCount)))
      : Math.max(0, workOrders.length - 1)
    return [{
      id,
      rootRunId,
      alertId,
      substationId: typeof record.substationId === 'number' ? record.substationId : alert.substationId,
      createdAt: typeof record.createdAt === 'string' ? record.createdAt : root.createdAt,
      workOrders,
      selectedWorkOrderVersion,
      acceptedWorkOrderVersion,
      workOrderRerunCount,
      messages: storedMessages(record, 'messages').filter((message): message is ScenarioChatMessage => 'workOrderVersion' in message),
      proposal: null,
      evaluationRequired: typeof record.evaluationRequired === 'boolean' ? record.evaluationRequired : workOrderRerunCount >= 2,
      improvementCandidate: storedImprovementCandidate(record),
      report: storedReport(record),
      reportMessages: storedMessages(record, 'reportMessages').filter((message): message is ScenarioReportMessage => !('workOrderVersion' in message)),
    }]
  })
}

function documentGroupFromState(state: ScenarioState): ScenarioDocumentGroup | null {
  const root = state.workOrders[0]
  const alertId = state.documentAlertId
  if (root == null || alertId == null) return null
  const fallbackId = root.sourceRunId ?? `scenario-${alertId}-${root.createdAt}`
  const id = state.activeDocumentGroupId ?? fallbackId
  return {
    id,
    rootRunId: root.sourceRunId ?? id,
    alertId,
    substationId: alertFor(alertId).substationId,
    createdAt: root.createdAt,
    workOrders: state.workOrders,
    selectedWorkOrderVersion: state.selectedWorkOrderVersion,
    acceptedWorkOrderVersion: state.acceptedWorkOrderVersion,
    workOrderRerunCount: state.workOrderRerunCount,
    messages: state.messages,
    proposal: state.proposal,
    evaluationRequired: state.evaluationRequired,
    improvementCandidate: state.improvementCandidate,
    report: state.report,
    reportMessages: state.reportMessages,
  }
}

function syncActiveDocumentGroup(state: ScenarioState): ScenarioState {
  const group = documentGroupFromState(state)
  if (group == null) return state
  const index = state.documentGroups.findIndex((candidate) => candidate.id === group.id)
  const documentGroups = index < 0
    ? [...state.documentGroups, group]
    : state.documentGroups.map((candidate, candidateIndex) => candidateIndex === index ? group : candidate)
  return { ...state, activeDocumentGroupId: group.id, documentGroups }
}

function activateDocumentGroup(state: ScenarioState, group: ScenarioDocumentGroup): ScenarioState {
  const alert = alertFor(group.alertId)
  return {
    ...state,
    selectedAlertId: group.alertId,
    selectedSubstationId: group.substationId || alert.substationId,
    documentAlertId: group.alertId,
    activeDocumentGroupId: group.id,
    workOrders: group.workOrders,
    selectedWorkOrderVersion: group.selectedWorkOrderVersion,
    acceptedWorkOrderVersion: group.acceptedWorkOrderVersion,
    workOrderRerunCount: group.workOrderRerunCount,
    messages: group.messages,
    proposal: group.proposal,
    evaluationRequired: group.evaluationRequired,
    improvementCandidate: group.improvementCandidate,
    report: group.report,
    reportMessages: group.reportMessages,
  }
}

function storedSnapshots(value: Record<string, unknown>): Readonly<Record<string, readonly SensorPoint[]>> {
  if (typeof value.alertSensorSnapshots !== 'object' || value.alertSensorSnapshots == null || Array.isArray(value.alertSensorSnapshots)) return {}
  return Object.fromEntries(Object.entries(value.alertSensorSnapshots).flatMap(([id, points]) => (
    Array.isArray(points) ? [[id, points as readonly SensorPoint[]] as const] : []
  )))
}

function loadSession(): ScenarioState {
  const raw = window.sessionStorage.getItem(SESSION_KEY)
  if (!raw) return initialState
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed == null || Array.isArray(parsed)) return initialState
    const value = parsed as Record<string, unknown>
    const mode = value.mode
    if ((mode !== 'normal' && mode !== 'fault') || value.entryStep !== 'console') return initialState
    const selectedAlertId = typeof value.selectedAlertId === 'string' ? value.selectedAlertId : initialState.selectedAlertId
    const documentAlertId = typeof value.documentAlertId === 'string' ? value.documentAlertId : null
    const documentAlert = alertFor(documentAlertId ?? selectedAlertId)
    const workOrders = storedWorkOrders(value, documentAlert)
    const selectedVersion = isVersion(value.selectedWorkOrderVersion) && workOrders.some((order) => order.version === value.selectedWorkOrderVersion) ? value.selectedWorkOrderVersion : workOrders.at(-1)?.version ?? null
    const acceptedVersion = isVersion(value.acceptedWorkOrderVersion) && workOrders.some((order) => order.version === value.acceptedWorkOrderVersion) ? value.acceptedWorkOrderVersion : null
    const rerunCount = typeof value.workOrderRerunCount === 'number' ? Math.min(2, Math.max(0, Math.floor(value.workOrderRerunCount))) : Math.max(0, workOrders.length - 1)
    const documentGroups = storedDocumentGroups(value)
    const loaded: ScenarioState = {
      ...initialState,
      mode,
      entryStep: 'console',
      scenarioId: mode === 'fault' ? ACTIVE_SCENARIO_ID : null,
      selectedAlertId,
      selectedSubstationId: typeof value.selectedSubstationId === 'number' ? value.selectedSubstationId : alertFor(selectedAlertId).substationId,
      incidentState: value.incidentState === 'incident-active' ? 'incident-active' : 'monitoring',
      analyzedAlertIds: storedIds(value, 'analyzedAlertIds'),
      dismissedIncidentAlertIds: storedIds(value, 'dismissedIncidentAlertIds'),
      resolvedAlertTimes: storedStringRecord(value, 'resolvedAlertTimes'),
      alertSensorSnapshots: storedSnapshots(value),
      documentGroups,
      activeDocumentGroupId: typeof value.activeDocumentGroupId === 'string' ? value.activeDocumentGroupId : null,
      documentAlertId,
      workOrders,
      selectedWorkOrderVersion: selectedVersion,
      acceptedWorkOrderVersion: acceptedVersion,
      workOrderRerunCount: rerunCount,
      messages: storedMessages(value, 'messages').filter((message): message is ScenarioChatMessage => 'workOrderVersion' in message),
      evaluationRequired: rerunCount >= 2,
      improvementCandidate: storedImprovementCandidate(value),
      report: storedReport(value),
      reportMessages: storedMessages(value, 'reportMessages').filter((message): message is ScenarioReportMessage => !('workOrderVersion' in message)),
    }
    if (documentGroups.length === 0) return syncActiveDocumentGroup(loaded)
    const activeGroup = documentGroups.find((group) => group.id === loaded.activeDocumentGroupId) ?? documentGroups.at(-1)
    return activeGroup == null ? loaded : activateDocumentGroup(loaded, activeGroup)
  } catch (error: unknown) {
    if (error instanceof SyntaxError) return initialState
    throw error
  }
}

function persist(state: ScenarioState): void {
  const snapshot = syncActiveDocumentGroup(state)
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    mode: snapshot.mode,
    entryStep: snapshot.entryStep,
    scenarioId: snapshot.scenarioId,
    selectedAlertId: snapshot.selectedAlertId,
    selectedSubstationId: snapshot.selectedSubstationId,
    incidentState: snapshot.incidentState,
    analyzedAlertIds: snapshot.analyzedAlertIds,
    dismissedIncidentAlertIds: snapshot.dismissedIncidentAlertIds,
    resolvedAlertTimes: snapshot.resolvedAlertTimes,
    alertSensorSnapshots: snapshot.alertSensorSnapshots,
    documentGroups: snapshot.documentGroups,
    activeDocumentGroupId: snapshot.activeDocumentGroupId,
    documentAlertId: snapshot.documentAlertId,
    workOrders: snapshot.workOrders,
    selectedWorkOrderVersion: snapshot.selectedWorkOrderVersion,
    acceptedWorkOrderVersion: snapshot.acceptedWorkOrderVersion,
    workOrderRerunCount: snapshot.workOrderRerunCount,
    messages: snapshot.messages,
    evaluationCategory: snapshot.improvementCandidate?.category ?? null,
    report: snapshot.report,
    reportMessages: snapshot.reportMessages,
  }))
}

export function ScenarioProvider({ children }: { readonly children: ReactNode }) {
  const [state, setState] = useState<ScenarioState>(loadSession)
  const sensor = useSensorStream(state.mode, state.entryStep === 'console', state.selectedSubstationId, state.incidentState)
  const alertTimeline = useMemo(() => scenarioAlertsAt(sensor.state.simulatedAt, state.resolvedAlertTimes), [sensor.state.simulatedAt, state.resolvedAlertTimes])
  const { alerts, alertHistory } = useMemo(() => state.mode === 'fault' && state.incidentState === 'incident-active'
    ? { alerts: alertTimeline.active, alertHistory: alertTimeline.history }
    : { alerts: [], alertHistory: [] }, [alertTimeline, state.incidentState, state.mode])

  useEffect(() => {
    if (state.entryStep === 'console') persist(state)
  }, [state])

  useEffect(() => {
    const ended = alertHistory.filter((alert) => (alert.status === 'resolved' || alert.status === 'expired') && state.alertSensorSnapshots[alert.id] == null)
    if (ended.length === 0 || sensor.state.points.length === 0) return
    setState((current) => ({
      ...current,
      alertSensorSnapshots: Object.fromEntries([
        ...Object.entries(current.alertSensorSnapshots),
        ...ended.map((alert) => [alert.id, [...sensor.state.points]] as const),
      ]),
    }))
  }, [alertHistory, sensor.state.points, state.alertSensorSnapshots])

  useEffect(() => {
    if (state.entryStep !== 'console' || state.mode !== 'fault' || state.incidentState === 'incident-active') return undefined
    const simulatedTime = Date.parse(sensor.state.simulatedAt)
    const incidentTime = Date.parse(SCENARIO_INCIDENT_AT)
    if (simulatedTime < incidentTime || simulatedTime - incidentTime > 86_400_000) return undefined
    setState((current) => current.mode === 'fault' && current.entryStep === 'console' ? { ...current, incidentState: 'incident-active', incidentPopupVisible: true } : current)
    return undefined
  }, [sensor.state.simulatedAt, state.entryStep, state.incidentState, state.mode])

  const update = useCallback((next: ScenarioState) => { persist(next); setState(next) }, [])
  const selectMode = useCallback((mode: EntryMode) => {
    const next = mode === 'normal' ? { ...initialState, mode, entryStep: 'console' as const } : { ...initialState, mode, entryStep: 'scenario-selection' as const }
    if (next.entryStep === 'console') persist(next)
    setState(next)
  }, [])
  const backToModeSelection = useCallback(() => { clearScenarioSession(); setState(initialState) }, [])
  const startFaultScenario = useCallback(() => update({ ...initialState, mode: 'fault', entryStep: 'console', scenarioId: ACTIVE_SCENARIO_ID }), [update])
  const restartScenario = useCallback(() => {
    if (state.mode == null) return
    sensor.reset()
    update({ ...initialState, mode: state.mode, entryStep: 'console', scenarioId: state.mode === 'fault' ? ACTIVE_SCENARIO_ID : null })
  }, [sensor, state.mode, update])
  const clearAiHistory = useCallback(() => {
    window.sessionStorage.removeItem(SESSION_KEY)
    window.localStorage.removeItem('heatgrid:last-agent-run')
    clearStoredAiDocumentDrafts()
    setState((current) => ({
      ...current,
      analysisState: 'idle',
      analysisAlertId: null,
      analyzedAlertIds: [],
      analysisToastVisible: false,
      aiEntry: 'overview',
      documentGroups: [],
      activeDocumentGroupId: null,
      documentAlertId: null,
      workOrders: [],
      selectedWorkOrderVersion: null,
      acceptedWorkOrderVersion: null,
      workOrderRerunCount: 0,
      messages: [],
      proposal: null,
      evaluationRequired: false,
      improvementCandidate: null,
      report: emptyReport(),
      reportMessages: [],
    }))
  }, [])
  const exitConsole = useCallback(() => { sensor.reset(); update({ ...initialState }) }, [sensor, update])
  const selectAlert = useCallback((selectedAlertId: string) => setState((current) => ({ ...current, selectedAlertId, selectedSubstationId: alertFor(selectedAlertId).substationId })), [])
  const selectSubstation = useCallback((selectedSubstationId: number) => setState((current) => ({ ...current, selectedSubstationId })), [])
  const startAnalysis = useCallback((analysisAlertId: string) => setState((current) => ({ ...current, selectedAlertId: analysisAlertId, analysisAlertId, analysisState: 'running', analysisToastVisible: false })), [])
  const completeAnalysis = useCallback(() => setState((current) => current.analysisAlertId == null ? current : ({ ...current, analysisState: 'complete', analyzedAlertIds: current.analyzedAlertIds.includes(current.analysisAlertId) ? current.analyzedAlertIds : [...current.analyzedAlertIds, current.analysisAlertId], analysisToastVisible: true })), [])
  const failAnalysis = useCallback(() => setState((current) => current.analysisState !== 'running' ? current : ({ ...current, analysisState: 'idle', analysisAlertId: null, analysisToastVisible: false })), [])
  const dismissAnalysisToast = useCallback(() => setState((current) => ({ ...current, analysisToastVisible: false })), [])
  const dismissIncidentAlert = useCallback((alertId: string) => setState((current) => ({ ...current, dismissedIncidentAlertIds: current.dismissedIncidentAlertIds.includes(alertId) ? current.dismissedIncidentAlertIds : [...current.dismissedIncidentAlertIds, alertId] })), [])
  const dismissIncidentPopup = useCallback(() => setState((current) => ({ ...current, incidentPopupVisible: false })), [])
  const resolveAlert = useCallback((alertId: string) => setState((current) => ({
    ...current,
    resolvedAlertTimes: current.resolvedAlertTimes[alertId] ? current.resolvedAlertTimes : { ...current.resolvedAlertTimes, [alertId]: sensor.state.simulatedAt },
    alertSensorSnapshots: current.alertSensorSnapshots[alertId] ? current.alertSensorSnapshots : { ...current.alertSensorSnapshots, [alertId]: [...sensor.state.points] },
    dismissedIncidentAlertIds: current.dismissedIncidentAlertIds.includes(alertId) ? current.dismissedIncidentAlertIds : [...current.dismissedIncidentAlertIds, alertId],
  })), [sensor.state.points, sensor.state.simulatedAt])
  const setAiEntry = useCallback((aiEntry: ScenarioAiEntry) => setState((current) => ({ ...current, aiEntry })), [])

  const createWorkOrder = useCallback((runId?: string, result?: OpsAgentResultV4, alertId?: string) => setState((current) => {
    if (runId == null || result == null) return current
    const snapshot = syncActiveDocumentGroup(current)
    const existing = snapshot.documentGroups.find((group) => group.rootRunId === runId)
    if (existing != null) return activateDocumentGroup(snapshot, existing)
    const targetAlertId = alertId ?? current.selectedAlertId
    const targetAlert = alertFor(targetAlertId)
    const order = workOrderFromResult(targetAlert, 1, runId, result, null, null)
    return syncActiveDocumentGroup({ ...snapshot, selectedAlertId: targetAlertId, selectedSubstationId: targetAlert.substationId, activeDocumentGroupId: runId, documentAlertId: targetAlertId, workOrders: [order], selectedWorkOrderVersion: 1, acceptedWorkOrderVersion: null, workOrderRerunCount: 0, messages: [], proposal: null, evaluationRequired: false, improvementCandidate: null, report: emptyReport(), reportMessages: [] })
  }), [])
  const selectDocumentGroup = useCallback((groupId: string) => setState((current) => {
    const snapshot = syncActiveDocumentGroup(current)
    const group = snapshot.documentGroups.find((candidate) => candidate.id === groupId)
    return group == null ? current : activateDocumentGroup(snapshot, group)
  }), [])
  const appendWorkOrderRevision = useCallback((runId: string, result: OpsAgentResultV4, instruction: string, target: WorkOrderRevisionTarget, baseVersion: 1 | 2 | 3, documentContent?: string) => setState((current) => {
    const latest = current.workOrders.at(-1)
    const base = current.workOrders.find((order) => order.version === baseVersion)
    if (base == null || latest == null || latest.version >= 3) return current
    const version = (latest.version + 1) as 2 | 3
    const generatedOrder = target.section === 'document'
      ? workOrderFromResult(alertFor(current.documentAlertId ?? current.selectedAlertId), version, runId, result, instruction, base.version)
      : mergeScenarioWorkOrder(base, result, target, version, instruction, runId)
    const order = documentContent?.trim() ? { ...generatedOrder, content: documentContent.trim() } : generatedOrder
    return syncActiveDocumentGroup({ ...current, workOrders: [...current.workOrders, order], selectedWorkOrderVersion: version, workOrderRerunCount: current.workOrderRerunCount + 1, proposal: null })
  }), [])
  const appendWorkOrderMessages = useCallback((messages: readonly ScenarioChatMessage[]) => setState((current) => {
    if (current.activeDocumentGroupId == null || current.workOrders.length === 0) return current
    const existingIds = new Set(current.messages.map((message) => message.id))
    const additions = messages.filter((message) => !existingIds.has(message.id))
    return additions.length === 0 ? current : syncActiveDocumentGroup({ ...current, messages: [...current.messages, ...additions] })
  }), [])
  const selectWorkOrderVersion = useCallback((selectedWorkOrderVersion: 1 | 2 | 3) => setState((current) => current.workOrders.some((order) => order.version === selectedWorkOrderVersion) ? syncActiveDocumentGroup({ ...current, selectedWorkOrderVersion }) : current), [])
  const updateWorkOrderContent = useCallback((version: 1 | 2 | 3, content: string) => setState((current) => {
    const editedAcceptedVersion = current.acceptedWorkOrderVersion === version
    return syncActiveDocumentGroup({
      ...current,
      workOrders: current.workOrders.map((order) => order.version === version ? { ...order, content, changeSummary: '운영자 직접 편집' } : order),
      acceptedWorkOrderVersion: editedAcceptedVersion ? null : current.acceptedWorkOrderVersion,
      report: editedAcceptedVersion ? emptyReport() : current.report,
      reportMessages: editedAcceptedVersion ? [] : current.reportMessages,
    })
  }), [])
  const acceptWorkOrder = useCallback((version: 1 | 2 | 3) => setState((current) => {
    if (!current.workOrders.some((order) => order.version === version)) return current
    return syncActiveDocumentGroup({ ...current, selectedWorkOrderVersion: version, acceptedWorkOrderVersion: version, report: current.acceptedWorkOrderVersion === version ? current.report : emptyReport(), reportMessages: current.acceptedWorkOrderVersion === version ? current.reportMessages : [] })
  }), [])
  const createReportDraft = useCallback(() => setState((current) => {
    const order = current.workOrders.find((candidate) => candidate.version === current.acceptedWorkOrderVersion)
    if (!order || current.report.status !== 'idle') return current
    return syncActiveDocumentGroup({ ...current, report: reportState('draft', reportContent(alertFor(current.documentAlertId ?? current.selectedAlertId), order)) })
  }), [])
  const saveReportDraft = useCallback((content: string) => setState((current) => current.report.status !== 'draft' ? current : syncActiveDocumentGroup({ ...current, report: { ...current.report, content, savedAt: new Date().toISOString() } })), [])
  const completeReport = useCallback(() => setState((current) => current.report.status !== 'draft' ? current : syncActiveDocumentGroup({ ...current, report: { ...current.report, status: 'completed', savedAt: current.report.savedAt ?? new Date().toISOString(), completedAt: new Date().toISOString() } })), [])
  const postReportMessage = useCallback((content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return
    const createdAt = new Date().toISOString()
    const messages: readonly ScenarioReportMessage[] = [
      { id: `report-operator-${Date.now()}`, role: 'operator', content: trimmed, createdAt },
      { id: `report-assistant-${Date.now()}`, role: 'assistant', content: '보고서 검토 의견으로 정리했습니다. 본문은 변경하지 않았으니 운영자가 필요한 문구만 직접 반영해 주세요.', createdAt },
    ]
    setState((current) => syncActiveDocumentGroup({ ...current, reportMessages: [...current.reportMessages, ...messages] }))
  }, [])

  const submitEvaluation = useCallback((category: EvaluationCategory) => setState((current) => syncActiveDocumentGroup({ ...current, improvementCandidate: { category, label: IMPROVEMENT_LABELS[category], status: 'approval-pending', createdAt: new Date().toISOString() } })), [])

  const value = useMemo<ScenarioContextValue>(() => ({
    state, sensor, alerts, alertHistory, selectMode, backToModeSelection, startFaultScenario, restartScenario, clearAiHistory, exitConsole, selectAlert, selectSubstation, startAnalysis, completeAnalysis, failAnalysis, dismissAnalysisToast, dismissIncidentAlert, dismissIncidentPopup, resolveAlert, setAiEntry, createWorkOrder, selectDocumentGroup, appendWorkOrderRevision, appendWorkOrderMessages, selectWorkOrderVersion, updateWorkOrderContent, acceptWorkOrder, createReportDraft, saveReportDraft, completeReport, postReportMessage, submitEvaluation,
  }), [acceptWorkOrder, alertHistory, alerts, appendWorkOrderMessages, appendWorkOrderRevision, backToModeSelection, clearAiHistory, completeAnalysis, completeReport, createReportDraft, createWorkOrder, dismissAnalysisToast, dismissIncidentAlert, dismissIncidentPopup, exitConsole, failAnalysis, postReportMessage, resolveAlert, restartScenario, saveReportDraft, selectAlert, selectDocumentGroup, selectMode, selectSubstation, selectWorkOrderVersion, sensor, setAiEntry, startAnalysis, startFaultScenario, state, submitEvaluation, updateWorkOrderContent])

  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>
}
