/** 운영 콘솔 — 알림 큐(피드) + 토큰·비용 지표 + 알림 상세/작업지시서. 전부 /api 계약 소비(mock/real 스위치). */

import { useEffect, useState } from 'react'
import type { AgentRunResponse, AlertStatus, PriorityLevel } from '../api/contracts'
import { useAgentRunResult, useAlerts, useCreateAgentRun } from '../api/hooks'
import AlertFeed from './AlertFeed'
import AlertDetail from './AlertDetail'
import AgentStats from './AgentStats'

export default function OpsConsole() {
  const [status, setStatus] = useState<AlertStatus | 'all'>('open')
  const [priority, setPriority] = useState<PriorityLevel | 'all'>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const alerts = useAlerts({ status, priority_level: priority === 'all' ? undefined : priority })
  const list = alerts.data
  const selected = list?.find((a) => a.alert_id === selectedId) ?? null

  // 진입/필터 변경 시 선택 알림이 없으면 첫 알림을 자동 선택 → 상세·지표 박스를 항상 고정 표시.
  useEffect(() => {
    if (!list || list.length === 0) return
    if (!list.some((a) => a.alert_id === selectedId)) {
      setSelectedId(list[0].alert_id)
    }
  }, [list, selectedId])

  // 선택 알림에 대한 에이전트 자동 실행 — 지표 박스와 상세 박스가 결과를 공유한다.
  const create = useCreateAgentRun()
  const [run, setRun] = useState<AgentRunResponse | null>(null)
  const result = useAgentRunResult(run?.run_id ?? null)

  useEffect(() => {
    setRun(null)
    if (!selected) return
    let cancelled = false
    create
      .mutateAsync({ alertId: selected.alert_id })
      .then((r) => {
        if (!cancelled) setRun(r)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // create는 안정 참조(react-query)라 선택 알림 변경에만 반응한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.alert_id])

  return (
    <div className="wrap">
      <section className="panel">
        <div className="panel-head">
          <span>알림 큐 · ALERT QUEUE</span>
          <span className="tag">{list?.length ?? 0} ALERTS</span>
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

      <div className="ops-right">
        <section className="panel">
          <div className="panel-head">
            <span>토큰 · 비용 지표</span>
            <span className="tag">USAGE</span>
          </div>
          <AgentStats usage={run?.token_usage ?? null} />
        </section>

        <aside className="panel">
          <div className="panel-head">
            <span>알림 상세 · 에이전트</span>
            <span className="tag">AGENT</span>
          </div>
          <AlertDetail
            alert={selected}
            run={run}
            opsResult={result.data ?? null}
            resultLoading={result.isLoading}
            resultError={result.isError}
            running={create.isPending}
          />
        </aside>
      </div>
    </div>
  )
}
