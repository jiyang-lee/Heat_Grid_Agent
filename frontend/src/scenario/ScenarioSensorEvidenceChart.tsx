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
  const isCritical = latest != null && (latest < metric.min || latest > metric.max)
  const breachY = latest != null && latest < metric.min ? rangeBottom : 4
  const breachHeight = latest != null && latest < metric.min ? Math.max(0, 92 - rangeBottom) : Math.max(0, rangeTop - 4)

  return <section className={`scenario-evidence-chart ${isCritical ? 'is-critical' : ''}`.trim()} aria-label={`${metric.label} 이상 시계열`}>
    <header><div>{isCritical && <span className="scenario-evidence-state">urgent · 정상 범위 이탈</span>}<h3>{metric.label} 이상 감지</h3><span>정상 {metric.min}~{metric.max} {metric.unit}</span></div>{latest != null && <strong className={isCritical ? 'critical-text' : ''} style={{ color: isCritical ? 'var(--ops-critical)' : metric.color }}>{latest.toFixed(1)} {metric.unit}</strong>}</header>
    <svg preserveAspectRatio="none" role="img" viewBox="0 0 300 96"><rect fill="var(--ops-critical-soft)" height={Math.max(0, rangeBottom - rangeTop)} opacity=".55" rx="4" width="264" x="18" y={rangeTop} />{isCritical && <rect className="scenario-evidence-breach-band" height={breachHeight} rx="3" width="264" x="18" y={breachY} />}<line className="scenario-evidence-axis" x1="18" x2="282" y1={rangeTop} y2={rangeTop} /><line className="scenario-evidence-axis" x1="18" x2="282" y1={rangeBottom} y2={rangeBottom} />{isCritical && <line className="scenario-evidence-critical-threshold" x1="18" x2="282" y1={rangeBottom} y2={rangeBottom} />}<polyline className={`scenario-evidence-line ${isCritical ? 'is-critical' : ''}`.trim()} fill="none" points={path} stroke={isCritical ? 'var(--ops-critical)' : metric.color} />{points.map((point, index) => <circle className={`${index === points.length - 1 ? 'latest' : ''} ${index === points.length - 1 && isCritical ? 'is-critical' : ''}`.trim()} cx={x(index)} cy={y(valueAt(point, metric.key))} fill={index === points.length - 1 && isCritical ? 'var(--ops-critical)' : metric.color} key={point.at} r={index === points.length - 1 ? (isCritical ? 6 : 4.5) : 2.5} />)}</svg>
  </section>
}
