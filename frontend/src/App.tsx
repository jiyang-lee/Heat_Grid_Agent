import { useState } from 'react'
import { AdminPage } from './console/AdminPage'
import { AlertsPage } from './console/AlertsPage'
import { AppShell, type ConsolePage } from './console/AppShell'
import { DashboardPage } from './console/DashboardPage'
import { ReportsPage } from './console/ReportsPage'
import { SettingsPage } from './console/SettingsPage'
import { ShowcasePage } from './console/ShowcasePage'
import './console/operations.css'

function isShowcase(): boolean {
  return new URLSearchParams(window.location.search).get('showcase') === '1'
}

function App() {
  const [page, setPage] = useState<ConsolePage>('dashboard')
  if (isShowcase()) return <ShowcasePage />
  return <AppShell onPageChange={setPage} page={page}>
    {page === 'dashboard' && <DashboardPage />}
    {page === 'alerts' && <AlertsPage />}
    {page === 'reports' && <ReportsPage />}
    {page === 'settings' && <SettingsPage />}
    {page === 'admin' && <AdminPage />}
  </AppShell>
}

export default App
