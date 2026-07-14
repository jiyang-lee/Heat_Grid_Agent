import { useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAlerts } from '../api/hooks'
import { Icon, type IconName } from './icons'

export type ConsolePage = 'dashboard' | 'alerts' | 'reports' | 'settings' | 'admin'

interface NavigationItem {
  readonly page: ConsolePage
  readonly label: string
  readonly icon: IconName
}

const navigation: readonly NavigationItem[] = [
  { page: 'dashboard', label: '홈', icon: 'home' },
  { page: 'alerts', label: '알림', icon: 'bell' },
  { page: 'reports', label: '보고서', icon: 'document' },
  { page: 'settings', label: '설정', icon: 'settings' },
  { page: 'admin', label: '관리자', icon: 'shield' },
]

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const

/** 상단바 실시간 시계(30초 틱). */
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
  readonly children: ReactNode
}

export function AppShell({ page, onPageChange, children }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const now = useClock()
  const queryClient = useQueryClient()
  // 알림 벨 배지 = 실제 열린 알림 수.
  const alerts = useAlerts({ status: 'open' })
  const openCount = alerts.data?.length ?? 0
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const date = `${now.getMonth() + 1}월 ${now.getDate()}일 ${WEEKDAYS[now.getDay()]}요일`
  const toggleCollapsed = () => setCollapsed((value) => !value)

  return (
    <div className={`ops-app-shell ${collapsed ? 'collapsed' : ''}`.trim()}>
      <aside className="ops-sidebar">
        <div className="ops-brand">
          <Icon className="brand-drop" fill="currentColor" name="droplet" strokeWidth={0} />
          <div className="brand-text"><strong>HeatGrid</strong><small>AIoT 운영 지원 시스템</small></div>
        </div>
        <nav aria-label="주요 메뉴" className="ops-navigation">
          {navigation.map((item) => <button aria-current={page === item.page ? 'page' : undefined} className={page === item.page ? 'active' : ''} key={item.page} onClick={() => onPageChange(item.page)} type="button"><Icon name={item.icon} /><span>{item.label}</span></button>)}
        </nav>
        <div className="sidebar-bottom">
          <button aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'} className="sidebar-collapse" onClick={toggleCollapsed} type="button"><Icon name="chevron" /></button>
        </div>
      </aside>
      <div className="ops-content-shell">
        <header className="ops-topbar">
          <button aria-label="사이드바 접기/펼치기" className="topbar-menu" onClick={toggleCollapsed} type="button"><Icon name="menu" /></button>
          <div className="mobile-brand">HeatGrid Ops</div>
          <div className="topbar-tools">
            <div className="topbar-clock"><strong>{time}</strong><span>{date}</span></div>
            <button className="refresh-button" onClick={() => void queryClient.invalidateQueries()} type="button"><Icon name="refresh" />새로고침</button>
            <button aria-label={`알림 ${openCount}건`} className="notification-button" onClick={() => onPageChange('alerts')} type="button"><Icon name="bell" />{openCount > 0 && <b>{openCount}</b>}</button>
            <button className="profile-button" type="button"><span><Icon name="users" /></span><strong>운영자 김현우</strong><Icon className="profile-chevron" name="chevron" /></button>
          </div>
        </header>
        <main className="ops-main">{children}</main>
      </div>
    </div>
  )
}
