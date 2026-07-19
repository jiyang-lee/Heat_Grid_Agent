import { useCallback, useState } from 'react'
import { AlertsPage } from './console/AlertsPage'
import { AdminPage } from './console/AdminPage'
import { AiActivityPage } from './console/ai-activity/AiActivityPage'
import { AppShell, type ConsolePage } from './console/AppShell'
import { DashboardPage } from './console/DashboardPage'
import { OperationsProvider } from './console/OperationsContext'
import { OperationsReportsPage } from './console/OperationsReportsPage'
import { SettingsPage } from './console/SettingsPage'
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
  const [initialAlertId, setInitialAlertId] = useState<string | null>(null)
  const [pendingRunId, setPendingRunId] = useState<string | null>(null)
  const mode = scenario.state.mode ?? 'normal'
  const replay = mode === 'fault'

  const navigate = (next: ConsolePage) => {
    if (next === 'ai-action') setPendingRunId(null)
    if (next === 'alerts') setInitialAlertId(null)
    setPage(next)
  }
  const openRun = (runId: string) => {
    setPendingRunId(runId)
    setPage('ai-action')
  }
  const consumePendingRun = useCallback(() => setPendingRunId(null), [])
  const consumeInitialAlert = useCallback(() => setInitialAlertId(null), [])
  const openAlerts = (alertId?: string) => {
    if (replay && alertId != null) scenario.selectAlert(alertId)
    setInitialAlertId(alertId ?? null)
    setPage('alerts')
  }

  return <OperationsProvider initialSubstationId={scenario.state.selectedSubstationId} mode={mode} referenceTime={replay ? scenario.sensor.state.simulatedAt : null}>
    <AppShell alertCount={replay && scenario.state.incidentState === 'incident-active' ? scenario.alerts.length : undefined} onPageChange={navigate} page={page} simulatedAt={replay ? scenario.sensor.state.simulatedAt : null}>
      {page === 'dashboard' && <DashboardPage onOpenAlerts={openAlerts} theme={theme.resolvedTheme} />}
      {page === 'alerts' && (replay ? <ScenarioAlertsPage initialAlertId={initialAlertId} key={scenario.state.incidentState} onConsumeInitialAlert={consumeInitialAlert} onOpenAiAction={openRun} /> : <AlertsPage onRunCreated={openRun} />)}
      {page === 'ai-action' && <AiActivityPage entryMode={mode} incidentAlertId={replay && pendingRunId != null ? scenario.state.selectedAlertId : null} initialRunId={pendingRunId} onConsumeInitialRun={consumePendingRun} />}
      {page === 'operations-reports' && <OperationsReportsPage />}
      {page === 'settings' && <SettingsPage onOpenAdmin={() => setPage('admin')} onThemePreferenceChange={theme.setPreference} themePreference={theme.preference} />}
      {page === 'admin' && <AdminPage onModeChanged={() => setPage('dashboard')} />}
    </AppShell>
  </OperationsProvider>
}

export default function App() {
  return <ScenarioProvider><ConsoleApp /></ScenarioProvider>
}
