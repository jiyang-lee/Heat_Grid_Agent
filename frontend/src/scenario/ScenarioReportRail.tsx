import { StatusBadge } from '../console/ui'
import type { ScenarioDocumentGroup } from './types'

interface Props {
  readonly activeGroupId: string | null
  readonly groups: readonly ScenarioDocumentGroup[]
  readonly onSelect: (groupId: string) => void
}

export function ScenarioReportRail({ activeGroupId, groups, onSelect }: Props) {
  const reportGroups = groups
    .filter((group) => group.report.status !== 'idle' || group.acceptedWorkOrderVersion != null)
    .sort((left, right) => (right.report.createdAt ?? right.createdAt).localeCompare(left.report.createdAt ?? left.createdAt))

  if (reportGroups.length === 0) return <p className="scenario-list-empty">보고서 생성이 가능한 작업지시서가 없습니다.</p>

  return <nav aria-label="보고서 목록" className="scenario-version-list scenario-report-list">
    {reportGroups.map((group) => {
      const root = group.workOrders[0]
      const acceptedVersion = group.acceptedWorkOrderVersion ?? group.workOrders.at(-1)?.version ?? 1
      const createdAt = new Date(group.report.createdAt ?? group.createdAt)
      const createdLabel = Number.isNaN(createdAt.getTime()) ? '' : createdAt.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      const reportReady = group.report.status !== 'idle'
      return <section className="scenario-version-entry" key={group.id}>
        <button aria-label={`${root?.title ?? `기계실 ${group.substationId} 작업지시서`} ${reportReady ? '보고서 상세' : '보고서 생성 준비'} 열기`} aria-pressed={group.id === activeGroupId} className={group.id === activeGroupId ? 'active' : ''} onClick={() => onSelect(group.id)} type="button"><span>R</span><div><strong>{root?.title.replace(/\s+v1$/, '') ?? `기계실 ${group.substationId} 조치 결과`}</strong><small>기계실 {group.substationId} · 작업지시서 v{acceptedVersion}{createdLabel ? ` · ${createdLabel}` : ''}</small></div><StatusBadge tone={group.report.status === 'completed' ? 'success' : group.report.status === 'draft' ? 'notice' : 'neutral'}>{group.report.status === 'completed' ? '완료' : group.report.status === 'draft' ? '초안' : '미생성'}</StatusBadge></button>
      </section>
    })}
  </nav>
}
