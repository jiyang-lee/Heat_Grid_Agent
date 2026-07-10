import { useEffect, useState } from 'react'
import type { HumanReviewTask, OpsAgentOutput } from '../api/contracts'
import { useReviewTasks, useSubmitReviewTask } from '../api/hooks'

function taskOutput(task: HumanReviewTask | null): OpsAgentOutput | null {
  const value = task?.payload.ops_output
  if (!value || typeof value !== 'object') return null
  const output = value as Record<string, unknown>
  if (
    typeof output.summary !== 'string' ||
    typeof output.action_plan !== 'string' ||
    typeof output.caution !== 'string'
  ) return null
  return {
    summary: output.summary,
    action_plan: output.action_plan,
    caution: output.caution,
  }
}

export default function ReviewQueue() {
  const [status, setStatus] = useState('pending')
  const tasks = useReviewTasks(status)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = tasks.data?.find((item) => item.task_id === selectedId) ?? null
  const submit = useSubmitReviewTask()
  const [reviewer, setReviewer] = useState('operator')
  const [reason, setReason] = useState('')
  const [correctedLabel, setCorrectedLabel] = useState('')
  const [summary, setSummary] = useState('')
  const [actionPlan, setActionPlan] = useState('')
  const [caution, setCaution] = useState('')

  useEffect(() => {
    const list = tasks.data ?? []
    if (list.length && !list.some((item) => item.task_id === selectedId)) {
      setSelectedId(list[0].task_id)
    }
  }, [tasks.data, selectedId])

  useEffect(() => {
    const output = taskOutput(selected)
    setSummary(output?.summary ?? '')
    setActionPlan(output?.action_plan ?? '')
    setCaution(output?.caution ?? '')
    setCorrectedLabel('')
    setReason('')
  }, [selected?.task_id])

  const send = (decision: 'approve' | 'reject' | 'correct') => {
    if (!selected) return
    const correctedOutput = summary && actionPlan && caution
      ? { summary, action_plan: actionPlan, caution }
      : undefined
    submit.mutate({
      taskId: selected.task_id,
      body: {
        decision,
        reviewer,
        reason,
        corrected_output: decision === 'correct' ? correctedOutput : undefined,
        corrected_label: decision === 'correct' && correctedLabel ? correctedLabel : undefined,
      },
    })
  }

  return (
    <div className="automation-page">
      <div className="ops-filters">
        <div className="seg">
          {['pending', 'approved', 'rejected', 'corrected', 'all'].map((item) => (
            <button key={item} type="button" className={`seg-b ${status === item ? 'on' : ''}`} onClick={() => setStatus(item)}>
              {item === 'pending' ? '대기' : item === 'approved' ? '승인' : item === 'rejected' ? '반려' : item === 'corrected' ? '교정' : '전체'}
            </button>
          ))}
        </div>
      </div>
      <div className="automation-grid">
        <section className="panel automation-list">
          <div className="panel-head"><span>검수 작업</span><span className="tag">{tasks.data?.length ?? 0}</span></div>
          <div className="aside-body">
            {tasks.isLoading && <div className="empty">검수 작업을 불러오는 중입니다.</div>}
            {tasks.isError && <div className="wo-err">검수 작업 조회 실패</div>}
            {tasks.data?.map((task) => (
              <button key={task.task_id} type="button" className={`review-row ${selectedId === task.task_id ? 'active' : ''}`} onClick={() => setSelectedId(task.task_id)}>
                <span className={`review-risk risk-${task.risk_level}`}>{task.risk_level}</span>
                <span className="review-row-main"><b>{task.title}</b><small>{task.task_type} · {task.status}</small></span>
              </button>
            ))}
            {tasks.data?.length === 0 && <div className="empty">해당 상태의 검수 작업이 없습니다.</div>}
          </div>
        </section>
        <section className="panel automation-detail">
          <div className="panel-head"><span>검수 상세</span><span className="tag">HUMAN REVIEW</span></div>
          {!selected && <div className="empty">왼쪽에서 검수 작업을 선택하세요.</div>}
          {selected && (
            <div className="form-stack">
              <div className="detail-line"><span>유형</span><b>{selected.task_type}</b></div>
              <div className="detail-line"><span>위험도</span><b>{selected.risk_level}</b></div>
              <label>검수자<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
              {taskOutput(selected) && (
                <>
                  <label>상황 요약<textarea value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
                  <label>조치 계획<textarea value={actionPlan} onChange={(event) => setActionPlan(event.target.value)} /></label>
                  <label>주의 사항<textarea value={caution} onChange={(event) => setCaution(event.target.value)} /></label>
                </>
              )}
              <label>교정 라벨
                <select value={correctedLabel} onChange={(event) => setCorrectedLabel(event.target.value)}>
                  <option value="">변경 없음</option><option value="normal">정상</option><option value="pre_fault">고장 전조</option>
                </select>
              </label>
              <label>검수 사유<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
              {selected.status === 'pending' && (
                <div className="command-row">
                  <button type="button" className="mini primary" disabled={submit.isPending} onClick={() => send('approve')}>승인</button>
                  <button type="button" className="mini" disabled={submit.isPending} onClick={() => send('correct')}>교정 반영</button>
                  <button type="button" className="mini danger" disabled={submit.isPending} onClick={() => send('reject')}>반려</button>
                </div>
              )}
              {submit.data?.automatic_retrain_job_id && (
                <div className="save-ok">교정 라벨이 반영되어 자동 재학습이 시작됐습니다.</div>
              )}
              {submit.isSuccess && !submit.data.automatic_retrain_job_id && (
                <div className="save-ok">검수 결과가 저장됐습니다.</div>
              )}
              {submit.isError && <div className="wo-err">검수 결과 저장 실패</div>}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
