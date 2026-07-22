import { useState } from 'react'
import { Icon } from '../console/icons'
import { ApiState } from '../console/ui'
import { FinalTestDocumentView } from './FinalTestDocument'
import { FinalTestProjectChat } from './FinalTestProjectChat'
import { useFinalTestPackage } from './hooks'
import './final-test.css'

type DocumentTab = 'work-order' | 'report'
type SplitRatio = '60-40' | '50-50' | '40-60'
type MobileSurface = 'document' | 'chat'

interface Props {
  readonly demoId: string
}

export function FinalTestDemoWorkspace({ demoId }: Props) {
  const demo = useFinalTestPackage(demoId)
  const [tab, setTab] = useState<DocumentTab>('work-order')
  const [ratio, setRatio] = useState<SplitRatio>('60-40')
  const [mobileSurface, setMobileSurface] = useState<MobileSurface>('document')

  if (demo.isLoading || demo.isError || !demo.data) {
    return <div className="final-test-state"><ApiState empty={false} error={demo.isError} loading={demo.isLoading} retry={() => void demo.refetch()} /></div>
  }

  const pkg = demo.data
  const document = tab === 'work-order' ? pkg.work_order_document : pkg.report_document
  return <div className="final-test-page">
    <header className="final-test-toolbar">
      <div><span>FINAL TEST · {pkg.demo_id}</span><h1>{pkg.facility_name}</h1><p>{pkg.fault_label}</p></div>
      <div className="final-test-db-status"><Icon name="check" /><span><strong>DB 사전 적재본</strong>계산·생성 없이 1:1 조회</span></div>
    </header>
    <section className="final-test-snapshot-strip" aria-label="고장 전후 동일 묶음 데이터">
      <div><span>고장 전</span><strong>{pkg.normal_payload.priority.reason}</strong><small>{pkg.normal_payload.captured_at}</small></div>
      <Icon name="arrow" />
      <div className="fault"><span>고장 감지</span><strong>{pkg.fault_payload.priority.score.toFixed(1)}점 · 우선순위 {pkg.fault_payload.priority.rank}</strong><small>{pkg.fault_payload.captured_at}</small></div>
      {pkg.fault_payload.sensors.map((sensor) => <div className={`sensor ${sensor.status}`} key={sensor.key}><span>{sensor.label}</span><strong>{sensor.value}{sensor.unit}</strong></div>)}
    </section>
    <div className="final-test-controls">
      <div role="tablist" aria-label="시연 문서">{([['work-order', '작업지시서'], ['report', '보고서']] as const).map(([key, label]) => <button aria-selected={tab === key} className={tab === key ? 'active' : ''} key={key} onClick={() => setTab(key)} role="tab" type="button"><Icon name="document" />{label}</button>)}</div>
      <div className="final-test-ratio" aria-label="문서와 챗봇 비율"><span>화면 비율</span>{(['60-40', '50-50', '40-60'] as const).map((value) => <button aria-pressed={ratio === value} key={value} onClick={() => setRatio(value)} type="button">{value.replace('-', ':')}</button>)}</div>
      <div className="final-test-mobile-switch" aria-label="모바일 화면 선택">
        <button aria-pressed={mobileSurface === 'document'} onClick={() => setMobileSurface('document')} type="button">문서 보기</button>
        <button aria-pressed={mobileSurface === 'chat'} onClick={() => setMobileSurface('chat')} type="button">챗봇 보기</button>
      </div>
    </div>
    <div className={`final-test-split ratio-${ratio} mobile-${mobileSurface}`}>
      <section className="final-test-preview"><div className="final-test-panel-title"><span><Icon name="document" />문서 미리보기</span><small>{document.document_id}</small></div><div className="final-test-preview-scroll"><FinalTestDocumentView document={document} /></div></section>
      <FinalTestProjectChat script={pkg.chat_script} />
    </div>
  </div>
}
