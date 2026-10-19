import savedReport from './saved-report.json'

export const demoData = {
  equipment: '가락마을13단지대광로제비앙아파트',
  equipmentId: '13',
  report: savedReport,
  source: 'output/ops_agent/cases/pump_failure_urgent_with_rag.json',
  repository: 'https://github.com/jiyang-lee/Heat_Grid_Agent/blob/51d680d55cce6dfdce72be001cd451aba19d00c0/output/ops_agent/cases/pump_failure_urgent_with_rag.json',
} as const

export type DemoPage = 'equipment' | 'alert' | 'evidence' | 'report'
export function readDemoPage(): DemoPage {
  switch (window.location.hash) {
    case '#alert': return 'alert'
    case '#evidence': return 'evidence'
    case '#report': return 'report'
    default: return 'equipment'
  }
}
