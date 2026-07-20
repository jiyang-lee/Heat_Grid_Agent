import { useCallback, useEffect, useState } from 'react'
import { AlertsPage } from './console/AlertsPage'
import { AdminPage } from './console/AdminPage'
import { AiActivityPage } from './console/ai-activity/AiActivityPage'
import { AppShell, type ConsolePage } from './console/AppShell'
import { DashboardPage } from './console/DashboardPage'
import { OperationsProvider } from './console/OperationsContext'
import { SettingsPage } from './console/SettingsPage'
import { AgentAnalysisProgress, type AgentAnalysisQueueEntry } from './console/AgentAnalysisProgress'
import { ScenarioAlertsPage } from './scenario/ScenarioAlertsPage'
import { ScenarioProvider } from './scenario/ScenarioContext'
import { useScenario } from './scenario/useScenario'
import { useThemePreference } from './console/useThemePreference'
import { demoAiHistoryApi } from './api/client'
import './console/operations.css'
import './scenario/scenario.css'

const AGENT_QUEUE_STORAGE_KEY = 'heatgrid:agent-analysis-queue'

function storedAgentQueue(): readonly AgentAnalysisQueueEntry[] {
  try {
    const value: unknown = JSON.parse(window.sessionStorage.getItem(AGENT_QUEUE_STORAGE_KEY) ?? '[]')
    if (!Array.isArray(value)) return []
    return value.filter((entry): entry is AgentAnalysisQueueEntry => (
      typeof entry === 'object'
      && entry != null
      && typeof entry.runId === 'string'
      && typeof entry.alertId === 'string'
      && typeof entry.label === 'string'
      && typeof entry.requestedAt === 'string'
    ))
  } catch {
    return []
  }
}

function ConsoleApp() {
  const scenario = useScenario()
  const theme = useThemePreference()
  const [page, setPage] = useState<ConsolePage>('dashboard')
  const [initialAlertId, setInitialAlertId] = useState<string | null>(null)
  const [pendingRunId, setPendingRunId] = useState<string | null>(null)
  const [analysisQueue, setAnalysisQueue] = useState<readonly AgentAnalysisQueueEntry[]>(storedAgentQueue)
  const [refreshRevision, setRefreshRevision] = useState(0)
  const mode = scenario.state.mode ?? 'normal'
  const replay = mode === 'fault'

  useEffect(() => {
    window.sessionStorage.setItem(AGENT_QUEUE_STORAGE_KEY, JSON.stringify(analysisQueue))
  }, [analysisQueue])

  const navigate = (next: ConsolePage) => {
    if (next === 'ai-action') setPendingRunId(null)
    if (next === 'alerts') setInitialAlertId(null)
    setPage(next)
  }
  const openRun = (runId: string) => {
    setPendingRunId(runId)
    setPage('ai-action')
  }
  const queueAgentRun = useCallback((entry: AgentAnalysisQueueEntry) => {
    setAnalysisQueue((current) => current.some((item) => item.runId === entry.runId)
      ? current
      : [entry, ...current])
  }, [])
  const removeAgentRuns = useCallback((runIds: readonly string[]) => {
    const targets = new Set(runIds)
    setAnalysisQueue((current) => current.filter((item) => !targets.has(item.runId)))
  }, [])
  const consumePendingRun = useCallback(() => setPendingRunId(null), [])
  const consumeInitialAlert = useCallback(() => setInitialAlertId(null), [])
  const openAlerts = (alertId?: string) => {
    if (replay && alertId != null) scenario.selectAlert(alertId)
    setInitialAlertId(alertId ?? null)
    setPage('alerts')
  }
  // 새로고침은 F5와 같다: 정상·고장 어느 모드든 서버 AI 기록과 클라이언트 캐시,
  // 만들어진 모든 산출물을 지우고 해당 모드의 첫 시점으로 되돌린다.
  const refreshConsole = useCallback(async () => {
    await demoAiHistoryApi.reset()
    scenario.restartScenario()
    setInitialAlertId(null)
    setPendingRunId(null)
    setAnalysisQueue([])
    setRefreshRevision((revision) => revision + 1)
    setPage('dashboard')
  }, [scenario])

  return <OperationsProvider initialSubstationId={scenario.state.selectedSubstationId} mode={mode} referenceTime={replay ? scenario.sensor.state.simulatedAt : null}>
    <AppShell alertCount={replay && scenario.state.incidentState === 'incident-active' ? scenario.alerts.length : 0} onPageChange={navigate} onRefresh={refreshConsole} page={page} simulatedAt={replay ? scenario.sensor.state.simulatedAt : null}>
      {page === 'dashboard' && <DashboardPage onOpenAlerts={openAlerts} theme={theme.resolvedTheme} />}
      {page === 'alerts' && (replay ? <ScenarioAlertsPage analysisQueue={analysisQueue} initialAlertId={initialAlertId} key={scenario.state.incidentState} onConsumeInitialAlert={consumeInitialAlert} onOpenAiAction={openRun} onRunQueued={queueAgentRun} /> : <AlertsPage analysisQueue={analysisQueue} onOpenAiAction={openRun} onRunCreated={queueAgentRun} />)}
      {page === 'ai-action' && <AiActivityPage entryMode={mode} incidentAlertId={replay && pendingRunId != null ? scenario.state.selectedAlertId : null} initialRunId={pendingRunId} onConsumeInitialRun={consumePendingRun} />}
      {page === 'settings' && <SettingsPage onOpenAdmin={() => setPage('admin')} onThemePreferenceChange={theme.setPreference} themePreference={theme.preference} />}
      {page === 'admin' && <AdminPage onModeChanged={() => setPage('dashboard')} refreshRevision={refreshRevision} />}
    </AppShell>
    <AgentAnalysisProgress entries={analysisQueue} onOpen={openRun} onRemoveEntries={removeAgentRuns} />
  </OperationsProvider>
}

export default function App() {
  return <ScenarioProvider><ConsoleApp /></ScenarioProvider>
}
