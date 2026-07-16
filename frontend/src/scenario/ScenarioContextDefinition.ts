import { createContext } from 'react'
import type { EntryMode, EvaluationCategory, ScenarioAiEntry, ScenarioState, ScenarioTimelineAlert } from './types'
import type { useSensorStream } from './useSensorStream'

export interface ScenarioContextValue {
  readonly state: ScenarioState
  readonly sensor: ReturnType<typeof useSensorStream>
  readonly alerts: readonly ScenarioTimelineAlert[]
  readonly alertHistory: readonly ScenarioTimelineAlert[]
  readonly selectMode: (mode: EntryMode) => void
  readonly backToModeSelection: () => void
  readonly startFaultScenario: () => void
  readonly restartScenario: () => void
  readonly exitConsole: () => void
  readonly selectAlert: (alertId: string) => void
  readonly startAnalysis: () => void
  readonly completeAnalysis: () => void
  readonly dismissAnalysisToast: () => void
  readonly dismissIncidentPopup: () => void
  readonly setAiEntry: (entry: ScenarioAiEntry) => void
  readonly createWorkOrder: () => void
  readonly acceptWorkOrder: (version: 1 | 2 | 3) => void
  readonly createReportDraft: () => void
  readonly issueReport: () => void
  readonly postChatMessage: (content: string) => void
  readonly confirmProposal: () => void
  readonly cancelProposal: () => void
  readonly submitEvaluation: (category: EvaluationCategory) => void
}

export const ScenarioContext = createContext<ScenarioContextValue | null>(null)
