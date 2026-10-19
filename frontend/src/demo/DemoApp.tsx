import { useEffect, useState } from 'react'
import mark from '../assets/brand/heatgrid-mark.webp'
import { demoData, readDemoPage, type DemoPage } from './provider'
import './demo.css'

const pages: readonly { readonly id: DemoPage; readonly label: string }[] = [
  { id: 'equipment', label: '설비' }, { id: 'alert', label: '알림' },
  { id: 'evidence', label: '판단 근거' }, { id: 'report', label: '저장된 보고서' },
]

export function DemoApp() {
  const [page, setPage] = useState(readDemoPage)
  const [normal, setNormal] = useState(false)
  useEffect(() => {
    const update = () => setPage(readDemoPage())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const reset = () => { setNormal(false); window.location.hash = 'equipment'; setPage('equipment') }
  const report = demoData.report
  return <div className="demo-app">
    <header className="demo-header"><a className="demo-brand" href="#equipment"><img alt="" src={mark} width="44" height="44" /><strong>HeatGrid</strong><span>운영 콘솔 체험</span></a><button onClick={reset} type="button"><svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8"><path d="M21 12a9 9 0 1 1-2.9-6.6M21 3v6h-6" /></svg>체험 초기화</button></header>
    <aside className="demo-banner" aria-label="체험 모드 안내"><strong>샘플 데이터와 저장된 실행 결과를 사용하는 체험 모드</strong><span>실시간 센서 조회 · 새 AI 실행 · 현장 제어는 수행하지 않습니다.</span></aside>
    <main className="demo-main">
      <div className="demo-intro"><div><p className="demo-eyebrow">PUBLIC SAMPLE / OFFLINE REPLAY</p><h1>설비에서 판단 근거까지</h1><p>공개 저장소의 샘플 사례로 HeatGrid의 점검 흐름을 살펴보세요.</p></div><div className="demo-scenarios" aria-label="시나리오"><button aria-pressed={!normal} onClick={() => setNormal(false)} type="button">고장 사례</button><button aria-pressed={normal} onClick={() => setNormal(true)} type="button">정상 상태</button></div></div>
      <nav className="demo-steps" aria-label="체험 단계">{pages.map((item, index) => <a aria-current={page === item.id ? 'step' : undefined} href={`#${item.id}`} key={item.id}><span>{index + 1}</span>{item.label}</a>)}</nav>
      {normal ? <section className="ops-surface demo-panel"><span className="demo-status normal">정상 상태 화면 예시</span><h2>열린 알림이 없습니다</h2><p>정상 상태의 빈 화면을 체험합니다. 이 화면은 실측 데이터나 저장된 정상 판정 결과가 아닙니다.</p><button onClick={() => setNormal(false)} type="button">고장 사례 살펴보기</button></section> : <>
        {page === 'equipment' && <section className="demo-grid"><article className="ops-surface demo-panel"><p className="demo-eyebrow">열수급 지점 {demoData.equipmentId}</p><h2 className="demo-equipment-name"><span>가락마을13단지</span><span>대광로제비앙아파트</span></h2><span className="demo-status">긴급 · 저장된 사례</span><p>의심 유형: 순환펌프 고장</p><p>공개된 저장 보고서에서 선택한 설비입니다. 현장 위치나 최신 운전 상태를 조회하지 않습니다.</p><a className="demo-primary" href="#alert">연결된 알림 확인 →</a></article><article className="ops-surface demo-panel"><h2>열공급 연결 개요</h2><div className="demo-network" aria-label="열원에서 열수급 지점 13을 거쳐 순환펌프로 이어지는 개념도"><span>열원</span><i /><span>열수급 지점 13</span><i /><span>순환펌프</span></div><p>개념도 · 실제 지도 및 배관 위치가 아닙니다.</p></article></section>}
        {page === 'alert' && <section className="ops-surface demo-panel"><p className="demo-eyebrow">SAVED CASE / PUMP FAILURE</p><h2>순환펌프 고장 의심</h2><span className="demo-status">긴급</span><p>{report.summary}</p><p>원본 우선순위 점수: <strong>{report.evidence.priority_score}</strong> (저장된 값)</p><a className="demo-primary" href="#evidence">판단 근거 확인 →</a></section>}
        {page === 'evidence' && <section className="ops-surface demo-panel"><h2>저장된 판단 근거</h2><p>아래 내용은 기존 실행 산출물의 evidence 필드입니다.</p><ul>{report.evidence.main_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul><h3>기존 실행에서 사용한 도구</h3><div className="demo-tags">{report.evidence.used_tools.map((tool) => <code key={tool}>{tool}</code>)}</div><p>체험 중에는 이 도구를 호출하지 않습니다.</p><a className="demo-primary" href="#report">저장된 에이전트 보고서 열기 →</a></section>}
        {page === 'report' && <section className="ops-surface demo-panel"><p className="demo-eyebrow">SAVED AGENT OUTPUT / 재실행 없음</p><h2>순환펌프 점검 보고서</h2><p>{report.summary}</p><h3>기존 실행의 조치 제안</h3><ol>{report.action_plan.map((action) => <li key={action}>{action}</li>)}</ol><h3>기존 실행의 주의 사항</h3><ul>{report.caution.map((item) => <li key={item}>{item}</li>)}</ul><details><summary>출처 및 원본 JSON</summary><p>출처: <a href={demoData.repository} target="_blank" rel="noreferrer">공개 Heat_Grid_Agent 저장소 원본 (고정 커밋)</a> / {demoData.source}</p><pre>{JSON.stringify(report, null, 2)}</pre></details><p className="demo-footnote">기존 샘플 산출물을 그대로 보여줍니다. 현재 현장에 대한 판단이나 작업 승인을 의미하지 않습니다.</p></section>}
      </>}
      <footer className="demo-footer">HeatGrid 공개 샘플 · 데이터와 보고서는 브라우저에 포함되어 있습니다. <a href="https://jiyang-lee.github.io/#/projects/heatgrid-agent" rel="noreferrer" target="_blank">프로젝트 소개 보기</a></footer>
    </main>
  </div>
}
