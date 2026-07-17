import { useCallback, useState } from 'react'
import { AlertsPage } from './console/AlertsPage'
import { AiActivityPage } from './console/ai-activity/AiActivityPage'
import { AppShell, type ConsolePage } from './console/AppShell'
import { DashboardPage } from './console/DashboardPage'
import { SettingsPage } from './console/SettingsPage'
import { EntryGate } from './scenario/EntryGate'
import { ScenarioAlertsPage } from './scenario/ScenarioAlertsPage'
import { ScenarioProvider } from './scenario/ScenarioContext'
import { useScenario } from './scenario/useScenario'
import { useThemePreference } from './console/useThemePreference'
import './console/operations.css'
import './scenario/scenario.css'

function ConsoleApp() {
  const scenario = useScenario()
  const theme = useThemePreference()
  const [page, setPage] = useState<ConsolePage>('dashboard')
  const [initialScenarioAlertId, setInitialScenarioAlertId] = useState<string | null>(null)
  // 알림에서 새 실행을 만든 직후에만 쓰는 1회성 딥링크.
  // localStorage 과거 run으로 상세를 자동 복원하지 않는다(기본 진입은 목록 전용).
  const [pendingRunId, setPendingRunId] = useState<string | null>(null)
  const openRun = (runId: string) => {
    window.localStorage.setItem('heatgrid:last-agent-run', runId) // 최근 실행 기록용(자동 복원에는 미사용)
    setPendingRunId(runId)
    setPage('reports')
  }
  const navigate = (next: ConsolePage) => {
    // 사이드바/벨로 AI 활동에 들어오는 경로는 항상 목록 전용으로 시작한다.
    if (next === 'reports') setPendingRunId(null)
    if (next === 'alerts') setInitialScenarioAlertId(null)
    setPage(next)
  }
  const consumePendingRun = useCallback(() => setPendingRunId(null), [])
  const consumeInitialScenarioAlert = useCallback(() => setInitialScenarioAlertId(null), [])
  const exitConsole = () => {
    setPage('dashboard')
    setPendingRunId(null)
    scenario.exitConsole()
  }
  const restartScenario = () => {
    setInitialScenarioAlertId(null)
    setPendingRunId(null)
    scenario.restartScenario()
  }

  if (scenario.state.entryStep !== 'console' || scenario.state.mode == null) return <EntryGate />
  const faultMode = scenario.state.mode === 'fault'

  return <AppShell
    alertCount={faultMode ? (scenario.state.incidentState === 'incident-active' ? scenario.alerts.length : 0) : undefined}
    mode={scenario.state.mode}
    onExit={exitConsole}
    onPageChange={navigate}
    onRefresh={restartScenario}
    page={page}
    simulatedAt={faultMode ? scenario.sensor.state.simulatedAt : null}
  >
    {page === 'dashboard' && <DashboardPage onOpenAlerts={(alertId) => { if (faultMode && alertId != null) scenario.selectAlert(alertId); setInitialScenarioAlertId(alertId ?? null); setPage('alerts') }} theme={theme.resolvedTheme} />}
    {page === 'alerts' && (faultMode ? <ScenarioAlertsPage initialAlertId={initialScenarioAlertId} key={scenario.state.incidentState} onConsumeInitialAlert={consumeInitialScenarioAlert} onOpenAiAction={openRun} /> : <AlertsPage onRunCreated={openRun} />)}
    {page === 'reports' && <AiActivityPage initialRunId={pendingRunId} onConsumeInitialRun={consumePendingRun} />}
    {page === 'settings' && <SettingsPage onThemePreferenceChange={theme.setPreference} themePreference={theme.preference} />}
  </AppShell>
}

function App() {
  return <ScenarioProvider><ConsoleApp /></ScenarioProvider>
}

export default App
