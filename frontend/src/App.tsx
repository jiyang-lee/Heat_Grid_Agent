import { useCallback, useState } from 'react'
import { AdminPage } from './console/AdminPage'
import { AlertsPage } from './console/AlertsPage'
import { AiActivityPage } from './console/ai-activity/AiActivityPage'
import { AppShell, type ConsolePage } from './console/AppShell'
import { DashboardPage } from './console/DashboardPage'
import { SettingsPage } from './console/SettingsPage'
import { ShowcasePage } from './console/ShowcasePage'
import './console/operations.css'

import { useEffect, useState } from 'react'
import './theme.css'
import Header, { type AppView } from './components/Header'
import MapView from './map/MapView'
import PriorityAside from './components/PriorityAside'
import DetailAside from './components/DetailAside'
import RoomSchematic from './room/RoomSchematic'
import OpsConsole from './ops/OpsConsole'
import { complexById } from './domain/model'
import { useAlerts, usePrioritySnapshot } from './api/hooks'

type View = 'city' | 'room'
type Theme = 'dark' | 'light'

function App() {
  const [appView, setAppView] = useState<AppView>('map')
  const [view, setView] = useState<View>('city')
  const [selBld, setSelBld] = useState<number | null>(null)
  const [selMachine, setSelMachine] = useState<string | null>(null)
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('theme') === 'light' ? 'light' : 'dark'))
  const [initialAlertId, setInitialAlertId] = useState<string | null>(null)
  const prioritySnapshot = usePrioritySnapshot()
  const alerts = useAlerts({ status: 'all' })
  const evaluation = prioritySnapshot.data?.evaluation ?? null
  const priorityResults = prioritySnapshot.data?.results ?? []
  const prioritySummary = {
    urgent: priorityResults.filter((item) => item.freshness_status === 'fresh' && item.priority_level === 'urgent').length,
    high: priorityResults.filter((item) => item.freshness_status === 'fresh' && item.priority_level === 'high').length,
    unavailable: priorityResults.filter((item) => item.freshness_status !== 'fresh').length,
  }

  // 테마를 <html data-theme>에 반영 + localStorage 저장.
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])
  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  const enterBuilding = (id: number) => {
    setSelBld(id)
    setSelMachine(null)
    setView('room')
  }
  const selectBuilding = (id: number) => {
    setSelBld(id)
    setSelMachine(null)
  }
  const openOps = (alertId: string) => {
    setInitialAlertId(alertId)
    setAppView('ops')
  }
  const backToCity = () => {
    setSelMachine(null)
    setView('city')
  }
  const selectMachine = (key: string) => setSelMachine((prev) => (prev === key ? null : key))

  const city = view === 'city'
  const sel = selBld != null ? complexById.get(selBld) ?? null : null

  return (
    <div className="app">
      <Header
        appView={appView}
        onAppView={setAppView}
        theme={theme}
        onToggleTheme={toggleTheme}
        prioritySummary={prioritySummary}
      />
      {appView === 'ops' && <OpsConsole initialAlertId={initialAlertId} />}
      {appView === 'map' && (
      <div className="wrap">
        {/* 메인 패널 */}
        <section className="panel">
          <div className="panel-head">
            <span>{city ? '단지 관제 · CITY MAP' : '기계실 관제 · MACHINE ROOM'}</span>
            <span className="tag">{city ? '31 SITES' : '7 UNITS'}</span>
            {!city && (
              <button type="button" className="btn-back" onClick={backToCity}>
                ← 지도로
              </button>
            )}
          </div>
          <div className={`stage ${city ? '' : 'room'}`.trim()}>
            {city ? (
              <MapView
                onSelectComplex={selectBuilding}
                theme={theme}
                results={priorityResults}
                loading={prioritySnapshot.isLoading}
                error={prioritySnapshot.isError}
              />
            ) : sel ? (
              <RoomSchematic complex={sel} selMachine={selMachine} onSelectMachine={selectMachine} />
            ) : null}
          </div>
          <div className="legend">
            <span>
              <i className="dot u" />
              긴급
            </span>
            <span>
              <i className="dot c" />
              높음
            </span>
            <span>
              <i className="dot n" />
              중간·낮음
            </span>
            <span>
              <i className="dot stale" />
              지연·누락
            </span>
            <span className="note">
              {city
                ? `· 모델 평가 ${evaluation ? new Date(evaluation.as_of_time).toLocaleString('ko-KR') : '조회 중'} · 위치=정적 메타데이터`
                : '· 회색=해당 PreDist 센서 미탑재(감시 불가)'}
            </span>
          </div>
        </section>

        {/* 보조 패널 */}
        <aside className="panel">
          <div className="panel-head">
            <span>{city ? '전체 Priority 순위' : '단지 · 설비 상세'}</span>
            <span className="tag">{city ? 'PRIORITY' : 'DETAIL'}</span>
          </div>
          {city ? (
            <div className="aside-body">
              <PriorityAside
                selectedId={selBld}
                onSelect={selectBuilding}
                onOpenRoom={enterBuilding}
                onOpenOps={openOps}
                evaluation={evaluation}
                results={priorityResults}
                alerts={alerts.data ?? []}
                loading={prioritySnapshot.isLoading}
                error={prioritySnapshot.isError}
              />
            </div>
          ) : sel ? (
            <DetailAside complex={sel} selMachine={selMachine} onSelectMachine={selectMachine} />
          ) : null}
        </aside>
      </div>
      )}
    </div>
  )
}

export default App
