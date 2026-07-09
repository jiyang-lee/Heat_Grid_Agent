/**
 * 앱 셸 — heating_agent.html의 2뷰 구조 이식.
 *
 * 도시(CITY) 뷰: MapLibre 3D 지도 + 수리 우선순위 사이드.
 * 기계실(ROOM) 뷰: 단지 클릭 시 진입 (Phase D에서 스키매틱/상세 구현).
 */

import { useState } from 'react'
import './theme.css'
import Header, { type AppView } from './components/Header'
import MapView from './map/MapView'
import PriorityAside from './components/PriorityAside'
import DetailAside from './components/DetailAside'
import RoomSchematic from './room/RoomSchematic'
import OpsConsole from './ops/OpsConsole'
import { complexById } from './domain/model'

type View = 'city' | 'room'

function App() {
  const [appView, setAppView] = useState<AppView>('map')
  const [view, setView] = useState<View>('city')
  const [selBld, setSelBld] = useState<number | null>(null)
  const [selMachine, setSelMachine] = useState<string | null>(null)

  const enterBuilding = (id: number) => {
    setSelBld(id)
    setSelMachine(null)
    setView('room')
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
      <Header appView={appView} onAppView={setAppView} />
      {appView === 'ops' && <OpsConsole />}
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
          <div className="stage">
            {city ? (
              <MapView selectedId={selBld} onSelectComplex={enterBuilding} />
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
              주의
            </span>
            <span>
              <i className="dot n" />
              정상
            </span>
            <span className="note">
              {city
                ? '· 상태=총관리비 단가(대리 열부하) 기반 데모 · 위치=실제 위경도'
                : '· 회색=해당 PreDist 센서 미탑재(감시 불가)'}
            </span>
          </div>
        </section>

        {/* 보조 패널 */}
        <aside className="panel">
          <div className="panel-head">
            <span>{city ? '수리 우선순위' : '단지 · 설비 상세'}</span>
            <span className="tag">{city ? 'PRIORITY' : 'DETAIL'}</span>
          </div>
          {city ? (
            <div className="aside-body">
              <PriorityAside selectedId={selBld} onSelect={enterBuilding} />
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
