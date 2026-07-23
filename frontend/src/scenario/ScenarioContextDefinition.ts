import { createContext } from 'react'
import type { EntryMode, EvaluationCategory, ScenarioAiEntry, ScenarioState, ScenarioTimelineAlert } from './types'
import type { OpsAgentResultV4 } from '../api/contracts'
import type { useSensorStream } from './useSensorStream'
import type { WorkOrderRevisionTarget } from './workOrderRevision'

export interface ScenarioContextValue {
  readonly state: ScenarioState
  readonly sensor: ReturnType<typeof useSensorStream>
  readonly alerts: readonly ScenarioTimelineAlert[]
  readonly alertHistory: readonly ScenarioTimelineAlert[]
  readonly selectMode: (mode: EntryMode) => void
  readonly backToModeSelection: () => void
  readonly startFaultScenario: () => void
  readonly startDemoScenario: () => void
  readonly restartScenario: () => void
  readonly clearAiHistory: () => void
  readonly exitConsole: () => void
  readonly selectAlert: (alertId: string) => void
  readonly selectSubstation: (substationId: number) => void
  readonly startAnalysis: (alertId: string) => void
  readonly completeAnalysis: () => void
  readonly failAnalysis: () => void
  readonly dismissAnalysisToast: () => void
  readonly dismissIncidentAlert: (alertId: string) => void
  readonly dismissIncidentPopup: () => void
  readonly resolveAlert: (alertId: string) => void
  readonly setAiEntry: (entry: ScenarioAiEntry) => void
  readonly createWorkOrder: (runId?: string, result?: OpsAgentResultV4, alertId?: string) => void
  readonly selectDocumentGroup: (groupId: string) => void
  readonly appendWorkOrderRevision: (runId: string, result: OpsAgentResultV4, instruction: string, target: WorkOrderRevisionTarget, baseVersion: 1 | 2 | 3, documentContent?: string) => void
  readonly appendManualWorkOrderRevision: (version: 2 | 3, baseVersion: 1 | 2 | 3, title: string, content: string, instruction: string, sourceRunId: string) => void
  readonly appendWorkOrderMessages: (messages: readonly import('./types').ScenarioChatMessage[]) => void
  readonly selectWorkOrderVersion: (version: 1 | 2 | 3) => void
  readonly updateWorkOrderContent: (version: 1 | 2 | 3, content: string, title?: string) => void
  readonly acceptWorkOrder: (version: 1 | 2 | 3) => void
  readonly createReportDraft: () => void
  readonly saveReportDraft: (content: string) => void
  readonly completeReport: () => void
  readonly postReportMessage: (content: string) => void
  readonly submitEvaluation: (category: EvaluationCategory) => void
}

export const ScenarioContext = createContext<ScenarioContextValue | null>(null)
