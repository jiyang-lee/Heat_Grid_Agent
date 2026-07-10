import { useEffect, useState } from 'react'
import type { AutomationMode } from '../api/contracts'
import { useAutomationPolicy, useUpdateAutomationPolicy } from '../api/hooks'

export default function AutomationPolicyPanel() {
  const policy = useAutomationPolicy()
  const update = useUpdateAutomationPolicy()
  const [mode, setMode] = useState<AutomationMode>('human_only')
  const [autoTransition, setAutoTransition] = useState(false)
  const [reviewCount, setReviewCount] = useState(100)
  const [approvalRate, setApprovalRate] = useState(0.95)
  const [confidence, setConfidence] = useState(0.9)
  const [sourceTrust, setSourceTrust] = useState(0.85)
  const [drift, setDrift] = useState(0.1)

  useEffect(() => {
    if (!policy.data) return
    setMode(policy.data.mode)
    setAutoTransition(policy.data.auto_transition_enabled)
    setReviewCount(policy.data.minimum_review_count)
    setApprovalRate(policy.data.minimum_approval_rate)
    setConfidence(policy.data.minimum_confidence)
    setSourceTrust(policy.data.minimum_source_trust)
    setDrift(policy.data.maximum_drift_score)
  }, [policy.data])

  const save = () => update.mutate({
    mode,
    auto_transition_enabled: autoTransition,
    minimum_review_count: reviewCount,
    minimum_approval_rate: approvalRate,
    minimum_confidence: confidence,
    minimum_source_trust: sourceTrust,
    maximum_drift_score: drift,
    updated_by: 'operator',
  })

  return <div className="automation-page policy-page">
    <section className="panel">
      <div className="panel-head"><span>단계적 자동화 정책</span><span className="tag">POLICY</span></div>
      <div className="policy-body">
        <div className="policy-state">
          <span>누적 검수 <b>{policy.data?.reviewed_count ?? 0}</b></span>
          <span>승인 일치율 <b>{((policy.data?.approval_rate ?? 0) * 100).toFixed(1)}%</b></span>
          <span>자동화 자격 <b>{policy.data?.eligible_for_guarded_auto ? '충족' : '미충족'}</b></span>
          <span>최종 검수 <b>항상 사람</b></span>
        </div>
        <div className="seg policy-mode">
          {([
            ['human_only', '전면 검수'],
            ['assisted', '검수 보조'],
            ['guarded_auto', '제한 자동'],
          ] as const).map(([value, label]) => <button key={value} type="button" className={`seg-b ${mode === value ? 'on' : ''}`} onClick={() => setMode(value)}>{label}</button>)}
        </div>
        <label className="toggle-line"><input type="checkbox" checked={autoTransition} onChange={(event) => setAutoTransition(event.target.checked)} /> 기준 충족 시 제한 자동 단계로 전환</label>
        <div className="policy-grid">
          <label>최소 검수 건수<input type="number" min="1" value={reviewCount} onChange={(event) => setReviewCount(Number(event.target.value))} /></label>
          <label>최소 승인 일치율<input type="number" min="0" max="1" step="0.01" value={approvalRate} onChange={(event) => setApprovalRate(Number(event.target.value))} /></label>
          <label>최소 판단 신뢰도<input type="number" min="0" max="1" step="0.01" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} /></label>
          <label>최소 출처 신뢰도<input type="number" min="0" max="1" step="0.01" value={sourceTrust} onChange={(event) => setSourceTrust(Number(event.target.value))} /></label>
          <label>최대 드리프트 점수<input type="number" min="0" max="1" step="0.01" value={drift} onChange={(event) => setDrift(Number(event.target.value))} /></label>
        </div>
        <div className="command-row"><button type="button" className="mini primary" disabled={update.isPending} onClick={save}>정책 저장</button></div>
        {update.isSuccess && <div className="save-ok">정책이 저장됐습니다.</div>}
        {update.isError && <div className="wo-err">정책 저장 실패</div>}
      </div>
    </section>
  </div>
}
