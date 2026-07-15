import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Icon, type IconName } from './icons'

export type Tone = 'critical' | 'warning' | 'notice' | 'success' | 'neutral' | 'primary'

interface SurfaceProps {
  readonly title?: string
  readonly action?: ReactNode
  readonly children: ReactNode
  readonly className?: string
}

export function SurfaceCard({ title, action, children, className = '' }: SurfaceProps) {
  return (
    <section className={`ops-surface ${className}`.trim()}>
      {title && <header className="surface-heading"><h2>{title}</h2>{action}</header>}
      {children}
    </section>
  )
}

interface MetricCardProps {
  readonly label: string
  readonly value: string
  readonly hint: string
  readonly icon: IconName
  readonly tone?: Tone
}

export function MetricCard({ label, value, hint, icon, tone = 'primary' }: MetricCardProps) {
  return <article className="metric-card"><div className={`metric-icon tone-${tone}`}><Icon name={icon} /></div><div><p>{label}</p><strong>{value}</strong><span>{hint}</span></div></article>
}

interface HomeMetricProps {
  readonly icon: IconName
  /** Tone 외 홈 전용 'violet' 톤도 허용한다(.tone-violet). */
  readonly tone: string
  readonly label: string
  readonly value: string
  readonly unit: string
  readonly children: ReactNode
}

/** 홈 요약 카드 — 헤더(아이콘+라벨), 우측 정렬 수치, 푸터 문구. 알림 페이지와 공용. */
export function HomeMetric({ icon, tone, label, value, unit, children }: HomeMetricProps) {
  return <article className="metric-card home-metric"><header><span className={`metric-icon tone-${tone}`}><Icon name={icon} /></span><p>{label}</p></header><strong>{value}<em>{unit}</em></strong><footer>{children}</footer></article>
}

export function StatusBadge({ tone, children }: { readonly tone: Tone; readonly children: ReactNode }) {
  return <span className={`status-badge tone-${tone}`}>{children}</span>
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly tone?: 'primary' | 'ghost' | 'danger'
  readonly icon?: IconName
}

export function Button({ tone = 'ghost', icon, children, className = '', ...props }: ButtonProps) {
  return <button className={`ops-button button-${tone} ${className}`.trim()} type="button" {...props}>{icon && <Icon name={icon} />}{children}</button>
}

export function EmptyState({ message, retry }: { readonly message: string; readonly retry?: () => void }) {
  return <div className="empty-state"><p>{message}</p>{retry && <Button onClick={retry} icon="activity">다시 시도</Button>}</div>
}

export function ApiState({ loading, error, empty, retry }: { readonly loading: boolean; readonly error: boolean; readonly empty: boolean; readonly retry: () => void }) {
  if (loading) return <div className="loading-state" aria-label="데이터를 불러오는 중"><i /><i /><i /></div>
  if (error) return <EmptyState message="실시간 운영 데이터를 불러오지 못했습니다." retry={retry} />
  if (empty) return <EmptyState message="표시할 운영 데이터가 없습니다." />
  return null
}

export function Sparkline({ values, tone = 'critical' }: { readonly values: readonly number[]; readonly tone?: Tone }) {
  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = max - min || 1
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${42 - ((value - min) / range) * 34}`).join(' ')
  return <svg className={`sparkline tone-${tone}`} viewBox="0 0 100 48" role="img" aria-label="최근 6시간 센서 추이"><path className="spark-grid" d="M0 12H100M0 28H100M0 44H100" /><polyline points={points} /></svg>
}
