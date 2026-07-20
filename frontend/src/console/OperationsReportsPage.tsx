import { useEffect, useMemo, useState } from 'react'
import { operationsReportsApi } from '../api/client'
import type { CurrentShiftMemo, OperationsReportPeriod } from '../api/contracts'
import { operationsDateTime } from './operationsTime'
import { Button, StatusBadge, SurfaceCard, type Tone } from './ui'

function reportTone(status: OperationsReportPeriod['status']): Tone {
  if (status === 'official') return 'success'
  if (status === 'failed' || status === 'overdue') return 'critical'
  return 'warning'
}

function reportTypeLabel(type: OperationsReportPeriod['report_type']): string {
  return type === 'shift' ? '교대 인계' : '일일 운영'
}

function reportStatusLabel(status: OperationsReportPeriod['status']): string {
  return { pending: '생성 대기', generating: '생성 중', official: '공식본', failed: '생성 실패', overdue: '생성 지연' }[status]
}

interface Props {
  readonly refreshRevision: number
}

export function OperationsReportsPage({ refreshRevision }: Props) {
  const [memo, setMemo] = useState<CurrentShiftMemo | null>(null)
  const [memoText, setMemoText] = useState('')
  const [reports, setReports] = useState<readonly OperationsReportPeriod[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setError(null)
    try {
      const [current, page] = await Promise.all([operationsReportsApi.currentShift(), operationsReportsApi.list()])
      setMemo(current)
      setMemoText(current.memo)
      setReports(page.items)
      setSelectedId((value) => page.items.some((item) => item.report_period_id === value) ? value : page.items[0]?.report_period_id ?? null)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : '운영 보고서를 불러오지 못했습니다.')
    }
  }

  useEffect(() => { void load() }, [refreshRevision])
  const selected = useMemo(() => reports.find((item) => item.report_period_id === selectedId) ?? null, [reports, selectedId])
  const latest = selected?.versions.at(-1) ?? null

  const saveMemo = async () => {
    setBusy(true)
    try {
      const saved = await operationsReportsApi.saveMemo(memoText)
      setMemo(saved)
      setMemoText(saved.memo)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : '교대 메모를 저장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const createCorrection = async () => {
    if (selected == null || latest == null || reason.trim() === '') return
    setBusy(true)
    try {
      await operationsReportsApi.correct(selected.report_period_id, {
        expected_latest_version: latest.version,
        content: latest.content,
        reason: reason.trim(),
      })
      setReason('')
      await load()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : '정정본을 만들지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const download = () => {
    if (selected == null || latest == null) return
    const blob = new Blob([JSON.stringify(latest.content, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${selected.report_type}-${selected.period_start.slice(0, 10)}-v${latest.version}.json`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return <div className="page-stack operations-reports-page">
    <SurfaceCard title="현재 교대 인계 메모">
      <div className="shift-memo-grid"><div><strong>{memo ? `${operationsDateTime(memo.period_start)} ~ ${operationsDateTime(memo.period_end)}` : '교대 시간 확인 중'}</strong><span>다음 공식 교대 보고서에 포함됩니다.</span></div><textarea aria-label="교대 인계 메모" onChange={(event) => setMemoText(event.target.value)} placeholder="다음 근무자에게 전달할 설비 상태와 미결 사항을 기록하세요." rows={4} value={memoText} /><Button disabled={busy} onClick={() => void saveMemo()} tone="primary">메모 저장</Button></div>
    </SurfaceCard>
    <div className="reports-record-layout">
      <SurfaceCard className="reports-record-list" title="공식 운영 기록">
        {reports.length === 0 ? <p className="admin-empty">생성된 운영 보고서가 없습니다.</p> : reports.map((report) => <button aria-pressed={selectedId === report.report_period_id} className={selectedId === report.report_period_id ? 'selected' : ''} key={report.report_period_id} onClick={() => setSelectedId(report.report_period_id)} type="button"><div><strong>{reportTypeLabel(report.report_type)}</strong><span>{operationsDateTime(report.period_start)} ~ {operationsDateTime(report.period_end)}</span></div><StatusBadge tone={reportTone(report.status)}>{reportStatusLabel(report.status)}</StatusBadge></button>)}
      </SurfaceCard>
      <SurfaceCard className="reports-record-detail" title="보고서 상세">
        {selected == null ? <p className="admin-empty">왼쪽에서 보고서를 선택하세요.</p> : <div className="report-record-body"><header><div><StatusBadge tone={reportTone(selected.status)}>{reportStatusLabel(selected.status)}</StatusBadge><h2>{reportTypeLabel(selected.report_type)} 보고서</h2></div>{latest && <Button icon="download" onClick={download}>내려받기</Button>}</header><dl><div><dt>대상 기간</dt><dd>{operationsDateTime(selected.period_start)} ~ {operationsDateTime(selected.period_end)}</dd></div><div><dt>공식 버전</dt><dd>{latest ? `v${latest.version}` : '-'}</dd></div><div><dt>생성 시각</dt><dd>{operationsDateTime(latest?.generated_at ?? null)}</dd></div></dl>{selected.error && <p className="form-error">{selected.error}</p>}{latest && <><pre>{JSON.stringify(latest.content, null, 2)}</pre>{latest.data_quality_caveats.length > 0 && <section><h3>데이터 품질 참고</h3><ul>{latest.data_quality_caveats.map((item) => <li key={item}>{item}</li>)}</ul></section>}<section className="report-correction"><h3>정정 이력</h3>{selected.versions.map((version) => <span key={version.report_version_id}>v{version.version}{version.correction_reason ? ` · ${version.correction_reason}` : ' · 최초 공식본'}</span>)}{selected.status === 'official' && <div><input onChange={(event) => setReason(event.target.value)} placeholder="정정 사유를 입력하세요." value={reason} /><Button disabled={busy || reason.trim() === ''} onClick={() => void createCorrection()}>정정본 만들기</Button></div>}</section></>}</div>}
      </SurfaceCard>
    </div>
    {error && <p className="form-error">{error} <button onClick={() => void load()} type="button">다시 불러오기</button></p>}
  </div>
}
