import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ACTIVE_SCENARIO_ID, IMPROVEMENT_LABELS, SCENARIO_ALERTS, scenarioAlertsAt, workOrderVersion } from './scenarioData'
import { ScenarioContext, type ScenarioContextValue } from './ScenarioContextDefinition'
import type { ChatProposal, ChatTargetStage, EntryMode, EvaluationCategory, ScenarioAiEntry, ScenarioAlert, ScenarioChatMessage, ScenarioReportStatus, ScenarioState } from './types'
import { useSensorStream } from './useSensorStream'

const SESSION_KEY = 'heatgrid:scenario-session'
const DEFAULT_ALERT = SCENARIO_ALERTS[0]

const initialState: ScenarioState = {
  entryStep: 'mode-selection',
  mode: null,
  scenarioId: null,
  selectedAlertId: DEFAULT_ALERT?.id ?? '',
  incidentState: 'monitoring',
  analysisState: 'idle',
  analysisAlertId: null,
  analyzedAlertIds: [],
  analysisToastVisible: false,
  incidentPopupVisible: false,
  dismissedIncidentAlertIds: [],
  resolvedAlertTimes: {},
  aiEntry: 'overview',
  workOrders: [],
  acceptedWorkOrderVersion: null,
  messages: [],
  proposal: null,
  evaluationRequired: false,
  improvementCandidate: null,
  report: { status: 'idle', createdAt: null, issuedAt: null },
}

function alertFor(id: string): ScenarioAlert {
  const fallback = DEFAULT_ALERT
  if (!fallback) throw new Error('시나리오 경보 데이터가 필요합니다.')
  return SCENARIO_ALERTS.find((alert) => alert.id === id) ?? fallback
}

function reportState(status: ScenarioReportStatus): ScenarioState['report'] {
  const now = new Date().toISOString()
  if (status === 'issued') return { status, createdAt: now, issuedAt: now }
  if (status === 'draft') return { status, createdAt: now, issuedAt: null }
  return { status, createdAt: null, issuedAt: null }
}

function storedIds(value: object, key: string): readonly string[] {
  if (!(key in value)) return []
  const candidate = (value as Record<string, unknown>)[key]
  return Array.isArray(candidate) ? candidate.filter((item): item is string => typeof item === 'string') : []
}

function storedStringRecord(value: object, key: string): Readonly<Record<string, string>> {
  if (!(key in value)) return {}
  const candidate = (value as Record<string, unknown>)[key]
  if (typeof candidate !== 'object' || candidate == null || Array.isArray(candidate)) return {}
  return Object.fromEntries(Object.entries(candidate).filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
}

function loadSession(): ScenarioState {
  const raw = window.sessionStorage.getItem(SESSION_KEY)
  if (!raw) return initialState
  try {
    const value: unknown = JSON.parse(raw)
    if (typeof value !== 'object' || value == null || !('mode' in value) || !('entryStep' in value)) return initialState
    const mode = value.mode
    const entryStep = value.entryStep
    if ((mode !== 'normal' && mode !== 'fault') || entryStep !== 'console') return initialState
    const selectedAlertId = 'selectedAlertId' in value && typeof value.selectedAlertId === 'string' ? value.selectedAlertId : initialState.selectedAlertId
    const workOrderCount = 'workOrderCount' in value && typeof value.workOrderCount === 'number' ? Math.min(3, Math.max(0, Math.floor(value.workOrderCount))) : 0
    const selectedAlert = alertFor(selectedAlertId)
    const workOrders = Array.from({ length: workOrderCount }, (_, index) => workOrderVersion(selectedAlert, (index + 1) as 1 | 2 | 3, index === 0 ? 'AI 초안 생성' : '세션에서 복원된 수정본'))
    const category = 'evaluationCategory' in value && (value.evaluationCategory === 'model' || value.evaluationCategory === 'external-data' || value.evaluationCategory === 'rag' || value.evaluationCategory === 'work-order') ? value.evaluationCategory : null
    const incidentState = 'incidentState' in value && value.incidentState === 'incident-active' ? 'incident-active' : 'monitoring'
    const storedReport = 'reportStatus' in value && (value.reportStatus === 'draft' || value.reportStatus === 'issued') ? value.reportStatus : 'idle'
    const analyzedAlertIds = storedIds(value, 'analyzedAlertIds')
    const acceptedWorkOrderVersion = 'acceptedWorkOrderVersion' in value && (value.acceptedWorkOrderVersion === 1 || value.acceptedWorkOrderVersion === 2 || value.acceptedWorkOrderVersion === 3) && value.acceptedWorkOrderVersion <= workOrderCount ? value.acceptedWorkOrderVersion : null
    return {
      ...initialState,
      mode,
      entryStep,
      scenarioId: mode === 'fault' ? ACTIVE_SCENARIO_ID : null,
      selectedAlertId,
      incidentState,
      analysisState: 'idle',
      analysisAlertId: null,
      analyzedAlertIds,
      dismissedIncidentAlertIds: storedIds(value, 'dismissedIncidentAlertIds'),
      resolvedAlertTimes: storedStringRecord(value, 'resolvedAlertTimes'),
      workOrders,
      acceptedWorkOrderVersion,
      evaluationRequired: workOrderCount >= 3,
      improvementCandidate: category ? { category, label: IMPROVEMENT_LABELS[category], status: 'approval-pending', createdAt: new Date().toISOString() } : null,
      report: reportState(storedReport),
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
    incidentState: state.incidentState,
    analyzedAlertIds: state.analyzedAlertIds,
    dismissedIncidentAlertIds: state.dismissedIncidentAlertIds,
    resolvedAlertTimes: state.resolvedAlertTimes,
    workOrderCount: state.workOrders.length,
    acceptedWorkOrderVersion: state.acceptedWorkOrderVersion,
    evaluationCategory: state.improvementCandidate?.category ?? null,
    reportStatus: state.report.status,
  }))
}

function classifyMessage(content: string): Omit<ChatProposal, 'id' | 'source'> {
  const normalized = content.toLowerCase()
  const mapping: readonly { readonly matches: readonly string[]; readonly stage: ChatTargetStage; readonly label: string; readonly summary: string }[] = [
    { matches: ['모델', '예측', '위험도', '평가'], stage: 'ml_validation', label: '모델 검증 단계', summary: '위험도와 예측 근거를 다시 평가하고 작업지시서 판단 문구를 갱신합니다.' },
    { matches: ['외부', '날씨', '기상', '데이터 품질'], stage: 'external_context', label: '외부 맥락 단계', summary: '외부 데이터의 적용 범위와 품질을 다시 확인해 운영 맥락을 교정합니다.' },
    { matches: ['rag', '문서', '매뉴얼', '최신'], stage: 'rag_retrieval', label: '검색·근거 단계', summary: '참고 문서의 최신성과 검색 근거를 다시 확인해 지시서 근거를 교체합니다.' },
  ]
  const selected = mapping.find((item) => item.matches.some((match) => normalized.includes(match)))
  return selected
    ? { intent: content, targetStage: selected.stage, targetLabel: selected.label, changeSummary: selected.summary }
    : { intent: content, targetStage: 'work_order_draft', targetLabel: '작업지시서 작성 단계', changeSummary: '운영자의 문구와 절차 지적을 반영해 작업지시서 초안을 다시 작성합니다.' }
}

export function ScenarioProvider({ children }: { readonly children: ReactNode }) {
  const [state, setState] = useState<ScenarioState>(loadSession)
  const selectedAlert = alertFor(state.selectedAlertId)
  const sensor = useSensorStream(state.mode, state.entryStep === 'console', selectedAlert.substationId, state.incidentState)
  const alertTimeline = useMemo(() => scenarioAlertsAt(sensor.state.simulatedAt, state.resolvedAlertTimes), [sensor.state.simulatedAt, state.resolvedAlertTimes])
  const { alerts, alertHistory } = useMemo(() => state.mode === 'fault' && state.incidentState === 'incident-active'
    ? { alerts: alertTimeline.active, alertHistory: alertTimeline.history }
    : { alerts: [], alertHistory: [] }, [alertTimeline, state.incidentState, state.mode])

  useEffect(() => {
    if (state.entryStep === 'console') persist(state)
  }, [state])

  useEffect(() => {
    if (state.entryStep !== 'console' || state.mode !== 'fault' || state.incidentState === 'incident-active') return undefined
    const timer = window.setTimeout(() => setState((current) => current.mode === 'fault' && current.entryStep === 'console' ? { ...current, incidentState: 'incident-active', incidentPopupVisible: true } : current), 5_000)
    return () => window.clearTimeout(timer)
  }, [state.entryStep, state.incidentState, state.mode])

  const update = useCallback((next: ScenarioState) => {
    persist(next)
    setState(next)
  }, [])

  const selectMode = useCallback((mode: EntryMode) => {
    const next = mode === 'normal' ? { ...initialState, mode, entryStep: 'console' as const } : { ...initialState, mode, entryStep: 'scenario-selection' as const }
    if (next.entryStep === 'console') persist(next)
    setState(next)
  }, [])

  const backToModeSelection = useCallback(() => {
    window.sessionStorage.removeItem(SESSION_KEY)
    setState(initialState)
  }, [])

  const startFaultScenario = useCallback(() => update({ ...initialState, mode: 'fault', entryStep: 'console', scenarioId: ACTIVE_SCENARIO_ID }), [update])
  const restartScenario = useCallback(() => {
    if (state.mode == null) return
    sensor.reset()
    update({ ...initialState, mode: state.mode, entryStep: 'console', scenarioId: state.mode === 'fault' ? ACTIVE_SCENARIO_ID : null })
  }, [sensor, state.mode, update])
  const exitConsole = useCallback(() => {
    sensor.reset()
    backToModeSelection()
  }, [backToModeSelection, sensor])
  const selectAlert = useCallback((selectedAlertId: string) => setState((current) => ({ ...current, selectedAlertId })), [])
  const startAnalysis = useCallback((analysisAlertId: string) => setState((current) => ({ ...current, selectedAlertId: analysisAlertId, analysisAlertId, analysisState: 'running' })), [])
  const completeAnalysis = useCallback(() => setState((current) => current.analysisAlertId == null ? current : ({
    ...current,
    analysisState: 'complete',
    analyzedAlertIds: current.analyzedAlertIds.includes(current.analysisAlertId) ? current.analyzedAlertIds : [...current.analyzedAlertIds, current.analysisAlertId],
    analysisToastVisible: true,
  })), [])
  const dismissAnalysisToast = useCallback(() => setState((current) => ({ ...current, analysisToastVisible: false })), [])
  const dismissIncidentAlert = useCallback((alertId: string) => setState((current) => ({ ...current, dismissedIncidentAlertIds: current.dismissedIncidentAlertIds.includes(alertId) ? current.dismissedIncidentAlertIds : [...current.dismissedIncidentAlertIds, alertId] })), [])
  const dismissIncidentPopup = useCallback(() => setState((current) => ({ ...current, incidentPopupVisible: false })), [])
  const resolveAlert = useCallback((alertId: string) => setState((current) => ({
    ...current,
    resolvedAlertTimes: current.resolvedAlertTimes[alertId] ? current.resolvedAlertTimes : { ...current.resolvedAlertTimes, [alertId]: sensor.state.simulatedAt },
    dismissedIncidentAlertIds: current.dismissedIncidentAlertIds.includes(alertId) ? current.dismissedIncidentAlertIds : [...current.dismissedIncidentAlertIds, alertId],
  })), [sensor.state.simulatedAt])
  const setAiEntry = useCallback((aiEntry: ScenarioAiEntry) => setState((current) => ({ ...current, aiEntry })), [])
  const createWorkOrder = useCallback(() => setState((current) => current.workOrders.length > 0 ? current : ({ ...current, workOrders: [workOrderVersion(alertFor(current.selectedAlertId), 1, 'AI 초안 생성')], acceptedWorkOrderVersion: null, report: reportState('idle') })), [])
  const acceptWorkOrder = useCallback((version: 1 | 2 | 3) => setState((current) => current.workOrders.some((order) => order.version === version) ? ({ ...current, acceptedWorkOrderVersion: version, report: reportState('idle') }) : current), [])
  const createReportDraft = useCallback(() => setState((current) => current.acceptedWorkOrderVersion == null ? current : ({ ...current, report: reportState('draft') })), [])
  const issueReport = useCallback(() => setState((current) => current.report.status !== 'draft' ? current : ({ ...current, report: reportState('issued') })), [])

  const postChatMessage = useCallback((content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return
    setState((current) => {
      const classified = classifyMessage(trimmed)
      const createdAt = new Date().toISOString()
      const proposal: ChatProposal = { id: `proposal-${Date.now()}`, ...classified, source: 'scenario-analysis' }
      const workOrderVersion = current.workOrders.at(-1)?.version ?? 1
      const messages: readonly ScenarioChatMessage[] = [...current.messages, { id: `operator-${Date.now()}`, role: 'operator', content: trimmed, createdAt, workOrderVersion }, { id: `assistant-${Date.now()}`, role: 'assistant', content: `${classified.targetLabel}로 돌아가 수정안을 만들겠습니다. 실행 전에 아래 제안을 확인해 주세요.`, createdAt, workOrderVersion }]
      return { ...current, messages, proposal }
    })
  }, [])

  const confirmProposal = useCallback(() => setState((current) => {
    if (!current.proposal || current.workOrders.length === 0 || current.workOrders.length >= 3) return current
    const version = (current.workOrders.length + 1) as 2 | 3
    const createdAt = new Date().toISOString()
    const messages: readonly ScenarioChatMessage[] = [...current.messages, { id: `system-${Date.now()}`, role: 'system', content: `${current.proposal.targetLabel} 재실행을 완료하고 작업지시서 v${version}을 발행했습니다.`, createdAt, workOrderVersion: version }]
    return { ...current, workOrders: [...current.workOrders, workOrderVersion(alertFor(current.selectedAlertId), version, current.proposal.changeSummary)], acceptedWorkOrderVersion: null, messages, proposal: null, evaluationRequired: version === 3, report: reportState('idle') }
  }), [])

  const cancelProposal = useCallback(() => setState((current) => ({ ...current, proposal: null })), [])
  const submitEvaluation = useCallback((category: EvaluationCategory) => setState((current) => ({ ...current, improvementCandidate: { category, label: IMPROVEMENT_LABELS[category], status: 'approval-pending', createdAt: new Date().toISOString() } })), [])

  const value = useMemo<ScenarioContextValue>(() => ({
    state, sensor, alerts, alertHistory, selectMode, backToModeSelection, startFaultScenario, restartScenario, exitConsole, selectAlert, startAnalysis, completeAnalysis, dismissAnalysisToast, dismissIncidentAlert, dismissIncidentPopup, resolveAlert, setAiEntry, createWorkOrder, acceptWorkOrder, createReportDraft, issueReport, postChatMessage, confirmProposal, cancelProposal, submitEvaluation,
  }), [acceptWorkOrder, alertHistory, alerts, backToModeSelection, cancelProposal, completeAnalysis, confirmProposal, createReportDraft, createWorkOrder, dismissAnalysisToast, dismissIncidentAlert, dismissIncidentPopup, exitConsole, issueReport, postChatMessage, resolveAlert, restartScenario, selectAlert, selectMode, sensor, setAiEntry, startAnalysis, startFaultScenario, state, submitEvaluation])

  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>
}
