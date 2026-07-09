/**
 * 알림 상세 + 에이전트 실행.
 * POST /api/agent-runs → ops_output(작업지시서) + token/cost + agent_mode
 *   + GET /api/agent-runs/{run_id}/events (SSE 진행) + /artifacts.
 */

import { useEffect, useState } from 'react'
import type { AgentRunResponse, AlertSummary } from '../api/contracts'
import { useAgentRunResult, useArtifacts, useCreateAgentRun } from '../api/hooks'
import { agentRunEventsPath, subscribeSse } from '../api/backend'

interface Props {
  alert: AlertSummary | null
}

interface EvLine {
  type: string
  message: string
}

export default function AlertDetail({ alert }: Props) {
  const create = useCreateAgentRun()
  const [run, setRun] = useState<AgentRunResponse | null>(null)
  const [events, setEvents] = useState<EvLine[]>([])
  const artifacts = useArtifacts(run?.run_id ?? null)
  const result = useAgentRunResult(run?.run_id ?? null)

  // 선택 알림이 바뀌면 초기화
  useEffect(() => {
    setRun(null)
    setEvents([])
  }, [alert?.alert_id])

  // run 생기면 진행 이벤트(SSE) 구독
  useEffect(() => {
    if (!run) return
    setEvents([])
    return subscribeSse(agentRunEventsPath(run.run_id), (d) => {
      const e = d as EvLine
      setEvents((prev) => [...prev, { type: e.type, message: e.message }])
    })
  }, [run])

  if (!alert) return <div className="empty">왼쪽에서 알림을 선택하세요</div>

  const runAgent = async () => {
    const r = await create.mutateAsync({ alertId: alert.alert_id })
    setRun(r)
  }

  const ops = run?.ops_output
  const opsResult = result.data
  const usage = run?.token_usage
  const cost = usage?.cost_estimate

  return (
    <div className="aside-body">
      <div className="aside-meta" style={{ padding: 0, border: 'none' }}>
        <div className="bn">{alert.enqueue_reason}</div>
        <div className="ba">
          {alert.priority_level} · score {alert.priority_score?.toFixed(3) ?? '-'} · {alert.status}
          {alert.acked_by ? ` · ${alert.acked_by}` : ''}
        </div>
      </div>

      <button type="button" className="wo-btn" disabled={create.isPending} onClick={runAgent}>
        {create.isPending ? '에이전트 실행 중…' : run ? '에이전트 재실행' : '에이전트 실행 (작업 지시서 생성)'}
      </button>
      {create.isError && <div className="wo-err">실행 실패: {String(create.error)}</div>}

      {events.length > 0 && (
        <div className="ops-timeline">
          {events.map((e, i) => (
            <div key={i} className="ev">
              <span className="ev-t">{e.type}</span>
              {e.message}
            </div>
          ))}
        </div>
      )}

      {run && (opsResult || ops) && (
        <div className="wo-card">
          <div className="wo-mode">
            {(run.agent_mode ?? 'mock').toUpperCase()} · {run.run_id} · {run.status}
          </div>
          <div className="wo-sec">
            <div className="wo-k">요약</div>
            <div className="wo-v">{opsResult?.headline ?? ops?.summary}</div>
          </div>
          {opsResult && (
            <>
              <div className="wo-sec">
                <div className="wo-k">상황</div>
                <div className="wo-v">{opsResult.situation}</div>
              </div>
              <div className="wo-sec">
                <div className="wo-k">근거</div>
                <div className="wo-v pre">
                  {opsResult.evidence.map((item) => `${item.label}: ${item.content}`).join('\n')}
                </div>
              </div>
            </>
          )}
          {result.isLoading && (
            <div className="wo-sec">
              <div className="wo-k">v4 결과</div>
              <div className="wo-v">작업 지시 결과를 불러오는 중입니다.</div>
            </div>
          )}
          {result.isError && (
            <div className="wo-sec">
              <div className="wo-k">v4 결과</div>
              <div className="wo-v">기존 작업 지시서 형식으로 표시 중입니다.</div>
            </div>
          )}
          <div className="wo-sec">
            <div className="wo-k">조치 계획</div>
            <div className="wo-v pre">
              {opsResult
                ? opsResult.actions
                    .map((item) => `${item.priority}. ${item.title}\n${item.detail}`)
                    .join('\n\n')
                : ops?.action_plan}
            </div>
          </div>
          <div className="wo-sec">
            <div className="wo-k">주의</div>
            <div className="wo-v pre">{opsResult ? opsResult.cautions.join('\n') : ops?.caution}</div>
          </div>
          {opsResult && (
            <details className="wo-report">
              <summary>{opsResult.report.title}</summary>
              <pre>{opsResult.report.content}</pre>
            </details>
          )}
        </div>
      )}

      {usage && (
        <div className="statgrid">
          <div className="stat">
            <div className="k">모델 호출</div>
            <div className="v">{usage.model_calls}</div>
          </div>
          <div className="stat">
            <div className="k">총 토큰</div>
            <div className="v">{usage.total_tokens.toLocaleString()}</div>
          </div>
          <div className="stat">
            <div className="k">입력 / 출력</div>
            <div className="v">
              {usage.input_tokens.toLocaleString()} / {usage.output_tokens.toLocaleString()}
            </div>
          </div>
          <div className="stat">
            <div className="k">예상 비용</div>
            <div className="v">${cost ? cost.total_cost_usd.toFixed(5) : '0'}</div>
          </div>
          {cost && (
            <div className="stat full">
              <div className="k">단가 출처</div>
              <div className="v sm">
                {cost.model} · {cost.pricing_source}
              </div>
            </div>
          )}
        </div>
      )}

      {run && artifacts.data && artifacts.data.length > 0 && (
        <div className="ops-artifacts">
          <div className="wo-k">산출물 (artifacts)</div>
          {artifacts.data.map((a) => (
            <a key={a.artifact_id} className="artifact" href={a.uri} target="_blank" rel="noreferrer">
              <span className="pill">{a.kind}</span>
              {a.name}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
