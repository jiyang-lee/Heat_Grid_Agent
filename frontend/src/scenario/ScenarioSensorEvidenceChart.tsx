import type { ScenarioAlert, SensorMetric, SensorPoint } from './types'

type MetricConfig = {
  readonly key: SensorMetric
  readonly label: string
  readonly unit: string
  readonly min: number
  readonly max: number
  readonly color: string
}

const metrics: Record<SensorMetric, MetricConfig> = {
  supply: { key: 'supply', label: '공급온도', unit: '°C', min: 75, max: 85, color: 'var(--ops-critical)' },
  returnTemperature: { key: 'returnTemperature', label: '환수온도', unit: '°C', min: 40, max: 50, color: 'var(--ops-sensor-return)' },
  flow: { key: 'flow', label: '유량', unit: 'm³/h', min: 100, max: 130, color: 'var(--ops-sensor-flow)' },
}

function valueAt(point: SensorPoint, metric: SensorMetric): number {
  return point[metric]
}

export function ScenarioSensorEvidenceChart({ alert, points }: { readonly alert: ScenarioAlert; readonly points: readonly SensorPoint[] }) {
  const metric = metrics[alert.affectedMetric]
  const values = points.map((point) => valueAt(point, metric.key))
  const floor = Math.min(metric.min - 6, ...values)
  const ceiling = Math.max(metric.max + 6, ...values)
  const span = ceiling - floor || 1
  const x = (index: number) => 24 + index * (252 / Math.max(1, points.length - 1))
  const y = (value: number) => 76 - ((value - floor) / span) * 58
  const path = points.map((point, index) => `${x(index)},${y(valueAt(point, metric.key))}`).join(' ')
  const rangeTop = y(metric.max)
  const rangeBottom = y(metric.min)
  const latest = values.at(-1)
  const isOutsideRange = latest != null && (latest < metric.min || latest > metric.max)
  const alertToneClass = alert.priority === 'urgent' ? 'is-critical' : 'is-warning'
  const alertColor = alert.priority === 'urgent' ? 'var(--ops-critical)' : 'var(--ops-warning)'
  const alertLabel = alert.priority === 'urgent' ? '긴급' : '경고'
  const breachY = latest != null && latest < metric.min ? rangeBottom : 4
  const breachHeight = latest != null && latest < metric.min ? Math.max(0, 92 - rangeBottom) : Math.max(0, rangeTop - 4)

  return <section className={`scenario-evidence-chart ${isOutsideRange ? alertToneClass : ''}`.trim()} aria-label={`${metric.label} 이상 시계열`}>
    <header><div>{isOutsideRange && <span className="scenario-evidence-state">{alertLabel} · 정상 범위 이탈</span>}<h3>{metric.label} 이상 감지</h3><span>정상 {metric.min}~{metric.max} {metric.unit}</span></div>{latest != null && <strong style={{ color: isOutsideRange ? alertColor : metric.color }}>{latest.toFixed(1)} {metric.unit}</strong>}</header>
    <svg preserveAspectRatio="none" role="img" viewBox="0 0 300 96"><rect fill="var(--ops-critical-soft)" height={Math.max(0, rangeBottom - rangeTop)} opacity=".55" rx="4" width="264" x="18" y={rangeTop} />{isOutsideRange && <rect className="scenario-evidence-breach-band" height={breachHeight} rx="3" width="264" x="18" y={breachY} />}<line className="scenario-evidence-axis" x1="18" x2="282" y1={rangeTop} y2={rangeTop} /><line className="scenario-evidence-axis" x1="18" x2="282" y1={rangeBottom} y2={rangeBottom} />{isOutsideRange && <line className="scenario-evidence-critical-threshold" x1="18" x2="282" y1={rangeBottom} y2={rangeBottom} />}<polyline className={`scenario-evidence-line ${isOutsideRange ? 'is-alert' : ''}`.trim()} fill="none" points={path} stroke={isOutsideRange ? alertColor : metric.color} />{points.map((point, index) => { const pointX = x(index); const pointY = y(valueAt(point, metric.key)); const isLatest = index === points.length - 1; const color = isLatest && isOutsideRange ? alertColor : metric.color; return <g key={point.at}>{isLatest && <line className="scenario-evidence-point-halo" vectorEffect="non-scaling-stroke" x1={pointX} x2={pointX} y1={pointY} y2={pointY} />}<line className={`scenario-evidence-point ${isLatest ? 'latest' : ''}`.trim()} stroke={color} vectorEffect="non-scaling-stroke" x1={pointX} x2={pointX} y1={pointY} y2={pointY} /></g> })}</svg>
  </section>
}
