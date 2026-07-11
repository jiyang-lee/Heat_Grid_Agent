import { useState } from 'react'
import {
  useActiveModelDeployment,
  useCreateRetrainJob,
  useModelCandidates,
  usePromoteModelCandidate,
  useRetrainJobs,
  useReviewRetrainJob,
  useTrainingFeedback,
} from '../api/hooks'

export default function ModelLifecycle() {
  const jobs = useRetrainJobs()
  const candidates = useModelCandidates()
  const feedback = useTrainingFeedback()
  const active = useActiveModelDeployment()
  const createJob = useCreateRetrainJob()
  const reviewJob = useReviewRetrainJob()
  const promote = usePromoteModelCandidate()
  const [reviewer, setReviewer] = useState('operator')
  const [reason, setReason] = useState('누적 검수 피드백 반영')

  const create = () => createJob.mutate({ requested_by: reviewer, reason, feedback_ids: [], auto_start_when_approved: false })
  const actJob = (jobId: string, approve: boolean) => reviewJob.mutate({ jobId, approve, body: { reviewer, reason } })
  const actCandidate = (candidateId: string, decision: 'promote' | 'reject') => promote.mutate({ candidateId, body: { reviewer, reason, decision } })

  return (
    <div className="automation-page model-page">
      <section className="panel lifecycle-control">
        <div className="panel-head"><span>재학습 실행 제어</span><span className="tag">TRAINING</span></div>
        <div className="form-row">
          <label>요청자<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
          <label className="grow">실행 사유<input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <button type="button" className="mini primary" disabled={createJob.isPending || !reason} onClick={create}>재학습 요청 생성</button>
        </div>
        <div className="lifecycle-summary">
          <span>검수 피드백 <b>{feedback.data?.length ?? 0}</b></span>
          <span>활성 모델 <b>{active.data?.version ?? '기본 모델'}</b></span>
          <span>승격자 <b>{active.data?.promoted_by ?? '-'}</b></span>
        </div>
      </section>
      <div className="automation-grid">
        <section className="panel automation-list">
          <div className="panel-head"><span>재학습 작업</span><span className="tag">{jobs.data?.length ?? 0}</span></div>
          <div className="aside-body lifecycle-list">
            {jobs.data?.map((job) => <article key={job.job_id} className="lifecycle-item">
              <div><b>{job.job_id}</b><small>{job.status} · 피드백 {String(job.dataset_snapshot.feedback_count ?? 0)}건</small></div>
              {job.error && <div className="wo-err">{job.error}</div>}
              {job.status === 'pending_approval' && <div className="command-row">
                <button type="button" className="mini primary" onClick={() => actJob(job.job_id, true)}>실행 승인</button>
                <button type="button" className="mini danger" onClick={() => actJob(job.job_id, false)}>반려</button>
              </div>}
            </article>)}
            {jobs.data?.length === 0 && <div className="empty">재학습 작업이 없습니다.</div>}
          </div>
        </section>
        <section className="panel automation-detail">
          <div className="panel-head"><span>모델 후보 및 최종 승격</span><span className="tag">PROMOTION</span></div>
          <div className="aside-body lifecycle-list">
            {candidates.data?.map((candidate) => <article key={candidate.candidate_id} className="lifecycle-item">
              <div><b>{candidate.version}</b><small>{candidate.status} · {candidate.artifact_uri}</small></div>
              <div className="detail-line"><span>검증 피드백</span><b>{String(candidate.validation_summary.reviewed_feedback_count ?? 0)}건</b></div>
              {candidate.status === 'awaiting_promotion' && <div className="command-row">
                <button type="button" className="mini primary" onClick={() => actCandidate(candidate.candidate_id, 'promote')}>최종 승격</button>
                <button type="button" className="mini danger" onClick={() => actCandidate(candidate.candidate_id, 'reject')}>후보 반려</button>
              </div>}
            </article>)}
            {candidates.data?.length === 0 && <div className="empty">승격 대기 모델 후보가 없습니다.</div>}
          </div>
        </section>
      </div>
    </div>
  )
}
