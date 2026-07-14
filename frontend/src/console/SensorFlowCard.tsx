/**
 * 실시간 센서 흐름 카드 — 클라이언트 시뮬레이션(DEMO).
 * 백엔드에 원시 센서 시계열 API가 없어(evidence의 sensor_summaries는 모델 피처 요약)
 * 권장범위 내 가상값을 생성한다.
 *
 * facility prop: 홈 '주요 알림'에서 선택한 설비. 설비별 결정적 시드로 서로 다른
 * 곡선을 보여준다(여전히 가상). 실 센서 시계열 계약이 생기면 이 prop을 키로
 * fetch하도록 seedSeries/tick 부분만 교체하면 된다.
 *
 * 기간 버튼: 실시간(5초 틱 라이브) / 6시간 / 일주일 / 한달 (정적 스냅샷).
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

type RangeKey = 'live' | '6h' | '7d' | '30d'

interface RangeDef {
  readonly key: RangeKey
  readonly label: string
  /** 포인트 간 간격(ms). 차트는 항상 POINTS개 포인트로 그린다. */
  readonly stepMs: number
  /** 지터 크기 — 긴 구간일수록 변동 폭을 키워 자연스럽게. */
  readonly jitter: number
  readonly live: boolean
  /** 설비 시드와 조합할 기간별 시드 소금값. */
  readonly seedSalt: number
}

const POINTS = 30
const TICK_MS = 5_000
const RANGES: readonly RangeDef[] = [
  { key: 'live', label: '실시간', stepMs: TICK_MS, jitter: 0.12, live: true, seedSalt: 1 },
  { key: '6h', label: '6시간', stepMs: (6 * 3_600_000) / (POINTS - 1), jitter: 0.22, live: false, seedSalt: 2 },
  { key: '7d', label: '일주일', stepMs: (7 * 86_400_000) / (POINTS - 1), jitter: 0.3, live: false, seedSalt: 3 },
  { key: '30d', label: '한달', stepMs: (30 * 86_400_000) / (POINTS - 1), jitter: 0.35, live: false, seedSalt: 4 },
]

const CHART_W = 720
const BAND_H = 44
const BAND_GAP = 14
const CHART_H = SERIES.length * (BAND_H + BAND_GAP) + BAND_GAP

/** 결정적 PRNG(mulberry32) — 같은 설비·기간이면 항상 같은 곡선이 나오게. */
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
function nextValue(def: SeriesDef, prev: number, jitter: number, anchor: number, rand: () => number): number {
  const span = def.max - def.min
  const drift = (rand() - 0.5) * span * jitter
  const pull = (anchor - prev) * 0.18
  return Math.min(def.max, Math.max(def.min, prev + drift + pull))
}

function seedSeries(def: SeriesDef, jitter: number, anchor: number, rand: () => number): number[] {
  let value = anchor
  return Array.from({ length: POINTS }, () => (value = nextValue(def, value, jitter, anchor, rand)))
}

function formatValue(def: SeriesDef, value: number): string {
  return value.toFixed(def.decimals)
}

const pad2 = (value: number) => String(value).padStart(2, '0')

function formatClock(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
}

/** 축 라벨 — 기간에 따라 시각/일자 표기를 바꾼다. */
function formatAxis(date: Date, range: RangeDef): string {
  if (range.key === 'live') return formatClock(date)
  if (range.key === '6h') return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
  return `${date.getMonth() + 1}/${date.getDate()}`
}

interface Props {
  readonly facility?: SensorFacility | null
}

export default function SensorFlowCard({ facility = null }: Props) {
  const [rangeKey, setRangeKey] = useState<RangeKey>('live')
  const range = RANGES.find((item) => item.key === rangeKey) ?? RANGES[0]
  const facilityId = facility?.id ?? 0
  const randRef = useRef<() => number>(Math.random)
  const [data, setData] = useState<readonly number[][]>(() => SERIES.map((def) => seedSeries(def, RANGES[0].jitter, anchorFor(def, facilityId), mulberry32(facilityId * 1000 + RANGES[0].seedSalt))))
  const [updatedAt, setUpdatedAt] = useState(() => new Date())

  // 설비/기간 전환 시 해당 조합의 결정적 시드로 다시 생성하고, 실시간에서만 5초 틱을 돌린다.
  useEffect(() => {
    const rand = mulberry32(facilityId * 1000 + range.seedSalt)
    randRef.current = rand
    setData(SERIES.map((def) => seedSeries(def, range.jitter, anchorFor(def, facilityId), rand)))
    setUpdatedAt(new Date())
    if (!range.live) return
    const timer = window.setInterval(() => {
      setData((prev) => prev.map((values, index) => [...values.slice(1), nextValue(SERIES[index], values[values.length - 1], range.jitter, anchorFor(SERIES[index], facilityId), randRef.current)]))
      setUpdatedAt(new Date())
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [range, facilityId])

  const xAt = (index: number) => (index / (POINTS - 1)) * CHART_W
  const axisIndexes = [0, Math.floor(POINTS / 2), POINTS - 1]
  const axisLabels = axisIndexes.map((index) => {
    const at = new Date(updatedAt.getTime() - (POINTS - 1 - index) * range.stepMs)
    return index === POINTS - 1 ? `${formatAxis(at, range)} (현재)` : formatAxis(at, range)
  })
  const metaText = range.live
    ? `시뮬레이션 데이터 · 5초 간격 · 마지막 갱신 ${formatClock(updatedAt)}`
    : `시뮬레이션 데이터 · 최근 ${range.label}`
  const title = facility ? `실시간 센서 흐름 — ${facility.name} (기계실 ${facility.id})` : '실시간 센서 흐름'

  return (
    <SurfaceCard
      action={
        <div className="sf-head">
          <div aria-label="조회 기간" className="sf-range" role="tablist">
            {RANGES.map((item) => <button aria-selected={item.key === rangeKey} className={item.key === rangeKey ? 'active' : ''} key={item.key} onClick={() => setRangeKey(item.key)} role="tab" type="button">{item.label}</button>)}
          </div>
          <div className="sf-meta"><span className="demo-badge">DEMO</span><span>{metaText}</span></div>
        </div>
      }
      className="sensor-flow"
      title={title}
    >
      <div className="sensor-tiles">
        {SERIES.map((def, index) => <article className={`sensor-tile ${def.className}`} key={def.key}><Icon name={def.icon} /><div><p>{def.tile}</p><strong>{formatValue(def, data[index][POINTS - 1])} <em>{def.unit}</em></strong></div></article>)}
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
          <div className="sf-axis">{axisLabels.map((label) => <span key={label}>{label}</span>)}</div>
        </div>
        <div className="sf-values">
          {SERIES.map((def, index) => <span className={`sf-value ${def.className}`} key={def.key}>{formatValue(def, data[index][POINTS - 1])}</span>)}
        </div>
      </div>
    </SurfaceCard>
  )
}
