import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ACTIVE_SCENARIO_ID, IMPROVEMENT_LABELS, SCENARIO_ALERTS, scenarioAlertsAt, workOrderVersion } from './scenarioData'
import { ScenarioContext, type ScenarioContextValue } from './ScenarioContextDefinition'
import type {
  EntryMode,
  EvaluationCategory,
  ScenarioAiEntry,
  ScenarioAlert,
  ScenarioChatMessage,
  ScenarioReportMessage,
  ScenarioReportStatus,
  ScenarioState,
  SensorPoint,
  WorkOrderVersion,
} from './types'
import { useSensorStream } from './useSensorStream'
import type { OpsAgentResultV4 } from '../api/contracts'

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
      return [{
        ...base,
        createdAt: typeof candidate.createdAt === 'string' ? candidate.createdAt : base.createdAt,
        content: typeof candidate.content === 'string' ? candidate.content : base.content,
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
    const category = value.evaluationCategory === 'model' || value.evaluationCategory === 'external-data' || value.evaluationCategory === 'rag' || value.evaluationCategory === 'work-order' ? value.evaluationCategory : null
    const reportValue = typeof value.report === 'object' && value.report != null && !Array.isArray(value.report) ? value.report as Record<string, unknown> : null
    const reportStatus = reportValue?.status === 'draft' || reportValue?.status === 'completed' ? reportValue.status : 'idle'
    const report: ScenarioState['report'] = reportStatus === 'idle' ? emptyReport() : {
      status: reportStatus,
      createdAt: typeof reportValue?.createdAt === 'string' ? reportValue.createdAt : new Date().toISOString(),
      savedAt: typeof reportValue?.savedAt === 'string' ? reportValue.savedAt : null,
      completedAt: typeof reportValue?.completedAt === 'string' ? reportValue.completedAt : null,
      content: typeof reportValue?.content === 'string' ? reportValue.content : '',
    }
    const rerunCount = typeof value.workOrderRerunCount === 'number' ? Math.min(2, Math.max(0, Math.floor(value.workOrderRerunCount))) : Math.max(0, workOrders.length - 1)
    return {
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
      documentAlertId,
      workOrders,
      selectedWorkOrderVersion: selectedVersion,
      acceptedWorkOrderVersion: acceptedVersion,
      workOrderRerunCount: rerunCount,
      messages: storedMessages(value, 'messages').filter((message): message is ScenarioChatMessage => 'workOrderVersion' in message),
      evaluationRequired: rerunCount >= 2,
      improvementCandidate: category ? { category, label: IMPROVEMENT_LABELS[category], status: 'approval-pending', createdAt: new Date().toISOString() } : null,
      report,
      reportMessages: storedMessages(value, 'reportMessages').filter((message): message is ScenarioReportMessage => !('workOrderVersion' in message)),
    }
  } catch (error: unknown) {
    if (error instanceof SyntaxError) return initialState
    throw error
  }
}

function persist(state: ScenarioState): void {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    mode: state.mode,
    entryStep: state.entryStep,
    scenarioId: state.scenarioId,
    selectedAlertId: state.selectedAlertId,
    selectedSubstationId: state.selectedSubstationId,
    incidentState: state.incidentState,
    analyzedAlertIds: state.analyzedAlertIds,
    dismissedIncidentAlertIds: state.dismissedIncidentAlertIds,
    resolvedAlertTimes: state.resolvedAlertTimes,
    alertSensorSnapshots: state.alertSensorSnapshots,
    documentAlertId: state.documentAlertId,
    workOrders: state.workOrders,
    selectedWorkOrderVersion: state.selectedWorkOrderVersion,
    acceptedWorkOrderVersion: state.acceptedWorkOrderVersion,
    workOrderRerunCount: state.workOrderRerunCount,
    messages: state.messages,
    evaluationCategory: state.improvementCandidate?.category ?? null,
    report: state.report,
    reportMessages: state.reportMessages,
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
    const timer = window.setTimeout(() => setState((current) => current.mode === 'fault' && current.entryStep === 'console' ? { ...current, incidentState: 'incident-active', incidentPopupVisible: true } : current), 5_000)
    return () => window.clearTimeout(timer)
  }, [state.entryStep, state.incidentState, state.mode])

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

  const createWorkOrder = useCallback((runId?: string, result?: OpsAgentResultV4) => setState((current) => {
    if (current.documentAlertId === current.selectedAlertId && current.workOrders.length > 0) return current
    if (runId == null || result == null) return current
    const order = workOrderFromResult(alertFor(current.selectedAlertId), 1, runId, result, null, null)
    return { ...current, documentAlertId: current.selectedAlertId, workOrders: [order], selectedWorkOrderVersion: 1, acceptedWorkOrderVersion: null, workOrderRerunCount: 0, messages: [], proposal: null, evaluationRequired: false, improvementCandidate: null, report: emptyReport(), reportMessages: [] }
  }), [])
  const appendWorkOrderRevision = useCallback((runId: string, result: OpsAgentResultV4, instruction: string) => setState((current) => {
    const base = current.workOrders.at(-1)
    if (base == null || base.version >= 3) return current
    const version = (base.version + 1) as 2 | 3
    const order = workOrderFromResult(alertFor(current.documentAlertId ?? current.selectedAlertId), version, runId, result, instruction, base.version)
    return { ...current, workOrders: [...current.workOrders, order], selectedWorkOrderVersion: version, acceptedWorkOrderVersion: null, workOrderRerunCount: current.workOrderRerunCount + 1, proposal: null, report: emptyReport(), reportMessages: [] }
  }), [])
  const appendWorkOrderMessages = useCallback((messages: readonly ScenarioChatMessage[]) => setState((current) => ({ ...current, messages: [...current.messages, ...messages] })), [])
  const selectWorkOrderVersion = useCallback((selectedWorkOrderVersion: 1 | 2 | 3) => setState((current) => current.workOrders.some((order) => order.version === selectedWorkOrderVersion) ? { ...current, selectedWorkOrderVersion } : current), [])
  const updateWorkOrderContent = useCallback((version: 1 | 2 | 3, content: string) => setState((current) => ({ ...current, workOrders: current.workOrders.map((order) => order.version === version ? { ...order, content } : order) })), [])
  const acceptWorkOrder = useCallback((version: 1 | 2 | 3) => setState((current) => {
    if (!current.workOrders.some((order) => order.version === version)) return current
    return { ...current, selectedWorkOrderVersion: version, acceptedWorkOrderVersion: version, report: current.acceptedWorkOrderVersion === version ? current.report : emptyReport(), reportMessages: current.acceptedWorkOrderVersion === version ? current.reportMessages : [] }
  }), [])
  const createReportDraft = useCallback(() => setState((current) => {
    const order = current.workOrders.find((candidate) => candidate.version === current.acceptedWorkOrderVersion)
    if (!order || current.report.status !== 'idle') return current
    return { ...current, report: reportState('draft', reportContent(alertFor(current.documentAlertId ?? current.selectedAlertId), order)) }
  }), [])
  const saveReportDraft = useCallback((content: string) => setState((current) => current.report.status !== 'draft' ? current : ({ ...current, report: { ...current.report, content, savedAt: new Date().toISOString() } })), [])
  const completeReport = useCallback(() => setState((current) => current.report.status !== 'draft' ? current : ({ ...current, report: { ...current.report, status: 'completed', savedAt: current.report.savedAt ?? new Date().toISOString(), completedAt: new Date().toISOString() } })), [])
  const postReportMessage = useCallback((content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return
    const createdAt = new Date().toISOString()
    const messages: readonly ScenarioReportMessage[] = [
      { id: `report-operator-${Date.now()}`, role: 'operator', content: trimmed, createdAt },
      { id: `report-assistant-${Date.now()}`, role: 'assistant', content: '보고서 검토 의견으로 정리했습니다. 본문은 변경하지 않았으니 운영자가 필요한 문구만 직접 반영해 주세요.', createdAt },
    ]
    setState((current) => ({ ...current, reportMessages: [...current.reportMessages, ...messages] }))
  }, [])

  const submitEvaluation = useCallback((category: EvaluationCategory) => setState((current) => ({ ...current, improvementCandidate: { category, label: IMPROVEMENT_LABELS[category], status: 'approval-pending', createdAt: new Date().toISOString() } })), [])

  const value = useMemo<ScenarioContextValue>(() => ({
    state, sensor, alerts, alertHistory, selectMode, backToModeSelection, startFaultScenario, restartScenario, exitConsole, selectAlert, selectSubstation, startAnalysis, completeAnalysis, failAnalysis, dismissAnalysisToast, dismissIncidentAlert, dismissIncidentPopup, resolveAlert, setAiEntry, createWorkOrder, appendWorkOrderRevision, appendWorkOrderMessages, selectWorkOrderVersion, updateWorkOrderContent, acceptWorkOrder, createReportDraft, saveReportDraft, completeReport, postReportMessage, submitEvaluation,
  }), [acceptWorkOrder, alertHistory, alerts, appendWorkOrderMessages, appendWorkOrderRevision, backToModeSelection, completeAnalysis, completeReport, createReportDraft, createWorkOrder, dismissAnalysisToast, dismissIncidentAlert, dismissIncidentPopup, exitConsole, failAnalysis, postReportMessage, resolveAlert, restartScenario, saveReportDraft, selectAlert, selectMode, selectSubstation, selectWorkOrderVersion, sensor, setAiEntry, startAnalysis, startFaultScenario, state, submitEvaluation, updateWorkOrderContent])

  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>
}
