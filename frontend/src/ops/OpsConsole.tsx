/** 운영 콘솔 — 알림 큐(피드) + 알림 상세/에이전트. 전부 /api 계약 소비(mock/real 스위치). */

import { useState } from 'react'
import type { AlertStatus, PriorityLevel } from '../api/contracts'
import { useAlerts } from '../api/hooks'
import AlertFeed from './AlertFeed'
import AlertDetail from './AlertDetail'

export default function OpsConsole() {
  const [status, setStatus] = useState<AlertStatus | 'all'>('open')
  const [priority, setPriority] = useState<PriorityLevel | 'all'>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const alerts = useAlerts({ status, priority_level: priority === 'all' ? undefined : priority })
  const selected = alerts.data?.find((a) => a.alert_id === selectedId) ?? null

  return (
    <div className="wrap">
      <section className="panel">
        <div className="panel-head">
          <span>알림 큐 · ALERT QUEUE</span>
          <span className="tag">{alerts.data?.length ?? 0} ALERTS</span>
        </div>
        <AlertFeed
          status={status}
          priority={priority}
          onStatus={setStatus}
          onPriority={setPriority}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </section>

      <aside className="panel">
        <div className="panel-head">
          <span>알림 상세 · 에이전트</span>
          <span className="tag">AGENT</span>
        </div>
        <AlertDetail alert={selected} />
      </aside>
    </div>
  )
}
