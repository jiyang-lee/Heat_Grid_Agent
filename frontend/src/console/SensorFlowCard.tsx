/**
 * 실시간 센서 흐름 카드 — 클라이언트 시뮬레이션(LIVE 데모).
 * 백엔드에 원시 센서 시계열 API가 없어(evidence의 sensor_summaries는 모델 피처 요약)
 * 권장범위 내 가상값을 결정적 시드로 생성한다. Math.random을 렌더에서 쓰지 않는다.
 *
 * facility prop: 홈 '주요 알림'에서 선택한 설비. 설비별 결정적 시드로 서로 다른
 * 곡선을 보여준다(여전히 가상). 실 센서 시계열 계약이 생기면 이 prop을 키로
 * fetch하도록 seedSeries/tick 부분만 교체하면 된다.
 *
 * 창: 최근 30분(1분 간격 31포인트). 5초마다 현재값이 갱신되고 1분마다 창이 민다.
 */

import { useEffect, useRef, useState } from 'react'
import { Icon, type IconName } from './icons'
import { SurfaceCard } from './ui'

export interface SensorFacility {
  readonly id: number
  readonly name: string
}

interface SeriesDef {
  readonly key: string
  readonly label: string
  readonly tile: string
  readonly unit: string
  readonly icon: IconName
  readonly min: number
  readonly max: number
  readonly base: number
  readonly decimals: number
  readonly className: string
}

const SERIES: readonly SeriesDef[] = [
  { key: 'supply', label: '공급온도', tile: '현재 공급온도', unit: '°C', icon: 'thermometer', min: 75, max: 85, base: 78.5, decimals: 1, className: 'sf-supply' },
  { key: 'return', label: '환수온도', tile: '현재 환수온도', unit: '°C', icon: 'thermometer', min: 40, max: 50, base: 43.2, decimals: 1, className: 'sf-return' },
  { key: 'pressure', label: '압력', tile: '압력', unit: 'MPa', icon: 'gauge', min: 0.6, max: 0.9, base: 0.72, decimals: 2, className: 'sf-pressure' },
  { key: 'flow', label: '유량', tile: '유량', unit: 'm³/h', icon: 'flow', min: 100, max: 160, base: 128.4, decimals: 1, className: 'sf-flow' },
]

/** 최근 30분을 1분 간격으로 그린다(0..30 → 31포인트). 축 라벨은 5분마다. */
const POINTS = 31
const STEP_MS = 60_000
const TICK_MS = 5_000
const TICKS_PER_STEP = STEP_MS / TICK_MS
const JITTER = 0.14
/** 미선택 시 표시할 수집 대상 기계실 수(시안 고정 문구). */
const DEFAULT_ROOM_COUNT = 12

const CHART_W = 720
const BAND_H = 45
const BAND_GAP = 15
const CHART_H = SERIES.length * (BAND_H + BAND_GAP) + BAND_GAP

/** 결정적 PRNG(mulberry32) — 같은 설비면 항상 같은 곡선이 나오게. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** 설비별 앵커값 — 기준값을 설비 id에 따라 권장범위 안에서 소폭 이동. */
function anchorFor(def: SeriesDef, facilityId: number): number {
  const span = def.max - def.min
  const shift = (((facilityId % 9) - 4) / 4) * span * 0.18
  return Math.min(def.max - span * 0.1, Math.max(def.min + span * 0.1, def.base + shift))
}

/** 평균회귀 + 소폭 지터로 권장범위 안에서 자연스럽게 흔들리는 다음 값. */
function nextValue(def: SeriesDef, prev: number, anchor: number, rand: () => number): number {
  const span = def.max - def.min
  const drift = (rand() - 0.5) * span * JITTER
  const pull = (anchor - prev) * 0.18
  return Math.min(def.max, Math.max(def.min, prev + drift + pull))
}

function seedSeries(def: SeriesDef, anchor: number, rand: () => number): number[] {
  let value = anchor
  return Array.from({ length: POINTS }, () => (value = nextValue(def, value, anchor, rand)))
}

function formatValue(def: SeriesDef, value: number): string {
  return value.toFixed(def.decimals)
}

const pad2 = (value: number) => String(value).padStart(2, '0')

function formatAxis(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

interface Props {
  readonly facility?: SensorFacility | null
}

export default function SensorFlowCard({ facility = null }: Props) {
  const facilityId = facility?.id ?? 0
  const randRef = useRef<() => number>(mulberry32(1))
  const tickRef = useRef(0)
  const [data, setData] = useState<readonly number[][]>(() => SERIES.map((def) => seedSeries(def, anchorFor(def, facilityId), mulberry32(facilityId * 1000 + 1))))
  const [updatedAt, setUpdatedAt] = useState(() => new Date())
  const [menuOpen, setMenuOpen] = useState(false)

  const reseed = (id: number) => {
    const rand = mulberry32(id * 1000 + 1)
    randRef.current = rand
    tickRef.current = 0
    setData(SERIES.map((def) => seedSeries(def, anchorFor(def, id), rand)))
    setUpdatedAt(new Date())
  }

  // 설비 전환 시 해당 설비의 결정적 시드로 재생성하고 5초 틱을 돌린다.
  // 틱마다 현재값(마지막 포인트)을 갱신하고, 1분(12틱)마다 창을 한 칸 민다.
  useEffect(() => {
    reseed(facilityId)
    const timer = window.setInterval(() => {
      tickRef.current += 1
      const shift = tickRef.current % TICKS_PER_STEP === 0
      setData((prev) => prev.map((values, index) => {
        const def = SERIES[index]
        const next = nextValue(def, values[values.length - 1], anchorFor(def, facilityId), randRef.current)
        return shift ? [...values.slice(1), next] : [...values.slice(0, -1), next]
      }))
      setUpdatedAt(new Date())
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [facilityId])

  const xAt = (index: number) => (index / (POINTS - 1)) * CHART_W
  const axisIndexes = [0, 5, 10, 15, 20, 25, 30]
  const axisLabels = axisIndexes.map((index) => {
    const at = new Date(updatedAt.getTime() - (POINTS - 1 - index) * STEP_MS)
    return index === POINTS - 1 ? `${formatAxis(at)} (현재)` : formatAxis(at)
  })
  const subText = facility ? `${facility.name} · 최근 30분` : `기계실 ${DEFAULT_ROOM_COUNT} · 최근 30분`

  return (
    <SurfaceCard
      action={
        <div className="sf-head">
          <span className="sf-sub">{subText}</span>
          <span className="live-badge">LIVE</span>
          <div className="sf-right">
            <span className="sf-meta"><i className="live-dot" />5초 전 업데이트</span>
            <button aria-label="센서 흐름 새로고침" className="sf-icon-button" onClick={() => reseed(facilityId)} type="button"><Icon name="refresh" /></button>
            <div className="sf-more">
              <button aria-expanded={menuOpen} aria-label="더보기" className="sf-icon-button" onClick={() => setMenuOpen((value) => !value)} type="button"><Icon name="more" /></button>
              {menuOpen && (
                <div className="sf-menu" role="menu">
                  <button onClick={() => { reseed(facilityId); setMenuOpen(false) }} role="menuitem" type="button">기준 데이터로 리셋</button>
                </div>
              )}
            </div>
          </div>
        </div>
      }
      className="sensor-flow"
      title="실시간 센서 흐름"
    >
      <div className="sensor-tiles">
        {SERIES.map((def, index) => <article className={`sensor-tile ${def.className}`} key={def.key}><span className="tile-icon"><Icon name={def.icon} /></span><div><p>{def.tile}</p><strong>{formatValue(def, data[index][POINTS - 1])} <em>{def.unit}</em></strong></div></article>)}
      </div>
      <div className="sf-chart-row">
        <div className="sf-legend">
          {SERIES.map((def) => <p key={def.key}><b><i className={`sf-dot ${def.className}`} />{def.label} ({def.unit})</b><span>권장 {def.min} ~ {def.max}</span></p>)}
        </div>
        <div className="sf-chart-mid">
          <svg aria-label="센서 시뮬레이션 추이 차트" className="sf-svg" preserveAspectRatio="none" role="img" viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
            {SERIES.map((def, seriesIndex) => {
              const bandTop = BAND_GAP + seriesIndex * (BAND_H + BAND_GAP)
              const yAt = (value: number) => bandTop + BAND_H - ((value - def.min) / (def.max - def.min)) * BAND_H
              const points = data[seriesIndex].map((value, index) => `${xAt(index)},${yAt(value)}`).join(' ')
              return (
                <g className={def.className} key={def.key}>
                  <line className="sf-grid-line" x1="0" x2={CHART_W} y1={bandTop + BAND_H} y2={bandTop + BAND_H} />
                  <polyline points={points} />
                  {data[seriesIndex].map((value, index) => <circle cx={xAt(index)} cy={yAt(value)} key={index} r="2.4" />)}
                </g>
              )
            })}
          </svg>
          <div className="sf-axis">{axisLabels.map((label, index) => <span key={axisIndexes[index]}>{label}</span>)}</div>
        </div>
        <div className="sf-values">
          {SERIES.map((def, index) => <span className={`sf-value ${def.className}`} key={def.key}>{formatValue(def, data[index][POINTS - 1])}</span>)}
        </div>
      </div>
    </SurfaceCard>
  )
}
