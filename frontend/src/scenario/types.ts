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

export type ScenarioAlertStatus = 'active' | 'expired' | 'resolved'

export interface ScenarioTimelineAlert extends ScenarioAlert {
  readonly status: ScenarioAlertStatus
  readonly resolvedAt: string | null
}

export type ScenarioAnalysisState = 'idle' | 'running' | 'complete'

export type ScenarioIncidentState = 'monitoring' | 'incident-active'

export type ScenarioReportStatus = 'idle' | 'draft' | 'completed'

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
  readonly content: string
  readonly sourceRunId: string | null
  readonly revisionInstruction: string | null
  readonly baseVersion: 1 | 2 | 3 | null
}

export interface WorkOrderSection {
  readonly title: string
  readonly items: readonly string[]
}

export interface ScenarioReport {
  readonly status: ScenarioReportStatus
  readonly createdAt: string | null
  readonly savedAt: string | null
  readonly completedAt: string | null
  readonly content: string
}

export interface ScenarioReportMessage {
  readonly id: string
  readonly role: 'operator' | 'assistant'
  readonly content: string
  readonly createdAt: string
}

export type EvaluationCategory = 'model' | 'external-data' | 'rag' | 'work-order'

export interface ImprovementCandidate {
  readonly category: EvaluationCategory
  readonly label: string
  readonly status: 'approval-pending'
  readonly createdAt: string
}

export interface ScenarioDocumentGroup {
  readonly id: string
  readonly rootRunId: string
  readonly alertId: string
  readonly substationId: number
  readonly createdAt: string
  readonly workOrders: readonly WorkOrderVersion[]
  readonly selectedWorkOrderVersion: 1 | 2 | 3 | null
  readonly acceptedWorkOrderVersion: 1 | 2 | 3 | null
  readonly workOrderRerunCount: number
  readonly messages: readonly ScenarioChatMessage[]
  readonly proposal: ChatProposal | null
  readonly evaluationRequired: boolean
  readonly improvementCandidate: ImprovementCandidate | null
  readonly report: ScenarioReport
  readonly reportMessages: readonly ScenarioReportMessage[]
}

export interface ScenarioState {
  readonly entryStep: EntryStep
  readonly mode: EntryMode | null
  readonly scenarioId: string | null
  readonly selectedAlertId: string
  readonly selectedSubstationId: number
  readonly incidentState: ScenarioIncidentState
  readonly analysisState: ScenarioAnalysisState
  readonly analysisAlertId: string | null
  readonly analyzedAlertIds: readonly string[]
  readonly analysisToastVisible: boolean
  readonly incidentPopupVisible: boolean
  readonly dismissedIncidentAlertIds: readonly string[]
  readonly resolvedAlertTimes: Readonly<Record<string, string>>
  readonly alertSensorSnapshots: Readonly<Record<string, readonly SensorPoint[]>>
  readonly aiEntry: ScenarioAiEntry
  readonly documentGroups: readonly ScenarioDocumentGroup[]
  readonly activeDocumentGroupId: string | null
  readonly documentAlertId: string | null
  readonly workOrders: readonly WorkOrderVersion[]
  readonly selectedWorkOrderVersion: 1 | 2 | 3 | null
  readonly acceptedWorkOrderVersion: 1 | 2 | 3 | null
  readonly workOrderRerunCount: number
  readonly messages: readonly ScenarioChatMessage[]
  readonly proposal: ChatProposal | null
  readonly evaluationRequired: boolean
  readonly improvementCandidate: ImprovementCandidate | null
  readonly report: ScenarioReport
  readonly reportMessages: readonly ScenarioReportMessage[]
}
