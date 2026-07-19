import { useState } from 'react'
import { StatusBadge } from '../console/ui'
import { ScenarioActionPlan } from './ScenarioActionPlan'
import { ScenarioAiOverview } from './ScenarioAiOverview'
import { ScenarioReportWorkspace } from './ScenarioReportWorkspace'
import { ScenarioWorkOrderWorkspace } from './ScenarioWorkOrderWorkspace'
import { useScenario } from './useScenario'

const tabs = ['계획서', '작업지시서', '보고서'] as const
type Tab = (typeof tabs)[number]

export function ScenarioAiPage() {
  const scenario = useScenario()
  const { alerts, state, createReportDraft, createWorkOrder, selectAlert, setAiEntry, acceptWorkOrder } = scenario
  const [tab, setTab] = useState<Tab>('계획서')
  const latestOrder = state.workOrders.at(-1)
  const acceptedOrder = state.workOrders.find((order) => order.version === state.acceptedWorkOrderVersion)
  const alert = alerts.find((item) => item.id === state.selectedAlertId) ?? alerts[0]
  if (!alert) return null

  const generateOrder = () => {
    createWorkOrder()
    setTab('작업지시서')
  }

  const openDetail = (alertId: string) => {
    selectAlert(alertId)
    setAiEntry('detail')
  }

  if (state.aiEntry === 'overview') return <div className="page-stack activity-page scenario-ai-page"><ScenarioAiOverview alerts={alerts} onSelect={openDetail} reportStatus={state.report.status} workOrders={state.workOrders} /></div>

  return <div className="page-stack activity-page scenario-ai-page">
    <header className="scenario-ai-heading"><button className="text-link" onClick={() => setAiEntry('overview')} type="button">조치 계획 목록</button><StatusBadge tone={alert.priority === 'urgent' ? 'critical' : 'warning'}>{alert.priority} · {alert.leadTimeHours}시간 이내</StatusBadge></header>
    <div className="activity-tabs" role="tablist">{tabs.map((item) => <button aria-selected={tab === item} className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)} role="tab" type="button">{item}</button>)}</div>

    {tab === '계획서' && <ScenarioActionPlan alert={alert} onCreateOrder={generateOrder} order={latestOrder} reportStatus={state.report.status} />}
    {tab === '작업지시서' && <ScenarioWorkOrderWorkspace alert={alert} runId={state.workOrders.at(-1)?.sourceRunId ?? null} onAccept={acceptWorkOrder} onAppendMessages={scenario.appendWorkOrderMessages} onAppendRevision={scenario.appendWorkOrderRevision} onCreateReport={() => { createReportDraft(); setTab('보고서') }} onSelectVersion={scenario.selectWorkOrderVersion} onUpdateContent={scenario.updateWorkOrderContent} state={state} />}
    {tab === '보고서' && <ScenarioReportWorkspace alert={alert} runId={null} messages={state.reportMessages} onComplete={scenario.completeReport} onCreateDraft={createReportDraft} onPostMessage={scenario.postReportMessage} onSave={scenario.saveReportDraft} order={acceptedOrder} report={state.report} />}
  </div>
}
