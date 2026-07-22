import { StatusBadge } from '../console/ui'
import type { ScenarioDocumentGroup } from './types'

interface Props {
  readonly activeGroupId: string | null
  readonly groups: readonly ScenarioDocumentGroup[]
  readonly onSelect: (groupId: string) => void
}

export function ScenarioVersionRail({ activeGroupId, groups, onSelect }: Props) {
  const sortedGroups = [...groups].sort((left, right) => right.createdAt.localeCompare(left.createdAt))
  if (sortedGroups.length === 0) return <p className="scenario-list-empty">생성된 작업지시서가 없습니다.</p>
  return <nav aria-label="작업지시서 목록" className="scenario-version-list">
    {sortedGroups.map((group) => {
      const order = group.workOrders[0]
      const latestVersion = group.workOrders.at(-1)?.version ?? 1
      const status = group.report.status === 'completed'
        ? '보고서 완료'
        : group.report.status === 'draft'
          ? '보고서 작성 중'
          : group.acceptedWorkOrderVersion == null
            ? `v${latestVersion} 검토 중`
            : `v${group.acceptedWorkOrderVersion} 채택`
      const createdAt = new Date(group.createdAt)
      const createdLabel = Number.isNaN(createdAt.getTime()) ? '' : createdAt.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      return order == null ? null : <section className="scenario-version-entry" key={group.id}>
        <button aria-label={`${order.title} 상세 열기 · 기계실 ${group.substationId} · ${status}`} aria-pressed={group.id === activeGroupId} className={group.id === activeGroupId ? 'active' : ''} onClick={() => onSelect(group.id)} type="button"><span>v1</span><div><strong>{order.title}</strong><small>기계실 {group.substationId} · {order.changeSummary}{createdLabel ? ` · ${createdLabel}` : ''}</small></div><StatusBadge tone={group.report.status === 'completed' || group.acceptedWorkOrderVersion != null ? 'success' : 'primary'}>{status}</StatusBadge></button>
      </section>
    })}
  </nav>
}
