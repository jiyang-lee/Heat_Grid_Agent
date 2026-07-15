import { Icon } from '../console/icons'
import { useScenario } from './useScenario'

const upcomingScenarios = [
  { title: '공급온도 과열 및 열원설비 이상', description: '공급 계통 과열과 열원 설비 보호 운전 시나리오', icon: 'thermometer' as const },
  { title: '유량 급감 및 배관 누수', description: '유량 급감과 배관 누수 의심 상황 대응 시나리오', icon: 'flow' as const },
] as const

export function EntryGate() {
  const { state, selectMode, backToModeSelection, startFaultScenario } = useScenario()
  const choosingScenario = state.entryStep === 'scenario-selection'

  return (
    <main className="entry-gate">
      <div className="entry-gate-orb entry-gate-orb-one" />
      <div className="entry-gate-orb entry-gate-orb-two" />
      <section className="entry-panel" aria-labelledby="entry-title">
        <header className="entry-brand">
          <span className="entry-brand-mark"><Icon name="droplet" fill="currentColor" strokeWidth={0} /></span>
          <div><strong>HeatGrid</strong><span>AIoT 지역난방 운영 콘솔</span></div>
        </header>

        <div className="entry-heading">
          {choosingScenario && <button className="entry-back" onClick={backToModeSelection} type="button"><Icon name="arrow" />버전 선택으로 돌아가기</button>}
          <span className="entry-eyebrow">OPERATION EXPERIENCE</span>
          <h1 id="entry-title">{choosingScenario ? '고장 대응 시나리오를 선택하세요' : '운영 환경을 선택하세요'}</h1>
          <p>{choosingScenario ? '사고 감지부터 AI 조치와 사용자 평가까지 한 흐름으로 실행합니다.' : '정상 운영 현황을 확인하거나 고장 대응 시나리오를 시작할 수 있습니다.'}</p>
        </div>

        {!choosingScenario && (
          <div className="entry-mode-grid">
            <button className="entry-mode-card normal" onClick={() => selectMode('normal')} type="button">
              <span className="entry-card-icon"><Icon name="shield" /></span>
              <span className="entry-card-status success"><i />정상 운영</span>
              <strong>정상 버전 보기</strong>
              <span>정상 센서 구간과 현재 운영 현황을 확인합니다.</span>
              <b>정상 대시보드 시작 <Icon name="arrow" /></b>
            </button>
            <button className="entry-mode-card fault" onClick={() => selectMode('fault')} type="button">
              <span className="entry-card-icon"><Icon name="alert" /></span>
              <span className="entry-card-status critical"><i />고장 대응</span>
              <strong>고장 버전 보기</strong>
              <span>센서 이상과 AI 조치·재실행 흐름을 체험합니다.</span>
              <b>고장 시나리오 선택 <Icon name="arrow" /></b>
            </button>
          </div>
        )}

        {choosingScenario && (
          <div className="scenario-card-grid">
            <button className="scenario-select-card active" onClick={startFaultScenario} type="button">
              <div className="scenario-card-top"><span className="entry-card-icon"><Icon name="thermometer" /></span><span className="entry-card-status critical"><i />실행 가능</span></div>
              <strong>환수온도 이상 및 동시다발 설비 고장</strong>
              <p>2020년 1월 13일 15시, 환수온도 급락과 설비 고장 3건이 동시에 감지됩니다.</p>
              <dl><div><dt>최고 우선순위</dt><dd>urgent</dd></div><div><dt>최단 리드타임</dt><dd>4.9시간</dd></div><div><dt>동시 경보</dt><dd>3건</dd></div></dl>
              <span className="scenario-tags"><i>환수온도</i><i>순환펌프</i><i>열교환기</i></span>
              <b>시나리오 시작 <Icon name="arrow" /></b>
            </button>
            {upcomingScenarios.map((scenario) => (
              <article className="scenario-select-card upcoming" key={scenario.title} aria-disabled="true">
                <div className="scenario-card-top"><span className="entry-card-icon"><Icon name={scenario.icon} /></span><span className="entry-card-status neutral">준비 중</span></div>
                <strong>{scenario.title}</strong><p>{scenario.description}</p><small>향후 시나리오 데이터 검증 후 제공됩니다.</small>
              </article>
            ))}
          </div>
        )}
        <footer className="entry-footer"><span><Icon name="info" />시나리오 데이터는 교육·검증용이며 실제 안전 판단을 대체하지 않습니다.</span><b>운영 시작 2020.01.01</b></footer>
      </section>
    </main>
  )
}
