import { useScenario } from '../scenario/useScenario'
import type { SensorPoint } from '../scenario/types'
import { Icon, type IconName } from './icons'
import { SurfaceCard } from './ui'

type SensorKey = 'supply' | 'returnTemperature' | 'flow'

interface MetricDef {
  readonly key: SensorKey
  readonly label: string
  readonly unit: string
  readonly icon: IconName
  readonly min: number
  readonly max: number
  readonly className: string
}

const METRICS: readonly MetricDef[] = [
  { key: 'supply', label: '공급온도', unit: '°C', icon: 'thermometer', min: 75, max: 85, className: 'sf-supply' },
  { key: 'returnTemperature', label: '환수온도', unit: '°C', icon: 'thermometer', min: 40, max: 50, className: 'sf-return' },
  { key: 'flow', label: '유량', unit: 'm³/h', icon: 'flow', min: 100, max: 130, className: 'sf-flow' },
]

const CHART_W = 720
const CHART_H = 300
const PLOT = { top: 28, right: 24, bottom: 42, left: 48 } as const

const pad2 = (value: number) => String(value).padStart(2, '0')

function historyDate(value: string): Date {
  return new Date(value)
}

function formatAxis(value: string): string {
  const date = historyDate(value)
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

function formatReceivedAt(value: string): string {
  const date = historyDate(value)
  return `${date.getFullYear()}.${pad2(date.getMonth() + 1)}.${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
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

function SensorChart({ title, unit, domain, lines, bands, data }: ChartProps) {
  const plotW = CHART_W - PLOT.left - PLOT.right
  const plotH = CHART_H - PLOT.top - PLOT.bottom
  const xAt = (index: number) => PLOT.left + (index / Math.max(1, data.length - 1)) * plotW
  const yAt = (value: number) => PLOT.top + plotH - ((value - domain[0]) / (domain[1] - domain[0])) * plotH
  const gridValues = Array.from({ length: 5 }, (_, index) => domain[0] + ((domain[1] - domain[0]) * index) / 4)
  const labelIndexes = [...new Set([0, 3, 6, 9, data.length - 1])].filter((index) => index >= 0 && index < data.length)
  const lastIndex = data.length - 1

  return (
    <article className="sf-chart-card">
      <header className="sf-chart-header">
        <div><h3>{title}</h3><div className="sf-chart-legend">{lines.map((line) => <span key={line.key}><i style={{ background: line.color }} />{line.label}</span>)}</div></div>
        <span>단위: {unit}</span>
      </header>
      <svg aria-label={`${title} 센서 시계열 차트`} className="sf-history-chart" role="img" viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
        {bands.map((band) => <rect fill={band.color} height={Math.abs(yAt(band.min) - yAt(band.max))} key={`${band.min}-${band.max}`} opacity="0.5" width={plotW} x={PLOT.left} y={yAt(band.max)} />)}
        {gridValues.map((value) => <g key={value}><line className="sf-grid-line" x1={PLOT.left} x2={CHART_W - PLOT.right} y1={yAt(value)} y2={yAt(value)} /><text className="sf-y-label" x={PLOT.left - 10} y={yAt(value) + 4}>{Math.round(value)}</text></g>)}
        <line className="sf-current-line" x1={xAt(lastIndex)} x2={xAt(lastIndex)} y1={PLOT.top} y2={PLOT.top + plotH} />
        {lines.map((line) => {
          const points = data.map((point, index) => `${xAt(index)},${yAt(point[line.key])}`).join(' ')
          const last = data[lastIndex]?.[line.key] ?? 0
          return <g key={line.key}><polyline fill="none" points={points} stroke={line.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />{data.map((point, index) => <circle className={index === lastIndex ? 'sf-new-point' : ''} cx={xAt(index)} cy={yAt(point[line.key])} fill={line.color} key={`${line.key}-${point.at}`} r={index === lastIndex ? 5 : 3.5} stroke="#fff" strokeWidth="1.5" />)}<text className="sf-current-value" fill={line.color} textAnchor="end" x={xAt(lastIndex) - 9} y={yAt(last) - 9}>{last.toFixed(1)}</text></g>
        })}
        {labelIndexes.map((index) => { const point = data[index]; return point ? <text className="sf-x-label" key={point.at} textAnchor={index === 0 ? 'start' : index === lastIndex ? 'end' : 'middle'} x={xAt(index)} y={CHART_H - 14}>{formatAxis(point.at)}</text> : null })}
      </svg>
    </article>
  )
}

export default function SensorFlowCard() {
  const { sensor, alerts, state: scenarioState } = useScenario()
  const data = sensor.state.points
  const latest = data.at(-1)
  if (!latest) return null
  const selectedAlert = alerts.find((alert) => alert.id === scenarioState.selectedAlertId)

  return (
    <SurfaceCard
      action={
        <div className="sf-head">
          <span className="sf-sub">기계실 {sensor.state.substationId}</span>
          <span className="sf-divider" />
          <span className="sf-sub">최근 2시간 · 10분 간격</span>
          <div className="sf-right">
            <span className="sf-received">최근 데이터 {formatReceivedAt(latest.at)}</span>
            <button className="sf-pause-button" onClick={sensor.togglePaused} type="button"><Icon name={sensor.state.paused ? 'arrow' : 'more'} />{sensor.state.paused ? '재개' : '일시정지'}</button>
          </div>
        </div>
      }
      className="sensor-flow"
      title="실시간 센서 흐름"
    >
      <div className="sensor-tiles">
        {METRICS.map((metric) => {
          const value = latest[metric.key]
          const normal = value >= metric.min && value <= metric.max
          const incidentFocus = scenarioState.incidentState === 'incident-active' && selectedAlert?.affectedMetric === metric.key
          return <article className={`sensor-tile ${metric.className} ${incidentFocus ? 'is-incident-focus' : ''}`.trim()} key={metric.key}><div className="sensor-tile-main"><span className="tile-icon"><Icon name={metric.icon} /></span><div><p>{metric.label}</p><strong>{value.toFixed(1)} <em>{metric.unit}</em></strong></div><span className={`sf-status ${normal ? 'normal' : 'warning'}`}><i />{incidentFocus ? '이상 감지' : normal ? '정상' : '범위 이탈'}</span></div></article>
        })}
      </div>
      <div className="sf-charts">
        <SensorChart bands={[{ min: 75, max: 85, color: 'var(--ops-critical-soft)' }, { min: 40, max: 50, color: 'var(--ops-primary-soft)' }]} data={data} domain={[30, 90]} lines={[{ key: 'supply', label: '공급온도', color: 'var(--ops-critical)' }, { key: 'returnTemperature', label: '환수온도', color: 'var(--ops-sensor-return)' }]} title="공급·환수 온도" unit="°C" />
        <SensorChart bands={[{ min: 100, max: 130, color: 'var(--ops-primary-soft)' }]} data={data} domain={[80, 160]} lines={[{ key: 'flow', label: '유량', color: 'var(--ops-sensor-flow)' }]} title="유량" unit="m³/h" />
      </div>
    </SurfaceCard>
  )
}
