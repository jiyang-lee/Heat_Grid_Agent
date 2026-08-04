import type { AgentRunListItem, OpsAgentResultV4 } from '../../api/contracts'
import { ApiError } from '../../api/client'
import { useAgentRun, useAgentRunResult, useAgentRunReviewSnapshot, useRunStages } from '../../api/hooks'
import { ApiState, Button, StatusBadge, SurfaceCard } from '../ui'
import { STAGE_LABELS, executionStatus, executionStatusTone, facilityName, priorityLabel } from './activityMappers'

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  if (totalSeconds < 60) return `${totalSeconds}초`
  return `${Math.floor(totalSeconds / 60)}분 ${totalSeconds % 60}초`
}

interface Props {
  readonly item: AgentRunListItem
  readonly onClose: () => void
  readonly onOpenWorkOrder: (runId: string, result: OpsAgentResultV4) => void
}

function displayText(value: string): string {
  return value.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, '해당 설비')
}

function conciseTitle(item: AgentRunListItem): string {
  const source = item.alert_reason?.trim() || '설비 이상 조치 계획서'
  const firstSummary = source.split(/\s*[·|]\s*/)[0]?.trim() || source
  return displayText(firstSummary.length > 90 ? `${firstSummary.slice(0, 89)}…` : firstSummary)
}

export function ExecutionDetail({ item, onClose, onOpenWorkOrder }: Props) {
  const run = useAgentRun(item.run_id)
  const result = useAgentRunResult(item.status === 'completed' ? item.run_id : null)
  const review = useAgentRunReviewSnapshot(item.run_id)
  const stages = useRunStages(item.run_id)
  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const snapshot = review.data?.snapshot ?? null
  const status = executionStatus(item)
  const actions = result.data?.actions ?? []
  const canOpenWorkOrder = item.status === 'completed' && result.data != null

  const runStartedAt = run.data?.created_at ? Date.parse(run.data.created_at) : null
  const sortedStages = [...(stages.data?.items ?? [])].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
  const stageDurations = sortedStages.map((stage, index) => {
    const previousAt = index === 0 ? runStartedAt : Date.parse(sortedStages[index - 1]!.created_at)
    const stageAt = Date.parse(stage.created_at)
    return { stage, durationMs: previousAt != null ? stageAt - previousAt : null }
  })
  const totalDurationMs = runStartedAt != null && sortedStages.length > 0
    ? Date.parse(sortedStages[sortedStages.length - 1]!.created_at) - runStartedAt
    : null

  return <SurfaceCard action={<div className="activity-detail-header-actions"><Button disabled={!canOpenWorkOrder} icon="document" onClick={() => { if (result.data != null) onOpenWorkOrder(item.run_id, result.data) }} tone="primary">작업지시서 생성</Button><Button aria-label="상세 닫기" icon="x" onClick={onClose} /></div>} className="activity-detail activity-plan-detail" title="계획서 상세">
    <div className="detail-body">
      <div className="detail-title">
        <StatusBadge tone={executionStatusTone(status)}>{status}</StatusBadge>
        <h2>{conciseTitle(item)}</h2>
        <p>{facilityName(item.substation_id, item.manufacturer_id)} · 기계실 {item.substation_id ?? '-'}</p>
        <span>{priorityLabel(item.priority)}</span>
      </div>

      <ApiState empty={false} error={run.isError || review.isError || (result.isError && !resultNotReady)} loading={run.isLoading || review.isLoading || result.isLoading} retry={() => { void run.refetch(); void review.refetch(); void result.refetch() }} />
      {resultNotReady && <p className="activity-empty-note">분석이 완료되면 계획서와 작업지시서 생성 기능이 준비됩니다.</p>}

      {stageDurations.length > 0 && <section className="activity-plan-section activity-stage-timing">
        <header><span>단계별 소요 시간</span>{totalDurationMs != null && <h3>총 {formatDuration(totalDurationMs)}</h3>}</header>
        <ol className="activity-stage-timing-list">
          {stageDurations.map(({ stage, durationMs }) => <li key={stage.stage_snapshot_id}>
            <span>{STAGE_LABELS[stage.stage_name]}</span>
            <strong>{durationMs != null ? formatDuration(durationMs) : '-'}</strong>
          </li>)}
        </ol>
      </section>}

      <section className="activity-plan-section">
        <header><span>계획 제목</span><h3>{displayText(result.data?.report.title ?? item.alert_reason ?? '현장 대응 계획')}</h3></header>
        <div className="activity-plan-structured">
          <article><h4>핵심 근거</h4>{result.data?.evidence.length ? <ul>{result.data.evidence.map((entry) => <li key={`${entry.label}-${entry.content}`}><strong>{displayText(entry.label)}</strong><span>{displayText(entry.content)}</span></li>)}</ul> : <p>{displayText(snapshot?.handling_reason ?? 'AI 판단 근거를 정리하고 있습니다.')}</p>}</article>
          <article><h4>현장 영향</h4><p>{displayText(result.data?.situation ?? snapshot?.handling_reason ?? '설비 영향 범위를 확인하고 있습니다.')}</p></article>
          <article className="activity-plan-actions"><h4>권장 조치</h4><ol>{actions.map((action) => <li key={`${action.priority}-${action.title}`}><strong>{displayText(action.title)}</strong><span>{displayText(action.detail)}</span></li>)}{actions.length === 0 && <li><span>분석 완료 후 순서형 조치가 표시됩니다.</span></li>}</ol></article>
        </div>
      </section>

    </div>
  </SurfaceCard>
}
