import { useEffect, useState } from 'react'
import { agentRunEventsPath, agentRunsApi, ApiError, subscribeSse } from '../api/client'

export const ANALYSIS_PHASES = [
  '기존 예측 결과 확인중',
  '외부데이터 확인중',
  '전문 문서 확인중',
  '계획서 정리중',
] as const

type AnalysisStatus = 'idle' | 'running' | 'completed' | 'failed'

interface AnalysisState {
  readonly error: string | null
  readonly phase: number
  readonly status: AnalysisStatus
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value != null && !Array.isArray(value)
}

function phaseFor(event: unknown): number | null {
  if (!isRecord(event) || typeof event.type !== 'string') return null
  const payload = isRecord(event.payload) ? event.payload : null
  const next = payload && typeof payload.next === 'string' ? payload.next : ''
  const tool = payload && typeof payload.tool === 'string' ? payload.tool : ''

  if (event.type === 'run_completed' || (event.type === 'status_changed' && payload?.status === 'completed')) return ANALYSIS_PHASES.length
  if (event.type === 'run_failed' || (event.type === 'status_changed' && payload?.status === 'failed')) return -1
  if (next === 'generate_operational_answer' || next === 'write_anomaly_report' || ['final_output', 'output_retry', 'review_requested', 'report_written'].includes(event.type)) return 3
  if (next === 'verify_active_models' || ['model_verification_started', 'model_verification', 'model_reverified', 'loop_decision'].includes(event.type)) return 0
  if (tool === 'get_internal_references' || event.type === 'evidence_expanded') return 2
  if (next === 'get_external_context' || tool === 'get_external_context') return 1
  return 0
}

export function agentAnalysisErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'AI 조치 실행 정보를 찾지 못했습니다. 백엔드 연결 상태를 확인해 주세요.'
    return `AI 조치 실행을 처리하지 못했습니다. (오류 ${error.status})`
  }
  return 'AI 조치 실행을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
}

export function useAgentAnalysis(runId: string | null): AnalysisState {
  const [state, setState] = useState<AnalysisState>({ error: null, phase: 0, status: 'idle' })

  useEffect(() => {
    if (runId == null) {
      setState({ error: null, phase: 0, status: 'idle' })
      return undefined
    }

    let terminal = false
    let pollPending = false
    setState({ error: null, phase: 0, status: 'running' })

    const complete = () => {
      if (terminal) return
      terminal = true
      setState({ error: null, phase: ANALYSIS_PHASES.length, status: 'completed' })
    }
    const fail = (error: unknown) => {
      if (terminal) return
      terminal = true
      setState({ error: agentAnalysisErrorMessage(error), phase: 0, status: 'failed' })
    }
    const stopEvents = subscribeSse(agentRunEventsPath(runId), (event) => {
      const phase = phaseFor(event)
      if (phase === ANALYSIS_PHASES.length) complete()
      else if (phase === -1) fail(new Error('AI 조치 분석 실행이 실패했습니다.'))
      else if (phase != null) setState((current) => current.status === 'running' ? { ...current, phase: Math.max(current.phase, phase) } : current)
    })
    const poll = window.setInterval(() => {
      if (terminal || pollPending) return
      pollPending = true
      void agentRunsApi.get(runId)
        .then((run) => {
          if (run.status === 'completed') complete()
          else if (run.status === 'failed') fail(new Error(run.error || 'AI 조치 분석 실행이 실패했습니다.'))
        })
        .catch(fail)
        .finally(() => { pollPending = false })
    }, 1_000)

    return () => {
      terminal = true
      stopEvents()
      window.clearInterval(poll)
    }
  }, [runId])

  return state
}
