/**
 * mock API — 계약 엔드포인트를 in-memory store로 구현.
 * backend.ts가 USE_MOCK일 때 real client 대신 이걸 export한다.
 */

import type {
  AgentRunArtifact,
  AgentRunCreateRequest,
  AgentRunResponse,
  AlertAckRequest,
  AlertEnqueueResponse,
  AlertListQuery,
  AlertSummary,
  HealthStatus,
  OpsAgentResultV4,
} from './contracts'
import { ApiError } from './client'
import { buildTokenUsage, complexForAlert, store } from './mockData'
import { buildMockOpsOutput } from './workOrder'

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

function transition(alertId: string, status: 'acked' | 'resolved', ackedBy: string): AlertSummary {
  const a = store.alerts.get(alertId)
  if (!a) throw new ApiError(404, `/alerts/${alertId}`, 'alert_id를 찾을 수 없습니다.')
  const updated: AlertSummary = { ...a, status, acked_at: new Date().toISOString(), acked_by: ackedBy }
  store.alerts.set(alertId, updated)
  return updated
}

export const alertsApi = {
  async list(query?: AlertListQuery): Promise<AlertSummary[]> {
    await delay(250)
    const status = query?.status ?? 'open'
    let rows = [...store.alerts.values()]
    if (status !== 'all') rows = rows.filter((a) => a.status === status)
    if (query?.priority_level) rows = rows.filter((a) => a.priority_level === query.priority_level)
    return rows.sort(
      (a, b) => b.created_at.localeCompare(a.created_at) || (b.priority_score ?? 0) - (a.priority_score ?? 0),
    )
  },
  async get(alertId: string): Promise<AlertSummary> {
    await delay(120)
    const a = store.alerts.get(alertId)
    if (!a) throw new ApiError(404, `/alerts/${alertId}`, 'alert_id를 찾을 수 없습니다.')
    return a
  },
  async ack(alertId: string, body: AlertAckRequest): Promise<AlertSummary> {
    await delay(200)
    return transition(alertId, 'acked', body.acked_by)
  },
  async resolve(alertId: string, body: AlertAckRequest): Promise<AlertSummary> {
    await delay(200)
    return transition(alertId, 'resolved', body.acked_by)
  },
  async enqueue(): Promise<AlertEnqueueResponse> {
    await delay(150)
    const open = [...store.alerts.values()].filter((a) => a.status === 'open').length
    return { queued_count: 0, existing_count: store.alerts.size, open_count: open, total_count: store.alerts.size }
  },
}

export const agentRunsApi = {
  async create(body: AgentRunCreateRequest): Promise<AgentRunResponse> {
    await delay(1100)
    const alert = store.alerts.get(body.alert_id)
    if (!alert) throw new ApiError(404, '/agent-runs', 'alert_id를 찾을 수 없습니다.')
    const complex = complexForAlert(body.alert_id)
    const opsOutput = complex
      ? buildMockOpsOutput(complex)
      : { summary: '-', action_plan: '-', caution: '-' }
    const tokenUsage = buildTokenUsage(opsOutput)
    const runId = `run-${String(store.runSeq++).padStart(4, '0')}`
    const run: AgentRunResponse = {
      run_id: runId,
      status: 'completed',
      input_source: 'alert',
      alert_id: body.alert_id,
      card_id: alert.card_id,
      agent_mode: 'llm',
      ops_output: opsOutput,
      token_usage: tokenUsage,
      error: null,
    }
    store.runs.set(runId, run)
    store.artifacts.set(runId, [
      { artifact_id: `${runId}-ev`, run_id: runId, kind: 'evidence', name: `evidence_${alert.card_id}.json`, uri: `/artifacts/${runId}/evidence.json` },
      { artifact_id: `${runId}-rp`, run_id: runId, kind: 'report', name: 'ops_action_report.md', uri: `/artifacts/${runId}/report.md` },
    ])
    return run
  },
  async get(runId: string): Promise<AgentRunResponse> {
    await delay(120)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}`, 'run_id를 찾을 수 없습니다.')
    return r
  },
  async result(runId: string): Promise<OpsAgentResultV4> {
    await delay(160)
    const r = store.runs.get(runId)
    if (!r) throw new ApiError(404, `/agent-runs/${runId}/result`, 'run_id를 찾을 수 없습니다.')
    const output = r.ops_output
    if (!output) throw new ApiError(409, `/agent-runs/${runId}/result`, 'agent run result is not ready.')
    return {
      schema_version: 'ops_agent_result.v4',
      run_id: r.run_id,
      card_id: r.card_id,
      headline: output.summary,
      situation: output.summary,
      evidence: [
        { label: '운영 근거', content: 'mock priority card evidence', source: 'manual' },
      ],
      actions: [{ priority: 1, title: '권장 조치', detail: output.action_plan }],
      cautions: [output.caution],
      report: {
        title: '작업 지시 보고서',
        format: 'markdown',
        content: `# 작업 지시 보고서\n\n## 상황 요약\n${output.summary}\n\n## 권장 조치\n${output.action_plan}\n\n## 주의 사항\n${output.caution}\n`,
      },
    }
  },
  async artifacts(runId: string): Promise<AgentRunArtifact[]> {
    await delay(150)
    if (!store.runs.has(runId)) throw new ApiError(404, `/agent-runs/${runId}/artifacts`, 'run_id를 찾을 수 없습니다.')
    return store.artifacts.get(runId) ?? []
  },
}

export const healthApi = {
  async get(): Promise<HealthStatus> {
    await delay(80)
    return { input: 'postgresql', database: 'mock', openai: 'mock', rag: 'mock' }
  },
}

/** mock SSE — 실제 EventSource 대신 타이머로 계약 이벤트를 방출. */
export function subscribeSse(path: string, onEvent: (data: unknown) => void): () => void {
  const timers: ReturnType<typeof setTimeout>[] = []
  if (path.includes('/agent-runs/') && path.endsWith('/events')) {
    const runId = path.split('/agent-runs/')[1].replace('/events', '')
    const run = store.runs.get(runId)
    if (run) {
      timers.push(
        setTimeout(
          () => onEvent({ type: 'run_started', message: 'agent run loaded', payload: { run_id: run.run_id, alert_id: run.alert_id } }),
          200,
        ),
      )
      timers.push(
        setTimeout(
          () =>
            onEvent({
              type: 'run_completed',
              message: 'agent run completed',
              payload: {
                run_id: run.run_id,
                status: run.status,
                card_id: run.card_id,
                agent_mode: run.agent_mode,
                ops_output: run.ops_output,
                token_usage: run.token_usage,
              },
            }),
          700,
        ),
      )
    }
  } else if (path.endsWith('/alerts/events')) {
    const open = [...store.alerts.values()].filter((a) => a.status === 'open')
    timers.push(
      setTimeout(() => onEvent({ type: 'alerts_snapshot', message: 'current open alerts loaded', payload: { alerts: open } }), 200),
    )
  }
  return () => timers.forEach(clearTimeout)
}

export const alertEventsPath = '/alerts/events'
export const agentRunEventsPath = (runId: string) => `/agent-runs/${runId}/events`
