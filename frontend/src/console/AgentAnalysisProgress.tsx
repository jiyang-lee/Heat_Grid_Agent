import { ANALYSIS_PHASES } from './agentAnalysisProgressState'

export function AgentAnalysisProgress({ phase }: { readonly phase: number }) {
  return <aside aria-live="polite" className="scenario-analysis-progress" role="status">
    <strong>{ANALYSIS_PHASES[Math.min(phase, ANALYSIS_PHASES.length - 1)]}</strong>
    <ol>{ANALYSIS_PHASES.map((label, index) => <li className={index < phase ? 'complete' : index === phase ? 'active' : ''} key={label}><span>{index + 1}</span>{label}</li>)}</ol>
  </aside>
}
