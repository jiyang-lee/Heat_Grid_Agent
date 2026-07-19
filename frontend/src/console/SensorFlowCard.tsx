import { useState } from 'react'
import { useScenario } from '../scenario/useScenario'
import type { SensorPoint } from '../scenario/types'
import { Icon } from './icons'
import { SurfaceCard } from './ui'
import { operationsDateTime } from './operationsTime'

type SensorKey = 'supply' | 'returnTemperature' | 'flow'

const CHART_W = 720
const CHART_H = 300
const PLOT = { top: 28, right: 18, bottom: 42, left: 48 } as const
const LIVE_PROGRESS = 0.75
const AXIS_POSITIONS = [0, 0.25, 0.5, 0.625, LIVE_PROGRESS, 1] as const

const pad2 = (value: number) => String(value).padStart(2, '0')

function historyDate(value: string): Date {
  return new Date(value)
}

function formatAxis(value: string): string {
  const date = historyDate(value)
  return formatDateAxis(date)
}

function formatDateAxis(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
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
}

interface HoveredPoint {
  readonly index: number
  readonly line: LineSpec
  readonly point: SensorPoint
}

function SensorChart({ title, unit, domain, lines, bands, data }: ChartProps) {
  const [hovered, setHovered] = useState<HoveredPoint | null>(null)
  const plotW = CHART_W - PLOT.left - PLOT.right
  const plotH = CHART_H - PLOT.top - PLOT.bottom
  const xAt = (index: number) => PLOT.left + (index / Math.max(1, data.length - 1)) * plotW * LIVE_PROGRESS
  const yAt = (value: number) => PLOT.top + plotH - ((value - domain[0]) / (domain[1] - domain[0])) * plotH
  const gridValues = Array.from({ length: 5 }, (_, index) => domain[0] + ((domain[1] - domain[0]) * index) / 4)
  const lastIndex = data.length - 1
  const currentAt = data[lastIndex] ? historyDate(data[lastIndex].at) : null
  const axisLayout = currentAt ? (() => {
    const twoHoursBeforeCurrent = new Date(currentAt)
    twoHoursBeforeCurrent.setHours(twoHoursBeforeCurrent.getHours() - 2)
    const ninetyMinutesBeforeCurrent = new Date(currentAt)
    ninetyMinutesBeforeCurrent.setMinutes(ninetyMinutesBeforeCurrent.getMinutes() - 90)
    const sixtyMinutesBeforeCurrent = new Date(currentAt)
    sixtyMinutesBeforeCurrent.setHours(sixtyMinutesBeforeCurrent.getHours() - 1)
    const tenMinutesBeforeCurrent = new Date(currentAt)
    tenMinutesBeforeCurrent.setMinutes(tenMinutesBeforeCurrent.getMinutes() - 10)
    const thirtyMinutesAfterCurrent = new Date(currentAt)
    thirtyMinutesAfterCurrent.setMinutes(thirtyMinutesAfterCurrent.getMinutes() + 30)
    return {
      dates: [twoHoursBeforeCurrent, ninetyMinutesBeforeCurrent, sixtyMinutesBeforeCurrent, tenMinutesBeforeCurrent, currentAt, thirtyMinutesAfterCurrent],
      positions: AXIS_POSITIONS,
    }
  })() : { dates: [], positions: [] }
  const axisDates = axisLayout.dates
  const futureAt = axisDates.at(-1) ?? null
  const axisPositions = axisLayout.positions.length > 0 ? axisLayout.positions : AXIS_POSITIONS
  const hoverValue = hovered?.point[hovered.line.key]
  const tooltipX = hovered ? Math.min(Math.max(xAt(hovered.index), 110), CHART_W - 110) : 0
  const tooltipY = hovered && hoverValue != null ? Math.max(PLOT.top + 28, yAt(hoverValue) - 30) : 0

  return (
    <article className="sf-chart-card">
      <header className="sf-chart-header">
        <h3>{title} <span className="sf-chart-unit">단위: {unit}</span></h3>
        <div className="sf-chart-legend">{lines.map((line) => <span key={line.key}><i style={{ background: line.color }} />{line.label}</span>)}</div>
      </header>
      <svg aria-label={`${title} 센서 시계열 차트`} className="sf-history-chart" role="img" viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
        {bands.map((band) => <rect fill={band.color} height={Math.abs(yAt(band.min) - yAt(band.max))} key={`${band.min}-${band.max}`} opacity="0.5" width={plotW} x={PLOT.left} y={yAt(band.max)} />)}
        {gridValues.map((value) => <g key={value}><line className="sf-grid-line" x1={PLOT.left} x2={CHART_W - PLOT.right} y1={yAt(value)} y2={yAt(value)} /><text className="sf-y-label" x={PLOT.left - 10} y={yAt(value) + 4}>{Math.round(value)}</text></g>)}
        <line className="sf-current-line" x1={xAt(lastIndex)} x2={xAt(lastIndex)} y1={PLOT.top} y2={PLOT.top + plotH} />
        {lines.map((line) => {
          const points = data.map((point, index) => `${xAt(index)},${yAt(point[line.key])}`).join(' ')
          const last = data[lastIndex]?.[line.key] ?? 0
          return <g key={line.key}><polyline fill="none" points={points} stroke={line.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />{data.map((point, index) => <circle aria-label={`${line.label} ${formatAxis(point.at)} ${point[line.key].toFixed(1)} ${unit}`} className={`sf-chart-point ${index === lastIndex ? 'sf-new-point' : ''}`.trim()} cx={xAt(index)} cy={yAt(point[line.key])} fill={line.color} key={`${line.key}-${point.at}`} onBlur={() => setHovered(null)} onFocus={() => setHovered({ index, line, point })} onMouseEnter={() => setHovered({ index, line, point })} onMouseLeave={() => setHovered(null)} r={index === lastIndex ? 5 : 3.5} stroke="#fff" strokeWidth="1.5" tabIndex={0} />)}<text className="sf-current-value" fill={line.color} textAnchor="end" x={xAt(lastIndex) - 9} y={yAt(last) - 9}>{last.toFixed(1)}</text></g>
        })}
        {axisDates.map((date, index) => <text className={`sf-x-label ${date === futureAt ? 'sf-future-label' : ''}`.trim()} key={date.getTime()} textAnchor={index === 0 ? 'start' : date === futureAt ? 'end' : 'middle'} x={PLOT.left + plotW * axisPositions[index]} y={CHART_H - 14}>{formatDateAxis(date)}</text>)}
        {hovered && hoverValue != null && <g className="sf-chart-tooltip" pointerEvents="none" transform={`translate(${tooltipX - 96} ${tooltipY - 24})`}><rect height="48" rx="7" width="192" /><text x="12" y="20">{formatAxis(hovered.point.at)} · {hovered.line.label}</text><text className="sf-tooltip-value" x="12" y="38">{hoverValue.toFixed(1)} {unit}</text></g>}
      </svg>
    </article>
  )
}

interface Props {
  readonly substationId: number | null
}

export default function SensorFlowCard({ substationId }: Props) {
  const { sensor } = useScenario()
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

  const data = sensor.state.points
  const latest = data.at(-1)
  if (!latest) return null

  return (
    <SurfaceCard
      action={
        <div className="sf-right">
          <span className="sf-title-meta">기계실 {substationId} · 최근 2시간 · {sensor.state.source === 'backend-replay' ? '검증된 수신 데이터' : '연결 대체 데이터'}</span>
          <button className="sf-pause-button" onClick={sensor.togglePaused} type="button"><Icon name={sensor.state.paused ? 'arrow' : 'more'} />{sensor.state.paused ? '재개' : '일시정지'}</button>
        </div>
      }
      className="sensor-flow"
      title="GRAPH"
    >
      <div className="sf-data-status"><strong>{sensor.state.connectionMessage}</strong><span>마지막 수신 {operationsDateTime(sensor.state.receivedAt)}</span></div>
      <div className="sf-charts">
        <SensorChart bands={[{ min: 75, max: 85, color: 'var(--ops-critical-soft)' }, { min: 40, max: 50, color: 'var(--ops-primary-soft)' }]} data={data} domain={[30, 90]} lines={[{ key: 'supply', label: '공급온도', color: 'var(--ops-critical)' }, { key: 'returnTemperature', label: '환수온도', color: 'var(--ops-sensor-return)' }]} title="공급·환수 온도" unit="°C" />
        <SensorChart bands={[{ min: 100, max: 130, color: 'var(--ops-primary-soft)' }]} data={data} domain={[80, 160]} lines={[{ key: 'flow', label: '유량', color: 'var(--ops-sensor-flow)' }]} title="유량" unit="m³/h" />
      </div>
    </SurfaceCard>
  )
}
