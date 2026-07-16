export type EntryMode = 'normal' | 'fault'

export type EntryStep = 'mode-selection' | 'scenario-selection' | 'console'

export type SensorStreamStatus = 'connecting' | 'live' | 'reconnecting' | 'offline' | 'fallback' | 'paused'

export type SensorStreamSource = 'backend-replay' | 'scenario-fallback'

export type SensorMetric = 'supply' | 'returnTemperature' | 'flow'

export interface SensorPoint {
  readonly at: string
  readonly supply: number
  readonly returnTemperature: number
  readonly flow: number
  readonly quality: string
  readonly sequence: number
}

export interface SensorStreamState {
  readonly status: SensorStreamStatus
  readonly source: SensorStreamSource
  readonly points: readonly SensorPoint[]
  readonly simulatedAt: string
  readonly receivedAt: string | null
  readonly nextReceiveSeconds: number
  readonly paused: boolean
  readonly speed: number
  readonly substationId: number
  readonly connectionMessage: string
}

export type ScenarioPriority = 'urgent' | 'high'

export interface ScenarioAlert {
  readonly id: string
  readonly title: string
  readonly facility: string
  readonly substationId: number
  readonly priority: ScenarioPriority
  readonly affectedMetric: SensorMetric
  readonly leadTimeHours: number
  readonly temperatureDelta: number
  readonly summary: string
  readonly evidence: readonly string[]
  readonly detectedAt: string
}

export type ScenarioAlertStatus = 'active' | 'resolved'

export interface ScenarioTimelineAlert extends ScenarioAlert {
  readonly status: ScenarioAlertStatus
  readonly resolvedAt: string | null
}

export type ScenarioAnalysisState = 'idle' | 'running' | 'complete'

export type ScenarioIncidentState = 'monitoring' | 'incident-active'

export type ScenarioReportStatus = 'idle' | 'draft' | 'issued'

export type ScenarioAiEntry = 'overview' | 'detail'

export type ChatTargetStage = 'ml_validation' | 'external_context' | 'rag_retrieval' | 'work_order_draft'

export interface ScenarioChatMessage {
  readonly id: string
  readonly role: 'operator' | 'assistant' | 'system'
  readonly content: string
  readonly createdAt: string
  readonly workOrderVersion: 1 | 2 | 3
}

export interface ChatProposal {
  readonly id: string
  readonly intent: string
  readonly targetStage: ChatTargetStage
  readonly targetLabel: string
  readonly changeSummary: string
  readonly source: 'review-chat-api' | 'scenario-analysis'
}

export interface WorkOrderVersion {
  readonly version: 1 | 2 | 3
  readonly createdAt: string
  readonly title: string
  readonly changeSummary: string
  readonly instructions: readonly string[]
  readonly sections: readonly WorkOrderSection[]
}

export interface WorkOrderSection {
  readonly title: string
  readonly items: readonly string[]
}

export interface ScenarioReport {
  readonly status: ScenarioReportStatus
  readonly createdAt: string | null
  readonly issuedAt: string | null
}

export type EvaluationCategory = 'model' | 'external-data' | 'rag' | 'work-order'

export interface ImprovementCandidate {
  readonly category: EvaluationCategory
  readonly label: string
  readonly status: 'approval-pending'
  readonly createdAt: string
}

export interface ScenarioState {
  readonly entryStep: EntryStep
  readonly mode: EntryMode | null
  readonly scenarioId: string | null
  readonly selectedAlertId: string
  readonly incidentState: ScenarioIncidentState
  readonly analysisState: ScenarioAnalysisState
  readonly analysisToastVisible: boolean
  readonly incidentPopupVisible: boolean
  readonly aiEntry: ScenarioAiEntry
  readonly workOrders: readonly WorkOrderVersion[]
  readonly acceptedWorkOrderVersion: 1 | 2 | 3 | null
  readonly messages: readonly ScenarioChatMessage[]
  readonly proposal: ChatProposal | null
  readonly evaluationRequired: boolean
  readonly improvementCandidate: ImprovementCandidate | null
  readonly report: ScenarioReport
}
