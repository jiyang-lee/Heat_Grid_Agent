import type { AgentReportListItem } from '../../api/contracts'
import { API_BASE, ApiError } from '../../api/client'
import { useAgentRunResult } from '../../api/hooks'
import { safeFilePart } from '../../scenario/documentPdf'
import { ApiState, Button, StatusBadge, SurfaceCard } from '../ui'
import { facilityName, formatDateTime, reportStatusLabel, reportTitle, reviewStatusTone } from './activityMappers'

interface Props {
  readonly item: AgentReportListItem
  readonly onClose: () => void
}

export function ReportDetail({ item, onClose }: Props) {
  const result = useAgentRunResult(item.run_id)
  const resultNotReady = result.error instanceof ApiError && result.error.status === 409
  const title = result.data?.report.title ?? reportTitle(item.kind, item.name)
  const facility = facilityName(item.substation_id, item.manufacturer_id)
  const created = new Date(item.created_at)
  const date = Number.isNaN(created.getTime()) ? 'unknown-date' : created.toISOString().slice(0, 10)
  const extension = item.name.includes('.') ? item.name.split('.').at(-1)?.toLowerCase() ?? 'json' : 'json'
  const fileName = `heatgrid-report-${safeFilePart(title)}-${safeFilePart(facility)}-${date}.${extension}`
  const downloadUrl = `${API_BASE}/agent-runs/${item.run_id}/artifacts/${item.artifact_id}/content`

  return <SurfaceCard action={<Button aria-label="상세 닫기" icon="x" onClick={onClose} />} className="activity-detail" title="보고서 상세">
    <div className="detail-body">
      <div className="detail-title">
        <StatusBadge tone={reviewStatusTone(item.operator_review_status)}>{reportStatusLabel(item.operator_review_status)}</StatusBadge>
        <h2>{title}</h2>
        <p>{facility} · 기계실 {item.substation_id ?? '-'}</p>
        <span>생성 {formatDateTime(item.created_at)}</span>
      </div>
      <ApiState empty={false} error={result.isError && !resultNotReady} loading={result.isLoading} retry={() => void result.refetch()} />
      {resultNotReady && <p className="activity-empty-note">실행이 완료되면 보고서 본문을 확인할 수 있습니다.</p>}
      {result.data && <article className="work-order-document report-official-document"><header><div><small>AI 사고 조치 보고서</small><h3>{title}</h3></div><StatusBadge tone={reviewStatusTone(item.operator_review_status)}>{reportStatusLabel(item.operator_review_status)}</StatusBadge></header><dl><div><dt>대상 설비</dt><dd>{facility}</dd></div><div><dt>생성 시간</dt><dd>{formatDateTime(item.created_at)}</dd></div></dl><pre className="activity-report-body report-single-body">{result.data.report.content}</pre></article>}
      <div className="detail-actions activity-guide-actions"><a className="ops-button button-ghost" download={fileName} href={downloadUrl}>원본 {extension.toUpperCase()} 다운로드</a></div>
    </div>
  </SurfaceCard>
}
