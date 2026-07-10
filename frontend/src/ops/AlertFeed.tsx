/** 알림 피드 — GET /api/alerts + 상태/우선순위 필터 + ack/resolve. */

import type { AlertStatus, PriorityLevel } from '../api/contracts'
import { useAckAlert, useAlerts, useResolveAlert } from '../api/hooks'
import { complexById } from '../domain/model'

const STATUS_KO: Record<AlertStatus | 'all', string> = {
  open: '열림',
  acked: '접수',
  resolved: '해결',
  all: '전체',
}

interface Props {
  status: AlertStatus | 'all'
  priority: PriorityLevel | 'all'
  onStatus: (s: AlertStatus | 'all') => void
  onPriority: (p: PriorityLevel | 'all') => void
  selectedId: string | null
  onSelect: (id: string) => void
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function locationLabel(substationId: number | null): string {
  if (substationId == null) return 'Substation -'
  return `${complexById.get(substationId)?.name ?? '미등록 단지'} · Substation ${substationId}`
}

export default function AlertFeed({ status, priority, onStatus, onPriority, selectedId, onSelect }: Props) {
  const alerts = useAlerts({ status, priority_level: priority === 'all' ? undefined : priority })
  const ack = useAckAlert()
  const resolve = useResolveAlert()

  return (
    <>
      <div className="ops-filters">
        <div className="seg">
          {(['open', 'acked', 'resolved', 'all'] as const).map((s) => (
            <button key={s} type="button" className={`seg-b ${status === s ? 'on' : ''}`} onClick={() => onStatus(s)}>
              {STATUS_KO[s]}
            </button>
          ))}
        </div>
        <div className="seg">
          {(['all', 'urgent', 'high'] as const).map((p) => (
            <button key={p} type="button" className={`seg-b ${priority === p ? 'on' : ''}`} onClick={() => onPriority(p)}>
              {p === 'all' ? '전체' : p === 'urgent' ? '긴급' : '높음'}
            </button>
          ))}
        </div>
      </div>

      <div className="aside-body">
        {alerts.isLoading && <div className="empty">알림 불러오는 중…</div>}
        {alerts.isError && <div className="wo-err">알림 불러오기 실패</div>}
        {alerts.data && alerts.data.length === 0 && <div className="empty">해당 조건의 알림이 없습니다</div>}
        {alerts.data?.map((a) => (
          <div
            key={a.alert_id}
            className={`row ${selectedId === a.alert_id ? 'active' : ''}`}
            onClick={() => onSelect(a.alert_id)}
          >
            <div className={`chip-st ${a.priority_level === 'urgent' ? 'st-urgent' : 'st-caution'}`}>
              {a.priority_level === 'urgent' ? '긴급' : '높음'}
            </div>
            <div className="info">
              <div className="nm">{locationLabel(a.substation_id)} · 전체 {a.priority_rank ?? '-'}위</div>
              <div className="ad">
                score {a.priority_score?.toFixed(1) ?? '-'} · 기준 {a.as_of_time ? fmtTime(a.as_of_time) : '-'} · {STATUS_KO[a.status]}
                {a.acked_by ? ` · ${a.acked_by}` : ''}
              </div>
            </div>
            <div className="ops-actions" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className="mini"
                disabled={a.status !== 'open' || ack.isPending}
                onClick={() => ack.mutate({ alertId: a.alert_id })}
              >
                접수
              </button>
              <button
                type="button"
                className="mini"
                disabled={a.status === 'resolved' || resolve.isPending}
                onClick={() => resolve.mutate({ alertId: a.alert_id })}
              >
                해결
              </button>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
