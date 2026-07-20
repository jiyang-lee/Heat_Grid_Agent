import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAlerts } from '../api/hooks'
import { operationsClock } from './operationsTime'
import { Icon, type IconName } from './icons'

export type ConsolePage = 'dashboard' | 'alerts' | 'ai-action' | 'operations-reports' | 'settings' | 'admin'

interface NavigationItem {
  readonly page: ConsolePage
  readonly label: string
  readonly icon: IconName
}

const navigation: readonly NavigationItem[] = [
  { page: 'dashboard', label: '홈', icon: 'home' },
  { page: 'alerts', label: '알림', icon: 'bell' },
  { page: 'ai-action', label: 'AI 조치', icon: 'activity' },
  { page: 'operations-reports', label: '운영 보고서', icon: 'document' },
  { page: 'settings', label: '설정', icon: 'settings' },
]

const pageLabels: Record<ConsolePage, { readonly title: string }> = {
  dashboard: { title: '홈' },
  alerts: { title: '알림' },
  'ai-action': { title: 'AI 조치' },
  'operations-reports': { title: '운영 보고서' },
  settings: { title: '설정' },
  admin: { title: '관리자' },
}

function useClock(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

interface Props {
  readonly page: ConsolePage
  readonly onPageChange: (page: ConsolePage) => void
  readonly simulatedAt: string | null
  readonly alertCount?: number
  readonly onRefresh?: () => void | Promise<void>
  readonly children: ReactNode
}

export function AppShell({ page, onPageChange, simulatedAt, alertCount, onRefresh, children }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const now = useClock()
  const queryClient = useQueryClient()
  const alerts = useAlerts({ status: 'open' })
  const display = operationsClock(simulatedAt ?? now)
  const openCount = alertCount ?? alerts.data?.length ?? 0
  const pageLabel = pageLabels[page]

  const refreshAll = async (event: MouseEvent<HTMLButtonElement>) => {
    if (refreshing) return
    const button = event.currentTarget
    setRefreshing(true)
    try {
      await onRefresh?.()
      await queryClient.refetchQueries({ type: 'active' })
    } finally {
      setRefreshing(false)
      button.blur()
    }
  }

  return <div className={`ops-app-shell ${collapsed ? 'collapsed' : ''}`.trim()}>
    <aside className="ops-sidebar">
      <div className="ops-brand"><Icon className="brand-drop" fill="currentColor" name="droplet" strokeWidth={0} /><div className="brand-text"><strong>HeatGrid</strong><small>AIoT 운영 콘솔</small></div></div>
      <nav aria-label="주요 화면" className="ops-navigation">
        {navigation.map((item) => <button aria-current={page === item.page ? 'page' : undefined} aria-label={item.label} className={page === item.page ? 'active' : ''} key={item.page} onClick={() => onPageChange(item.page)} title={item.label} type="button"><Icon name={item.icon} /><span>{item.label}</span></button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="profile-button sidebar-profile"><span><Icon name="users" /></span><strong>운영자</strong></div>
        <button aria-label={collapsed ? '메뉴 펼치기' : '메뉴 접기'} className="sidebar-collapse" onClick={() => setCollapsed((value) => !value)} type="button"><Icon name="chevron" /></button>
      </div>
    </aside>
    <div className="ops-content-shell">
      <header className="ops-topbar">
        <div className="topbar-page-area"><div className="topbar-page-context"><strong>{pageLabel.title}</strong></div></div>
        <div className="topbar-tools">
          <div className="topbar-clock"><strong>{display.time}</strong><span>{display.date}</span></div>
          <button aria-label={`열린 알림 ${openCount}건`} className="notification-button" onClick={() => onPageChange('alerts')} type="button"><Icon name="bell" />{openCount > 0 && <b>{openCount}</b>}</button>
          <button aria-busy={refreshing} aria-label="새로고침" className={`refresh-button ${refreshing ? 'is-refreshing' : ''}`.trim()} disabled={refreshing} onClick={(event) => void refreshAll(event)} type="button"><Icon name="refresh" />{refreshing ? '갱신 중' : '새로고침'}</button>
        </div>
      </header>
      <main className="ops-main">{children}</main>
    </div>
  </div>
}
