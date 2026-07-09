/** 헤더 — 로고 + 타이틀 + 뷰 전환(지도/운영) + 헬스 + 긴급/주의/정상 요약. */

import { summaryCounts } from '../domain/model'
import { useHealth } from '../api/hooks'

export type AppView = 'map' | 'ops'

interface Props {
  appView: AppView
  onAppView: (v: AppView) => void
}

export default function Header({ appView, onAppView }: Props) {
  const c = summaryCounts()
  const health = useHealth()
  const h = health.data

  return (
    <header className="app-header">
      <svg className="logo" viewBox="0 0 48 48" aria-hidden="true">
        <defs>
          <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#00e5ff" />
            <stop offset="1" stopColor="#2979ff" />
          </linearGradient>
        </defs>
        <path d="M24 4 L42 14 V34 L24 44 L6 34 V14 Z" fill="none" stroke="url(#lg)" strokeWidth="2" />
        <path d="M16 30 q4-14 8 0 q4 12 8 -2" fill="none" stroke="#00e5ff" strokeWidth="2.4" strokeLinecap="round" />
        <circle cx="24" cy="22" r="2.6" fill="#00e5ff" />
      </svg>
      <div className="titlewrap">
        <h1>지역난방 보조운영 에이전트</h1>
        <div className="sub">세종 1생활권 · 지역난방 31개 단지 · MACHINE ROOM CONTROL</div>
      </div>

      <div className="app-nav">
        <button type="button" className={`nav-b ${appView === 'map' ? 'on' : ''}`} onClick={() => onAppView('map')}>
          지도 관제
        </button>
        <button type="button" className={`nav-b ${appView === 'ops' ? 'on' : ''}`} onClick={() => onAppView('ops')}>
          운영 콘솔
        </button>
      </div>

      <div className="summary">
        {h && (
          <div className="badge health" title={`input=${h.input} db=${h.database} openai=${h.openai}`}>
            <i className={`dot ${h.database === 'unavailable' ? 'u' : 'n'}`} />
            DB {h.database} · LLM {h.openai}
          </div>
        )}
        <div className="badge">
          <i className="dot u" />
          긴급 <b className="u">{c.urgent}</b>
        </div>
        <div className="badge">
          <i className="dot c" />
          주의 <b className="c">{c.caution}</b>
        </div>
        <div className="badge">
          <i className="dot n" />
          정상 <b className="n">{c.normal}</b>
        </div>
      </div>
    </header>
  )
}
