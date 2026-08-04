/** 운영 콘솔 — 알림 큐(피드) + 토큰·비용 지표 + 알림 상세/작업지시서. 전부 실 /api 계약 소비. */

import { useEffect, useRef, useState } from 'react'
import type { AgentRunArtifact, AgentRunResponse, AlertStatus, PriorityLevel } from '../api/contracts'
import { useAgentRun, useAgentRunResult, useAlerts, useCreateAgentRun, useGenerateDailyReport } from '../api/hooks'
import AlertFeed from './AlertFeed'
import AlertDetail from './AlertDetail'
import AgentStats from './AgentStats'

interface Props {
  initialAlertId?: string | null
}

export default function OpsConsole({ initialAlertId = null }: Props) {
  const [status, setStatus] = useState<AlertStatus | 'all'>('open')
  const [priority, setPriority] = useState<PriorityLevel | 'all'>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const alerts = useAlerts({ status, priority_level: priority === 'all' ? undefined : priority })
  const list = alerts.data
  const selected = list?.find((a) => a.alert_id === selectedId) ?? null

  useEffect(() => {
    if (!initialAlertId) return
    setStatus('all')
    setPriority('all')
    setSelectedId(initialAlertId)
  }, [initialAlertId])

  // 진입/필터 변경 시 선택 알림이 없으면 첫 알림을 자동 선택 → 상세·지표 박스를 항상 고정 표시.
  useEffect(() => {
    if (!list || list.length === 0) return
    if (!list.some((a) => a.alert_id === selectedId)) {
      setSelectedId(list[0].alert_id)
    }
  }, [list, selectedId])

  const create = useCreateAgentRun()
  const dailyReport = useGenerateDailyReport()
  const [run, setRun] = useState<AgentRunResponse | null>(null)
  const [dailyArtifact, setDailyArtifact] = useState<AgentRunArtifact | null>(null)
  const selectedAlertRef = useRef<string | null>(selected?.alert_id ?? null)
  const activeRunRef = useRef<string | null>(run?.run_id ?? null)
  selectedAlertRef.current = selected?.alert_id ?? null
  activeRunRef.current = run?.run_id ?? null
  const runStatus = useAgentRun(run?.run_id ?? null)
  const result = useAgentRunResult(run?.status === 'completed' ? run.run_id : null)

  useEffect(() => {
    if (!runStatus.data) return
    setRun((current) => current?.run_id === runStatus.data.run_id ? runStatus.data : current)
  }, [runStatus.data])

  useEffect(() => {
    setRun(null)
    setDailyArtifact(null)
  }, [selected?.alert_id])

  const runSelectedAlert = (forceNew = false) => {
    if (!selected) return
    const targetAlertId = selected.alert_id
    const reason = forceNew
      ? window.prompt('재실행 사유를 입력하세요')?.trim()
      : undefined
    if (forceNew && !reason) return
    create.mutate(
      {
        alertId: targetAlertId,
        forceNew,
        requestedBy: forceNew ? 'ops-console' : undefined,
        reason,
      },
      {
        onSuccess: (createdRun) => {
          if (selectedAlertRef.current === targetAlertId) setRun(createdRun)
        },
      },
    )
  }

  const generateDailyReport = () => {
    if (!run) return
    const targetRunId = run.run_id
    dailyReport.mutate(
      { runId: targetRunId },
      {
        onSuccess: (artifact) => {
          if (activeRunRef.current === targetRunId) setDailyArtifact(artifact)
        },
      },
    )
  }

  return (
    <div className="ops-console">
      <div className="wrap">
      <section className="panel">
        <div className="panel-head">
          <span>알림 큐 · ALERT QUEUE</span>
          <span className="tag">{selected?.evaluation_run_id ? `SNAPSHOT ${selected.evaluation_run_id.slice(0, 8)}` : `${list?.length ?? 0} ALERTS`}</span>
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
            <div className="command-row">
              <button
                type="button"
                className="mini primary"
                disabled={!selected || create.isPending || run?.status === 'queued' || run?.status === 'running'}
                onClick={() => runSelectedAlert(run?.status === 'completed')}
              >
                {create.isPending
                  ? '생성 중'
                  : run?.status === 'failed'
                    ? '작업지시서 다시 생성'
                    : run?.status === 'queued' || run?.status === 'running'
                      ? '작업지시서 실행 중'
                      : run?.status === 'completed'
                      ? '작업지시서 다시 실행'
                      : '작업지시서 생성'}
              </button>
              <button
                type="button"
                className="mini"
                disabled={!run || run.status !== 'completed' || dailyReport.isPending || dailyArtifact != null}
                onClick={generateDailyReport}
              >
                {dailyReport.isPending ? '보고서 생성 중' : dailyArtifact ? '보고서 생성됨' : '일일 보고서 생성'}
              </button>
            </div>
          </div>
          <AlertDetail
            alert={selected}
            run={run}
            opsResult={result.data ?? null}
            resultLoading={result.isLoading}
            resultError={result.isError}
            running={create.isPending}
            commandError={create.isError || runStatus.isError}
            dailyReport={dailyArtifact}
            dailyReportError={dailyReport.isError}
          />
        </aside>
      </div>
      </div>
    </div>
  )
}
