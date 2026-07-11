import type {
  AlertSummary,
  PriorityEvaluationResult,
  PriorityEvaluationRun,
} from '../api/contracts'
import { complexes } from '../data/complexes'
import {
  formatMetric,
  PRIORITY_STATUS_LABEL,
  priorityDisplayStatus,
} from '../domain/priority'

interface Props {
  selectedId: number | null
  onSelect: (id: number) => void
  onOpenRoom: (id: number) => void
  onOpenOps: (alertId: string) => void
  evaluation: PriorityEvaluationRun | null
  results: PriorityEvaluationResult[]
  alerts: AlertSummary[]
  loading: boolean
  error: boolean
}

function ageLabel(seconds: number | null): string {
  if (seconds == null) return '-'
  const hours = seconds / 3600
  return hours < 24 ? `${hours.toFixed(1)}시간` : `${(hours / 24).toFixed(1)}일`
}

export default function PriorityAside({
  selectedId,
  onSelect,
  onOpenRoom,
  onOpenOps,
  evaluation,
  results,
  alerts,
  loading,
  error,
}: Props) {
  const resultById = new Map(results.map((result) => [result.substation_id, result]))
  const list = complexes
    .map((complex) => ({ complex, result: resultById.get(complex.id) }))
    .sort((left, right) => {
      const leftRank = left.result?.priority_rank ?? Number.MAX_SAFE_INTEGER
      const rightRank = right.result?.priority_rank ?? Number.MAX_SAFE_INTEGER
      return leftRank - rightRank || left.complex.id - right.complex.id
    })
  const selected = selectedId == null ? null : list.find((item) => item.complex.id === selectedId) ?? null
  const selectedAlert = selected?.result
    ? alerts.find(
        (alert) =>
          alert.evaluation_run_id === selected.result?.evaluation_run_id &&
          alert.substation_id === selected.result?.substation_id,
      ) ?? null
    : null

  if (loading) return <div className="empty">31개 Substation 평가를 불러오는 중입니다.</div>
  if (error) return <div className="priority-error">Priority 평가 API 조회에 실패했습니다.</div>

  return (
    <div className="priority-runtime">
      <div className="snapshot-strip">
        <span>평가 기준 <b>{evaluation ? new Date(evaluation.as_of_time).toLocaleString('ko-KR') : '-'}</b></span>
        <span>순위 포함 <b>{evaluation?.ranked_count ?? 0}</b></span>
        <span>지연·누락 <b>{(evaluation?.stale_count ?? 0) + (evaluation?.missing_count ?? 0)}</b></span>
      </div>

      {selected?.result && (
        <div className="priority-selected">
          <div className="selected-heading">
            <div><b>Substation {selected.complex.id}</b><span>{selected.complex.name}</span></div>
            <span className={`snapshot-status status-${priorityDisplayStatus(selected.result)}`}>
              {PRIORITY_STATUS_LABEL[priorityDisplayStatus(selected.result)]}
            </span>
          </div>
          <div className="priority-metrics">
            <span>전체 순위<b>{selected.result.priority_rank ? `${selected.result.priority_rank}위` : '제외'}</b></span>
            <span>Priority<b>{formatMetric(selected.result.priority_score)}</b></span>
            <span>위험도<b>{formatMetric(selected.result.risk_score, 3)}</b></span>
            <span>이상탐지<b>{formatMetric(selected.result.anomaly_score, 3)}</b></span>
            <span>고장 임박도<b>{formatMetric(selected.result.leadtime_urgency_score, 3)}</b></span>
            <span>데이터 경과<b>{ageLabel(selected.result.data_age_seconds)}</b></span>
          </div>
          <div className="snapshot-source-time">
            원시 창 {selected.result.source_window_end ? new Date(selected.result.source_window_end).toLocaleString('ko-KR') : '없음'}
          </div>
          <div className="command-row">
            <button type="button" className="mini" onClick={() => onOpenRoom(selected.complex.id)}>기계실</button>
            {selectedAlert ? (
              <button type="button" className="mini primary" onClick={() => onOpenOps(selectedAlert.alert_id)}>알림·에이전트</button>
            ) : (
              <span className="no-alert">최신 스냅샷 알림 대상 아님</span>
            )}
          </div>
        </div>
      )}

      <div className="priority-list" aria-label="전체 Substation 우선순위">
        {list.map(({ complex, result }) => {
          const status = priorityDisplayStatus(result)
          return (
            <button
              key={complex.id}
              type="button"
              className={`priority-row ${selectedId === complex.id ? 'active' : ''}`}
              onClick={() => onSelect(complex.id)}
            >
              <span className="rank">{result?.priority_rank ?? '-'}</span>
              <span className="info">
                <b>{complex.id}. {complex.name}</b>
                <small>{complex.addr}</small>
              </span>
              <span className="priority-score">{formatMetric(result?.priority_score ?? null)}</span>
              <span className={`snapshot-status status-${status}`}>{PRIORITY_STATUS_LABEL[status]}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
