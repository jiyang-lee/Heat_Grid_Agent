/**
 * 작업 지시서 패널 — 기계실 상세 하단.
 * 버튼 클릭 → 생성(mock/LLM) → summary/action_plan/caution 카드 표시(결과만).
 */

import { useState } from 'react'
import type { Complex } from '../data/complexes'
import type { OpsAgentOutput } from '../api/contracts'
import { generateWorkOrder, type WorkOrderMode } from '../api/workOrder'

interface Props {
  complex: Complex
}

type Phase = 'idle' | 'loading' | 'done' | 'error'

export default function WorkOrderPanel({ complex }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [output, setOutput] = useState<OpsAgentOutput | null>(null)
  const [mode, setMode] = useState<WorkOrderMode>('mock')
  const [err, setErr] = useState('')

  const run = async () => {
    setPhase('loading')
    setErr('')
    try {
      const r = await generateWorkOrder(complex)
      setOutput(r.output)
      setMode(r.mode)
      setPhase('done')
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setPhase('error')
    }
  }

  return (
    <div className="wo">
      <button type="button" className="wo-btn" onClick={run} disabled={phase === 'loading'}>
        {phase === 'loading' ? '작업 지시서 생성 중…' : phase === 'done' ? '작업 지시서 재생성' : '작업 지시서 생성'}
      </button>

      {phase === 'done' && output && (
        <div className="wo-card">
          <div className="wo-mode">{mode.toUpperCase()} · 작업 지시서</div>
          <div className="wo-sec">
            <div className="wo-k">요약</div>
            <div className="wo-v">{output.summary}</div>
          </div>
          <div className="wo-sec">
            <div className="wo-k">조치 계획</div>
            <div className="wo-v pre">{output.action_plan}</div>
          </div>
          <div className="wo-sec">
            <div className="wo-k">주의</div>
            <div className="wo-v">{output.caution}</div>
          </div>
        </div>
      )}

      {phase === 'error' && <div className="wo-err">{err}</div>}
    </div>
  )
}
