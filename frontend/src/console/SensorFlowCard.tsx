import { useEffect, useState } from 'react'
import { useScenario } from '../scenario/useScenario'
import type { SensorPoint } from '../scenario/types'
import { Icon } from './icons'
import { operationsClock } from './operationsTime'
import { SurfaceCard } from './ui'

type SensorKey = 'supply' | 'returnTemperature' | 'flow'

const CHART_W = 720
const CHART_H = 300
const PLOT = { top: 28, right: 18, bottom: 42, left: 48 } as const
const LIVE_PROGRESS = 0.75
const LIVE_AXIS_POSITIONS = [0, 0.25, 0.5, 0.625, LIVE_PROGRESS, 1] as const

function useCurrentAxisEnd(enabled: boolean): string {
  const [axisEnd, setAxisEnd] = useState(() => new Date().toISOString())
  useEffect(() => {
    if (!enabled) return undefined
    const timer = window.setInterval(() => setAxisEnd(new Date().toISOString()), 30_000)
    return () => window.clearInterval(timer)
  }, [enabled])
  return axisEnd
}

function historyDate(value: string): Date {
  return new Date(value)
}

function formatAxis(value: string): string {
  const date = historyDate(value)
  return formatDateAxis(date)
}

function formatDateAxis(date: Date): string {
  return operationsClock(date).time
}

function roundedAxisCurrent(value: Date): Date {
  const current = new Date(value)
  current.setMinutes(Math.floor(current.getMinutes() / 10) * 10, 0, 0)
  return current
}

function axisLayout(currentAt: Date): { readonly dates: readonly Date[]; readonly positions: readonly number[] } {
  const current = roundedAxisCurrent(currentAt)
  const twoHoursBeforeCurrent = new Date(current)
  twoHoursBeforeCurrent.setHours(twoHoursBeforeCurrent.getHours() - 2)
  const ninetyMinutesBeforeCurrent = new Date(current)
  ninetyMinutesBeforeCurrent.setMinutes(ninetyMinutesBeforeCurrent.getMinutes() - 90)
  const sixtyMinutesBeforeCurrent = new Date(current)
  sixtyMinutesBeforeCurrent.setHours(sixtyMinutesBeforeCurrent.getHours() - 1)
  const tenMinutesBeforeCurrent = new Date(current)
  tenMinutesBeforeCurrent.setMinutes(tenMinutesBeforeCurrent.getMinutes() - 10)
  const sixtyMinutesAfterCurrent = new Date(current)
  sixtyMinutesAfterCurrent.setHours(sixtyMinutesAfterCurrent.getHours() + 1)
  return {
    dates: [twoHoursBeforeCurrent, ninetyMinutesBeforeCurrent, sixtyMinutesBeforeCurrent, tenMinutesBeforeCurrent, current, sixtyMinutesAfterCurrent],
    positions: LIVE_AXIS_POSITIONS,
  }
}

interface LineSpec {
  readonly key: SensorKey
  readonly label: string
  readonly color: string
}

interface BandSpec {
  readonly min: number
  readonly max: number
  readonly color: string
}

interface ChartProps {
  readonly title: string
  readonly unit: string
  readonly domain: readonly [number, number]
  readonly lines: readonly LineSpec[]
  readonly bands: readonly BandSpec[]
  readonly data: readonly SensorPoint[]
  readonly axisEnd: string
  readonly hasData: boolean
}

interface HoveredPoint {
  readonly index: number
  readonly line: LineSpec
  readonly point: SensorPoint
}

function SensorChart({ title, unit, domain, lines, bands, data, axisEnd, hasData }: ChartProps) {
  const [hovered, setHovered] = useState<HoveredPoint | null>(null)
  const plotW = CHART_W - PLOT.left - PLOT.right
  const plotH = CHART_H - PLOT.top - PLOT.bottom
  const xAt = (index: number) => PLOT.left + (index / Math.max(1, data.length - 1)) * plotW * (hasData ? LIVE_PROGRESS : 1)
  const yAt = (value: number) => PLOT.top + plotH - ((value - domain[0]) / (domain[1] - domain[0])) * plotH
  const gridValues = Array.from({ length: 5 }, (_, index) => domain[0] + ((domain[1] - domain[0]) * index) / 4)
  const lastIndex = data.length - 1
  const currentAt = data[lastIndex] ? historyDate(data[lastIndex].at) : null
  const axis = axisLayout(currentAt ?? historyDate(axisEnd))
  const hoverValue = hovered?.point[hovered.line.key]
  const tooltipX = hovered ? Math.min(Math.max(xAt(hovered.index), 110), CHART_W - 110) : 0
  const tooltipY = hovered && hoverValue != null ? Math.max(PLOT.top + 28, yAt(hoverValue) - 30) : 0

  return (
    <article className="sf-chart-card">
      <header className="sf-chart-header">
        <h3>{title} <span className="sf-chart-unit">단위: {unit}</span></h3>
        {hasData && <div className="sf-chart-legend">{lines.map((line) => <span key={line.key}><i style={{ background: line.color }} />{line.label}</span>)}</div>}
      </header>
      <svg aria-label={`${title} 센서 시계열 차트${hasData ? '' : ' (수신 데이터 없음)'}`} className="sf-history-chart" role="img" viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
        {hasData && bands.map((band) => <rect fill={band.color} height={Math.abs(yAt(band.min) - yAt(band.max))} key={`${band.min}-${band.max}`} opacity="0.5" width={plotW} x={PLOT.left} y={yAt(band.max)} />)}
        {gridValues.map((value) => <g key={value}><line className="sf-grid-line" x1={PLOT.left} x2={CHART_W - PLOT.right} y1={yAt(value)} y2={yAt(value)} /><text className="sf-y-label" x={PLOT.left - 10} y={yAt(value) + 4}>{Math.round(value)}</text></g>)}
        {hasData && <line className="sf-current-line" x1={xAt(lastIndex)} x2={xAt(lastIndex)} y1={PLOT.top} y2={PLOT.top + plotH} />}
        {hasData && lines.map((line) => {
          const points = data.map((point, index) => `${xAt(index)},${yAt(point[line.key])}`).join(' ')
          const last = data[lastIndex]?.[line.key] ?? 0
          return <g key={line.key}><polyline fill="none" points={points} stroke={line.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />{data.map((point, index) => <circle aria-label={`${line.label} ${formatAxis(point.at)} ${point[line.key].toFixed(1)} ${unit}`} className={`sf-chart-point ${index === lastIndex ? 'sf-new-point' : ''}`.trim()} cx={xAt(index)} cy={yAt(point[line.key])} fill={line.color} key={`${line.key}-${point.at}`} onBlur={() => setHovered(null)} onFocus={() => setHovered({ index, line, point })} onMouseEnter={() => setHovered({ index, line, point })} onMouseLeave={() => setHovered(null)} r={index === lastIndex ? 5 : 3.5} stroke="#fff" strokeWidth="1.5" tabIndex={0} />)}<text className="sf-current-value" fill={line.color} textAnchor="end" x={xAt(lastIndex) - 9} y={yAt(last) - 9}>{last.toFixed(1)}</text></g>
        })}
        {axis.dates.map((date, index) => {
          const isFuture = index === axis.dates.length - 1
          const position = axis.positions[index] ?? 0
          return <text className={`sf-x-label ${isFuture ? 'sf-future-label' : ''}`.trim()} key={date.getTime()} textAnchor={index === 0 ? 'start' : isFuture ? 'end' : 'middle'} x={PLOT.left + plotW * position} y={CHART_H - 14}>{formatDateAxis(date)}</text>
        })}
        {hovered && hoverValue != null && <g className="sf-chart-tooltip" pointerEvents="none" transform={`translate(${tooltipX - 96} ${tooltipY - 24})`}><rect height="48" rx="7" width="192" /><text x="12" y="20">{formatAxis(hovered.point.at)} · {hovered.line.label}</text><text className="sf-tooltip-value" x="12" y="38">{hoverValue.toFixed(1)} {unit}</text></g>}
      </svg>
    </article>
  )
}

interface Props {
  readonly substationId: number | null
}

export default function SensorFlowCard({ substationId }: Props) {
  const { sensor, state } = useScenario()
  const hasData = state.mode === 'fault'
  const normalAxisEnd = useCurrentAxisEnd(!hasData)
  if (substationId == null) {
    return (
      <SurfaceCard className="sensor-flow sensor-flow-empty" title="GRAPH">
        <div className="sf-empty-state">
          <span className="sf-empty-icon"><Icon name="map" /></span>
          <strong>기계실 미선택</strong>
          <p>지도 또는 주요 알림을 선택하세요.</p>
        </div>
      </SurfaceCard>
    )
  }

  const data = hasData ? sensor.state.points : []
  const axisEnd = hasData ? sensor.state.simulatedAt : normalAxisEnd

  return (
    <SurfaceCard
      action={
        <div className="sf-right">
          <span className="sf-title-meta">기계실 {substationId} · 최근 2시간 · 10분 간격</span>
          <button className="sf-pause-button" onClick={sensor.togglePaused} type="button"><Icon name={sensor.state.paused ? 'arrow' : 'more'} />{sensor.state.paused ? '재개' : '일시정지'}</button>
        </div>
      }
      className="sensor-flow"
      title="GRAPH"
    >
      <div className="sf-charts">
        <SensorChart axisEnd={axisEnd} bands={[{ min: 75, max: 85, color: 'var(--ops-critical-soft)' }, { min: 40, max: 50, color: 'var(--ops-primary-soft)' }]} data={data} domain={[30, 90]} hasData={hasData} lines={[{ key: 'supply', label: '공급온도', color: 'var(--ops-critical)' }, { key: 'returnTemperature', label: '환수온도', color: 'var(--ops-sensor-return)' }]} title="공급·환수 온도" unit="°C" />
        <SensorChart axisEnd={axisEnd} bands={[{ min: 100, max: 130, color: 'var(--ops-primary-soft)' }]} data={data} domain={[80, 160]} hasData={hasData} lines={[{ key: 'flow', label: '유량', color: 'var(--ops-sensor-flow)' }]} title="유량" unit="m³/h" />
      </div>
    </SurfaceCard>
  )
}
