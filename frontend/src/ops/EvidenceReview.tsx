import { useEffect, useState } from 'react'
import { useEvidenceCandidates, useReviewEvidenceCandidate } from '../api/hooks'

export default function EvidenceReview() {
  const [status, setStatus] = useState('pending')
  const candidates = useEvidenceCandidates(status)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = candidates.data?.find((item) => item.candidate_id === selectedId) ?? null
  const review = useReviewEvidenceCandidate()
  const [reviewer, setReviewer] = useState('operator')
  const [reason, setReason] = useState('')

  useEffect(() => {
    const list = candidates.data ?? []
    if (list.length && !list.some((item) => item.candidate_id === selectedId)) setSelectedId(list[0].candidate_id)
  }, [candidates.data, selectedId])

  const send = (decision: 'approve' | 'reject') => {
    if (!selected) return
    review.mutate({ candidateId: selected.candidate_id, body: { decision, reviewer, reason } })
  }

  return (
    <div className="automation-page">
      <div className="ops-filters"><div className="seg">
        {['pending', 'approved', 'auto_approved', 'rejected', 'ingest_failed', 'all'].map((item) => (
          <button key={item} type="button" className={`seg-b ${status === item ? 'on' : ''}`} onClick={() => setStatus(item)}>{item === 'pending' ? '대기' : item === 'approved' ? '승인' : item === 'auto_approved' ? '자동 승인' : item === 'rejected' ? '반려' : item === 'ingest_failed' ? '적재 실패' : '전체'}</button>
        ))}
      </div></div>
      <div className="automation-grid">
        <section className="panel automation-list">
          <div className="panel-head"><span>근거 후보</span><span className="tag">{candidates.data?.length ?? 0}</span></div>
          <div className="aside-body">
            {candidates.data?.map((item) => (
              <button key={item.candidate_id} type="button" className={`review-row ${selectedId === item.candidate_id ? 'active' : ''}`} onClick={() => setSelectedId(item.candidate_id)}>
                <span className={`review-risk risk-${item.risk_level}`}>{Math.round(item.trust_score * 100)}</span>
                <span className="review-row-main"><b>{item.title}</b><small>{item.source_type} · {item.status}</small></span>
              </button>
            ))}
            {candidates.isLoading && <div className="empty">근거 후보를 불러오는 중입니다.</div>}
            {candidates.data?.length === 0 && <div className="empty">해당 상태의 근거 후보가 없습니다.</div>}
          </div>
        </section>
        <section className="panel automation-detail">
          <div className="panel-head"><span>원문 및 적재 검수</span><span className="tag">EVIDENCE</span></div>
          {!selected && <div className="empty">왼쪽에서 근거 후보를 선택하세요.</div>}
          {selected && <div className="form-stack">
            <div className="detail-line"><span>상태</span><b>{selected.status}</b></div>
            <div className="detail-line"><span>신뢰 점수</span><b>{selected.trust_score.toFixed(2)}</b></div>
            {selected.source_uri && <a className="source-link" href={selected.source_uri} target="_blank" rel="noreferrer">원문 출처 열기</a>}
            <div className="evidence-content">{selected.content}</div>
            {selected.rag_chunk_id && <div className="detail-line"><span>적재 청크</span><b>{selected.rag_chunk_id}</b></div>}
            <label>검수자<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
            <label>검수 사유<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
            {selected.status === 'pending' && <div className="command-row">
              <button type="button" className="mini primary" disabled={review.isPending} onClick={() => send('approve')}>승인 후 지식 적재</button>
              <button type="button" className="mini danger" disabled={review.isPending} onClick={() => send('reject')}>반려</button>
            </div>}
            {review.isError && <div className="wo-err">근거 후보 검수 저장 실패</div>}
          </div>}
        </section>
      </div>
    </div>
  )
}
