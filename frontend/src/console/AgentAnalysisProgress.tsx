import { ANALYSIS_PHASES } from './agentAnalysisProgressState'
import { Button } from './ui'

interface Props {
  readonly onOpen?: () => void
  readonly phase: number
}

export function AgentAnalysisProgress({ onOpen, phase }: Props) {
  return <aside aria-live="polite" className="scenario-analysis-progress" role="status">
    <strong>{ANALYSIS_PHASES[Math.min(phase, ANALYSIS_PHASES.length - 1)]}</strong>
    <ol>{ANALYSIS_PHASES.map((label, index) => <li className={index < phase ? 'complete' : index === phase ? 'active' : ''} key={label}><span>{index + 1}</span>{label}</li>)}</ol>
    <p>분석은 보통 1분 내외 걸립니다. AI 조치 화면으로 이동해도 서버에서 계속 진행됩니다.</p>
    {onOpen && <Button icon="arrow" onClick={onOpen} tone="primary">AI 조치에서 진행 보기</Button>}
  </aside>
}
