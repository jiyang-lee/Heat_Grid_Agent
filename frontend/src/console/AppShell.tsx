import { useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { qk, useAlerts } from '../api/hooks'
import { Icon, type IconName } from './icons'
import type { EntryMode } from '../scenario/types'

export type ConsolePage = 'dashboard' | 'alerts' | 'reports' | 'settings' | 'admin'

interface NavigationItem {
  readonly page: ConsolePage
  readonly label: string
  readonly icon: IconName
}

const navigation: readonly NavigationItem[] = [
  { page: 'dashboard', label: '홈', icon: 'home' },
  { page: 'alerts', label: '알림', icon: 'bell' },
  { page: 'reports', label: 'AI 조치', icon: 'activity' },
  { page: 'settings', label: '설정', icon: 'settings' },
]

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const

const pageLabels: Record<ConsolePage, { readonly title: string; readonly summary: string }> = {
  dashboard: { title: '홈', summary: '현재 시스템 요약과 주요 현황을 한눈에 확인하세요.' },
  alerts: { title: '알림', summary: '경보를 선택해 출동 기한과 판단 근거를 확인하세요.' },
  reports: { title: 'AI 조치', summary: '위험도와 리드타임을 기준으로 조치와 문서를 관리합니다.' },
  settings: { title: '설정', summary: '개인 운영 환경과 알림 수신, 업무 화면 기본 설정을 관리합니다.' },
  admin: { title: '관리', summary: '운영 권한과 시스템 정책을 관리합니다.' },
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
  readonly mode: EntryMode
  readonly simulatedAt: string | null
  readonly alertCount?: number
  readonly onExit: () => void
  readonly children: ReactNode
}

export function AppShell({ page, onPageChange, mode, simulatedAt, alertCount, onExit, children }: Props) {
  const [collapsed, setCollapsed] = useState(true)
  const now = useClock()
  const queryClient = useQueryClient()
  const alerts = useAlerts({ status: 'open' })
  const displayNow = simulatedAt ? new Date(simulatedAt) : now
  const openCount = alertCount ?? alerts.data?.length ?? 0
  const time = `${String(displayNow.getHours()).padStart(2, '0')}:${String(displayNow.getMinutes()).padStart(2, '0')}`
  const date = `${displayNow.getFullYear()}년 ${displayNow.getMonth() + 1}월 ${displayNow.getDate()}일 ${WEEKDAYS[displayNow.getDay()]}요일`
  const toggleCollapsed = () => setCollapsed((value) => !value)
  const pageLabel = pageLabels[page]

  const refreshAll = () => {
    void Promise.allSettled([
      queryClient.refetchQueries({ queryKey: qk.prioritySnapshot }),
      queryClient.refetchQueries({ queryKey: ['alerts'] }),
      queryClient.refetchQueries({ queryKey: qk.health }),
      queryClient.refetchQueries({ queryKey: ['review-tasks'] }),
    ])
  }

  return (
    <div className={`ops-app-shell ${collapsed ? 'collapsed' : ''}`.trim()}>
      <aside className="ops-sidebar">
        <div className="ops-brand">
          <Icon className="brand-drop" fill="currentColor" name="droplet" strokeWidth={0} />
          <div className="brand-text">
            <strong>HeatGrid</strong>
            <small>AIoT 운영 콘솔</small>
          </div>
        </div>
        <nav aria-label="메인 탐색" className="ops-navigation">
          {navigation.map((item) => (
            <button
              aria-label={item.label}
              aria-current={page === item.page ? 'page' : undefined}
              className={page === item.page ? 'active' : ''}
              key={item.page}
              onClick={() => onPageChange(item.page)}
              type="button"
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button aria-label={collapsed ? '메뉴 펼치기' : '메뉴 접기'} className="sidebar-collapse" onClick={toggleCollapsed} type="button">
            <Icon name="chevron" />
          </button>
        </div>
      </aside>
      <div className="ops-content-shell">
        <header className="ops-topbar">
          <div className="topbar-page-area"><div className="topbar-page-context"><strong>{pageLabel.title}</strong><span>{pageLabel.summary}</span></div></div>
          <div className="topbar-tools">
            <span className={`topbar-mode mode-${mode}`}><i />{mode === 'fault' ? '고장 시나리오' : '정상 운영'}</span>
            <div className="topbar-clock">
              <strong>{time}</strong>
              <span>{date}</span>
            </div>
            <button className="refresh-button" onClick={refreshAll} type="button">
              <Icon name="refresh" />
              새로고침
            </button>
            <button className="version-exit-button" onClick={onExit} type="button"><Icon name="x" />버전 종료</button>
            <button aria-label={`열린 알림 ${openCount}개`} className="notification-button" onClick={() => onPageChange('alerts')} type="button">
              <Icon name="bell" />
              {openCount > 0 && <b>{openCount}</b>}
            </button>
            <button className="profile-button" type="button">
              <span><Icon name="users" /></span>
              <strong>운영자</strong>
              <Icon className="profile-chevron" name="chevron" />
            </button>
          </div>
        </header>
        <main className="ops-main">{children}</main>
      </div>
    </div>
  )
}
