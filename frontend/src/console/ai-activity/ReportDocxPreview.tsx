import { useState } from 'react'
import type { AnomalyReportArtifact, AnomalyReportSection } from '../../api/contracts'
import { Icon } from '../icons'

interface Props {
  readonly buildingName: string
  readonly machineRoom: string
  readonly report: AnomalyReportArtifact
  readonly statusLabel: string
  readonly version: number
}

function section(report: AnomalyReportArtifact, key: string): AnomalyReportSection {
  const value = report[key]
  return value != null && typeof value === 'object' && !Array.isArray(value) ? value as AnomalyReportSection : {}
}

function rows(report: AnomalyReportArtifact, key: string): readonly AnomalyReportSection[] {
  const value = report[key]
  return Array.isArray(value) ? value.filter((item): item is AnomalyReportSection => item != null && typeof item === 'object') : []
}

function text(record: AnomalyReportSection, key: string, fallback = '-'): string {
  const value = record[key]
  if (value == null || value === '') return fallback
  if (Array.isArray(value)) return value.map(String).join(', ')
  return String(value).replace(/^#{1,6}\s+/gm, '').replace(/\n\s*\n\s*(?=\d+[.)]\s)/g, '\n\n')
}

function evidenceFor(items: readonly AnomalyReportSection[], keyword: string): AnomalyReportSection | undefined {
  return items.find((item) => text(item, 'label', '').replaceAll(' ', '').includes(keyword.replaceAll(' ', '')))
}

export function ReportDocxPreview({ buildingName, machineRoom, report, statusLabel, version }: Props) {
  const [zoom, setZoom] = useState(100)
  const metadata = section(report, 'report_metadata')
  const asset = section(report, 'target_asset')
  const priority = section(report, 'priority_summary')
  const situation = section(report, 'situation_summary')
  const risk = section(report, 'risk_analysis')
  const evidence = rows(report, 'key_evidence')
  const actions = rows(report, 'recommended_actions')
  const measurements = rows(report, 'sensor_measurements')
  const sensorLabels = ['공급 온도', '환수 온도', '온도차 ΔT', '유량', '차압']
  const measurementFor = (label: string) => measurements.find((item) => text(item, 'label', '').replaceAll(' ', '') === label.replaceAll(' ', '')) ?? evidenceFor(evidence, label)
  const modelRows = [
    ['Anomaly', text(section(report, 'model_judgment'), 'anomaly_score', text(priority, 'priority_score')), text(section(report, 'model_judgment'), 'anomaly_label', text(situation, 'current_status')), text(section(report, 'model_judgment'), 'reason', text(situation, 'summary'))],
    ['Risk', text(priority, 'priority_score'), text(risk, 'risk_level'), text(risk, 'risk_summary')],
    ['Lead time', text(priority, 'urgency'), '검토 필요', text(priority, 'priority_reason')],
    ['M1 Specialist', text(evidenceFor(evidence, '불일치') ?? {}, 'value'), evidenceFor(evidence, '불일치') ? '불일치' : '확인 필요', text(evidenceFor(evidence, '불일치') ?? {}, 'interpretation')],
    ['Hybrid Priority', text(priority, 'priority_score'), text(priority, 'priority_level'), text(priority, 'priority_reason')],
  ]

  return <div className="work-order-document-viewer report-docx-viewer">
    <div aria-label="문서 보기 도구" className="work-order-viewer-toolbar" role="toolbar">
      <button aria-label="축소" disabled={zoom <= 70} onClick={() => setZoom((value) => Math.max(70, value - 10))} type="button"><Icon name="minus" /></button>
      <span aria-label="확대 비율" role="status">{zoom}%</span>
      <button aria-label="확대" disabled={zoom >= 130} onClick={() => setZoom((value) => Math.min(130, value + 10))} type="button"><Icon name="plus" /></button>
      <button aria-label="너비 맞춤" onClick={() => setZoom(100)} type="button"><Icon name="expand" /></button>
      <span>양식 미리보기</span>
    </div>
    <div className="work-order-viewer-viewport report-preview-viewport">
      <div className="report-docx-pages" style={{ transform: `scale(${zoom / 100})` }}>
        <article aria-label="DOCX 양식 이상 분석 보고서 미리보기" className="report-docx-page cover-page">
          <div className="report-page-brand">HEATGRID OPS | AI 이상 분석 보고서</div>
          <header><h2>AI 이상 분석 보고서</h2><p>단일 알림 · 모델 판단 · 현장 검토용</p></header>
          <dl className="report-cover-grid">
            <div><dt>보고서 번호</dt><dd>{text(metadata, 'report_id')}</dd></div><div><dt>보고서 유형</dt><dd>AI 이상 분석</dd></div>
            <div><dt>대상 건물</dt><dd>{buildingName}</dd></div><div><dt>기계실</dt><dd>{machineRoom}</dd></div>
            <div><dt>대상 설비/계통</dt><dd>{text(asset, 'asset_label', text(asset, 'configuration_type'))}</dd></div><div><dt>설비 ID</dt><dd>-</dd></div>
            <div><dt>대상 기간</dt><dd>{text(asset, 'window_start')} ~ {text(asset, 'window_end')}</dd></div><div><dt>생성 일시</dt><dd>{text(metadata, 'generated_at')}</dd></div>
            <div><dt>작성자</dt><dd>AI 초안</dd></div><div><dt>검토자</dt><dd></dd></div>
            <div><dt>승인 상태</dt><dd>{statusLabel}</dd></div><div><dt>문서 버전</dt><dd>v{version}</dd></div>
          </dl>
          <aside>본 문서는 운영 의사결정을 지원하는 초안입니다. 현장 조치와 승인 책임은 지정된 담당자에게 있습니다.</aside>
        </article>

        <article className="report-docx-page">
          <h3>1. 의사결정 요약</h3>
          <dl className="report-kpi-grid">
            <div><dt>최종 상태</dt><dd>{text(situation, 'current_status', text(situation, 'headline'))}</dd></div>
            <div><dt>우선순위</dt><dd>{text(priority, 'priority_level')}</dd></div>
            <div><dt>위험 점수</dt><dd>{text(priority, 'priority_score')}</dd></div>
            <div><dt>신뢰 수준</dt><dd>{text(priority, 'confidence')}</dd></div>
            <div><dt>예상 선행시간</dt><dd>{text(priority, 'urgency')}</dd></div>
            <div><dt>현장 검토</dt><dd>{text(priority, 'operator_review')}</dd></div>
            <div><dt>모델 일치</dt><dd>{evidenceFor(evidence, '불일치') ? '불일치' : '확인 필요'}</dd></div>
            <div><dt>데이터 완전성</dt><dd>원자료 확인 필요</dd></div>
          </dl>
          <section className="report-callout"><strong>관리자 요약</strong><p>{text(situation, 'summary')}</p></section>
          <section className="report-callout decision"><strong>권고 결정</strong><ol>{actions.slice(0, 4).map((item, index) => <li key={`${index}-${text(item, 'action')}`}>{text(item, 'action')}</li>)}</ol></section>
          <h3>2. 알림 및 대상 개요</h3>
          <dl className="report-cover-grid compact">
            <div><dt>카드 ID</dt><dd>{text(metadata, 'source_card_id')}</dd></div><div><dt>분석 구간</dt><dd>{text(asset, 'window_start')} ~ {text(asset, 'window_end')}</dd></div>
            <div><dt>건물/기계실</dt><dd>{buildingName} / {machineRoom}</dd></div><div><dt>대상 계통</dt><dd>{text(asset, 'configuration_type')}</dd></div>
            <div><dt>운전 상태</dt><dd>{text(situation, 'current_status')}</dd></div><div><dt>고객 영향</dt><dd>{text(situation, 'impact_summary')}</dd></div>
          </dl>
          <h3>3. 운전 데이터 분석</h3>
          <table><thead><tr><th>측정 항목</th><th>현재값</th><th>데이터 상태</th><th>판정</th></tr></thead><tbody>{sensorLabels.map((label) => { const item = measurementFor(label); return <tr key={label}><td>{label}</td><td>{text(item ?? {}, 'current_value', text(item ?? {}, 'value'))}</td><td>{text(item ?? {}, 'data_status', item ? '확인됨' : '원자료 없음')}</td><td>{text(item ?? {}, 'judgement', text(item ?? {}, 'interpretation', '확인 필요'))}</td></tr> })}</tbody></table>
        </article>

        <article className="report-docx-page">
          <h3>4. 모델 판단 및 불일치 분석</h3>
          <table><thead><tr><th>판단 계층</th><th>산출값</th><th>판정</th><th>기여 근거</th></tr></thead><tbody>{modelRows.map((row) => <tr key={row[0]}>{row.map((cell, index) => <td key={index}>{cell}</td>)}</tr>)}</tbody></table>
          <section className="report-callout"><strong>모델 불일치 해석</strong><p>{text(evidenceFor(evidence, '불일치') ?? {}, 'interpretation', text(priority, 'priority_reason'))}</p></section>
        </article>

        <article className="report-docx-page">
          <h3>5. 판정과 후속 조치</h3>
          <table><thead><tr><th>구분</th><th>후속 조치</th><th>기한/책임자</th></tr></thead><tbody>{actions.slice(0, 5).map((item, index) => <tr key={`${index}-${text(item, 'action')}`}><td>{index === 0 ? '현장 확인' : '후속 검토'}</td><td>{text(item, 'action')}</td><td>{text(item, 'urgency')} / {text(item, 'owner_hint')}</td></tr>)}</tbody></table>
        </article>
      </div>
    </div>
  </div>
}
