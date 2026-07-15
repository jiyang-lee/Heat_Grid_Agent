import { useCallback, useState } from 'react'
import { AdminPage } from './console/AdminPage'
import { AlertsPage } from './console/AlertsPage'
import { AiActivityPage } from './console/ai-activity/AiActivityPage'
import { AppShell, type ConsolePage } from './console/AppShell'
import { DashboardPage } from './console/DashboardPage'
import { SettingsPage } from './console/SettingsPage'
import { ShowcasePage } from './console/ShowcasePage'
import './console/operations.css'

function isShowcase(): boolean {
  return new URLSearchParams(window.location.search).get('showcase') === '1'
}

function App() {
  const [page, setPage] = useState<ConsolePage>('dashboard')
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
    setPage(next)
  }
  const consumePendingRun = useCallback(() => setPendingRunId(null), [])
  if (isShowcase()) return <ShowcasePage />
  return <AppShell onPageChange={navigate} page={page}>
    {page === 'dashboard' && <DashboardPage onOpenAlerts={() => setPage('alerts')} />}
    {page === 'alerts' && <AlertsPage onRunCreated={openRun} />}
    {page === 'reports' && <AiActivityPage initialRunId={pendingRunId} onConsumeInitialRun={consumePendingRun} />}
    {page === 'settings' && <SettingsPage />}
    {page === 'admin' && <AdminPage />}
  </AppShell>
}

export default App
