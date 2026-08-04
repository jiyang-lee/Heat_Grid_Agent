import { useEffect, useMemo, useRef, useState } from 'react'
import type { AgentRunStatus } from '../api/contracts'
import { agentRunsApi } from '../api/client'
import { Button, StatusBadge } from './ui'

export interface AgentAnalysisQueueEntry {
  readonly runId: string
  readonly alertId: string
  readonly label: string
  readonly requestedAt: string
}

interface RunProgress {
  readonly status: AgentRunStatus
  readonly error: string | null
  readonly elapsedMs: number
}

const TERMINAL_STATUSES: readonly AgentRunStatus[] = ['completed', 'failed', 'cancelled']

function formatElapsed(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.round(elapsedMs / 1000))
  if (totalSeconds < 60) return `${totalSeconds}초`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}분 ${seconds}초`
}

interface Props {
  readonly entries: readonly AgentAnalysisQueueEntry[]
  readonly onRemoveEntries: (runIds: readonly string[]) => void
  readonly onOpen: (runId: string) => void
}

function statusLabel(status: AgentRunStatus): string {
  if (status === 'queued') return '대기 중'
  if (status === 'running') return '분석 중'
  if (status === 'completed') return '완료'
  if (status === 'cancelled') return '취소됨'
  return '실패'
}

function statusTone(status: AgentRunStatus): 'critical' | 'neutral' | 'success' | 'warning' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'critical'
  if (status === 'running') return 'warning'
  return 'neutral'
}

function useQueueProgress(entries: readonly AgentAnalysisQueueEntry[]): Readonly<Record<string, RunProgress>> {
  const [progress, setProgress] = useState<Readonly<Record<string, RunProgress>>>({})
  const runIds = useMemo(() => entries.map((entry) => entry.runId), [entries])
  const runKey = runIds.join('|')
  const entriesRef = useRef(entries)
  entriesRef.current = entries

  useEffect(() => {
    if (runIds.length === 0) {
      setProgress({})
      return undefined
    }

    let disposed = false
    let refreshing = false
    const refresh = async () => {
      if (refreshing) return
      refreshing = true
      const snapshots = await Promise.all(runIds.map(async (runId) => {
        try {
          const run = await agentRunsApi.get(runId)
          return [runId, { status: run.status, error: run.error }] as const
        } catch {
          return [runId, { status: 'failed' as const, error: '작업 상태를 불러오지 못했습니다.' }] as const
        }
      }))
      if (!disposed) setProgress((current) => Object.fromEntries(snapshots.map(([runId, snap]) => {
        const previous = current[runId]
        const requestedAt = entriesRef.current.find((entry) => entry.runId === runId)?.requestedAt
        const frozen = previous && TERMINAL_STATUSES.includes(previous.status)
        const elapsedMs = frozen ? previous.elapsedMs : requestedAt ? Date.now() - Date.parse(requestedAt) : 0
        return [runId, { status: snap.status, error: snap.error, elapsedMs }]
      })))
      refreshing = false
    }

    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 1_000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [runKey, runIds])

  return progress
}

/**
 * 화면을 가리지 않는 접이식 AI 작업 현황함.
 * 작업 상태는 서버의 agent run을 주기적으로 조회하므로 페이지 이동 후에도 유지된다.
 */
export function AgentAnalysisProgress({ entries, onRemoveEntries, onOpen }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [cancellingRunIds, setCancellingRunIds] = useState<readonly string[]>([])
  const [cancelErrors, setCancelErrors] = useState<Readonly<Record<string, string>>>({})
  const progress = useQueueProgress(entries)
  const items = entries.map((entry) => ({
    ...entry,
    progress: progress[entry.runId] ?? { status: 'queued' as const, error: null, elapsedMs: Date.now() - Date.parse(entry.requestedAt) },
  }))
  const active = items.filter((item) => item.progress.status === 'queued' || item.progress.status === 'running')
  const completed = items.filter((item) => item.progress.status === 'completed')
  const failed = items.filter((item) => item.progress.status === 'failed')
  const cancelled = items.filter((item) => item.progress.status === 'cancelled')
  const finished = [...completed, ...failed, ...cancelled]

  if (items.length === 0) return null

  const summary = active.length > 0
    ? `AI 조치 ${active.length}건 ${active.some((item) => item.progress.status === 'running') ? '진행 중' : '대기 중'}`
    : failed.length > 0
      ? `AI 조치 ${failed.length}건 확인 필요`
      : cancelled.length > 0
        ? `AI 조치 ${cancelled.length}건 취소됨`
        : `AI 조치 ${completed.length}건 완료`

  const cancelQueuedRun = async (runId: string) => {
    setCancelErrors((current) => {
      const { [runId]: _removed, ...rest } = current
      return rest
    })
    setCancellingRunIds((current) => [...current, runId])
    try {
      await agentRunsApi.cancel(runId)
    } catch {
      setCancelErrors((current) => ({ ...current, [runId]: '대기 작업을 취소하지 못했습니다. 다시 시도해 주세요.' }))
    } finally {
      setCancellingRunIds((current) => current.filter((id) => id !== runId))
    }
  }

  return <aside aria-live="polite" className={`scenario-analysis-progress ${expanded ? 'is-expanded' : ''}`.trim()}>
    <button aria-expanded={expanded} aria-label={summary} className="scenario-analysis-progress-trigger" onClick={() => setExpanded((value) => !value)} type="button">
      <span aria-hidden="true" className="scenario-analysis-progress-indicator" />
      <strong>{summary}</strong>
      <span>{expanded ? '접기' : '펼치기'}</span>
    </button>
    {expanded && <section aria-label="AI 작업 현황" className="scenario-analysis-progress-panel">
      <header>
        <div><strong>AI 작업 현황</strong><span>동시 2건까지 분석하고, 나머지는 순서대로 시작합니다.</span></div>
        {finished.length > 0 && <button className="scenario-analysis-clear" onClick={() => onRemoveEntries(finished.map((item) => item.runId))} type="button">완료 항목 지우기</button>}
      </header>
      <ul>
        {items.map((item) => <li key={item.runId}>
          <div><strong>{item.label}</strong><span>{cancelErrors[item.runId] ?? item.progress.error ?? `${statusLabel(item.progress.status)} · ${formatElapsed(item.progress.elapsedMs)}`}</span></div>
          <div className="scenario-analysis-progress-actions"><StatusBadge tone={statusTone(item.progress.status)}>{statusLabel(item.progress.status)}</StatusBadge>{item.progress.status === 'queued' && <button className="scenario-analysis-cancel" disabled={cancellingRunIds.includes(item.runId)} onClick={() => void cancelQueuedRun(item.runId)} type="button">{cancellingRunIds.includes(item.runId) ? '취소 중' : '대기 취소'}</button>}<Button icon="arrow" onClick={() => onOpen(item.runId)} tone="ghost">{item.progress.status === 'completed' ? '결과 보기' : '진행 보기'}</Button></div>
        </li>)}
      </ul>
    </section>}
  </aside>
}
