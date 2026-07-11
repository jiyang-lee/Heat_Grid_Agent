import type { ReactNode } from 'react'
import { Icon, type IconName } from './icons'

export type ConsolePage = 'dashboard' | 'alerts' | 'reports' | 'settings' | 'admin'

interface NavigationItem {
  readonly page: ConsolePage
  readonly label: string
  readonly icon: IconName
}

const navigation: readonly NavigationItem[] = [
  { page: 'dashboard', label: '홈', icon: 'home' },
  { page: 'alerts', label: '알림', icon: 'alert' },
  { page: 'reports', label: '보고서/작업지시서', icon: 'document' },
  { page: 'settings', label: '설정', icon: 'settings' },
  { page: 'admin', label: '관리자', icon: 'shield' },
]

interface Props {
  readonly page: ConsolePage
  readonly onPageChange: (page: ConsolePage) => void
  readonly children: ReactNode
}

export function AppShell({ page, onPageChange, children }: Props) {
  return (
    <div className="ops-app-shell">
      <aside className="ops-sidebar">
        <div className="ops-brand"><span className="ops-brand-mark"><span /><span /><span /></span><strong>지역난방 운영 보조</strong></div>
        <nav aria-label="주요 메뉴" className="ops-navigation">
          {navigation.map((item) => <button aria-current={page === item.page ? 'page' : undefined} className={page === item.page ? 'active' : ''} key={item.page} onClick={() => onPageChange(item.page)} type="button"><Icon name={item.icon} /><span>{item.label}</span></button>)}
        </nav>
        <div className="sidebar-bottom">
          <section className="system-summary"><header>시스템 상태 <span className="status-inline tone-success">정상</span></header><p><span>연결 설비</span><strong>31 / 31</strong></p><p><span>데이터 수집 시간</span><strong>1분 전</strong></p></section>
          <small>© 2026 HeatGrid Ops<br />v2.0.0</small>
        </div>
      </aside>
      <div className="ops-content-shell">
        <header className="ops-topbar"><div className="mobile-brand">HeatGrid Ops</div><div className="topbar-tools"><label className="topbar-search"><Icon name="search" /><input aria-label="건물, 기계실, 설비 검색" placeholder="검색 (건물명, 기계실명, 설비)" /></label><button className="date-control" type="button"><Icon name="calendar" />2026.07.05 - 2026.07.11<Icon name="chevron" /></button><button aria-label="알림 12건" className="notification-button" type="button"><Icon name="alert" /><b>12</b></button><button className="profile-button" type="button"><span>운</span><strong>원운영<small>운영센터 관리자</small></strong><Icon name="chevron" /></button></div></header>
        <main className="ops-main">{children}</main>
      </div>
    </div>
  )
}
