/**
 * 실시간 센서 흐름 카드 — 클라이언트 시뮬레이션(DEMO).
 * 백엔드에 원시 센서 시계열 API가 없어(evidence의 sensor_summaries는 모델 피처 요약)
 * 권장범위 내 가상값을 5초 틱으로 생성한다. 실계약이 생기면 이 카드만 교체하면 된다.
 */

import { useEffect, useState } from 'react'
import { Icon, type IconName } from './icons'
import { SurfaceCard } from './ui'

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

const POINTS = 30
const TICK_MS = 5_000
const CHART_W = 720
const BAND_H = 44
const BAND_GAP = 14
const CHART_H = SERIES.length * (BAND_H + BAND_GAP) + BAND_GAP

/** 평균회귀 + 소폭 지터로 권장범위 안에서 자연스럽게 흔들리는 다음 값. */
function nextValue(def: SeriesDef, prev: number): number {
  const span = def.max - def.min
  const drift = (Math.random() - 0.5) * span * 0.12
  const pull = (def.base - prev) * 0.18
  return Math.min(def.max, Math.max(def.min, prev + drift + pull))
}

function seedSeries(def: SeriesDef): number[] {
  let value = def.base
  return Array.from({ length: POINTS }, () => (value = nextValue(def, value)))
}

function formatValue(def: SeriesDef, value: number): string {
  return value.toFixed(def.decimals)
}

function formatTime(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
}

export default function SensorFlowCard() {
  const [data, setData] = useState<readonly number[][]>(() => SERIES.map(seedSeries))
  const [updatedAt, setUpdatedAt] = useState(() => new Date())

  useEffect(() => {
    const timer = window.setInterval(() => {
      setData((prev) => prev.map((values, index) => [...values.slice(1), nextValue(SERIES[index], values[values.length - 1])]))
      setUpdatedAt(new Date())
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [])

  const xAt = (index: number) => (index / (POINTS - 1)) * CHART_W
  const axisIndexes = [0, Math.floor(POINTS / 2), POINTS - 1]
  const axisLabels = axisIndexes.map((index) => {
    const at = new Date(updatedAt.getTime() - (POINTS - 1 - index) * TICK_MS)
    return index === POINTS - 1 ? `${formatTime(at)} (현재)` : formatTime(at)
  })

  return (
    <SurfaceCard
      action={<div className="sf-meta"><span className="demo-badge">DEMO</span><span>시뮬레이션 데이터 · 5초 간격 · 마지막 갱신 {formatTime(updatedAt)}</span></div>}
      className="sensor-flow"
      title="실시간 센서 흐름"
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
