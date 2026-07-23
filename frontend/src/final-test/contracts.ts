export interface FinalTestDemoPackageSummary {
  readonly demo_id: string
  readonly alert_id: string
  readonly substation_id: number
  readonly facility_name: string
  readonly fault_label: string
}

export interface FinalTestSensor {
  readonly key: string
  readonly label: string
  readonly value: number
  readonly unit: string
  readonly status: 'normal' | 'warning' | 'critical'
}

export interface FinalTestPriority {
  readonly level: string
  readonly score: number
  readonly rank: number | null
  readonly reason: string
}

export interface FinalTestSnapshot {
  readonly state: 'normal' | 'fault'
  readonly captured_at: string
  readonly sensors: readonly FinalTestSensor[]
  readonly priority: FinalTestPriority
}

export interface FinalTestDocument {
  readonly document_id: string
  readonly document_type: string
  readonly title: string
  readonly status: string
  readonly header?: Readonly<Record<string, string>>
  readonly summary?: string
  readonly executive_summary?: string
  readonly risk?: readonly string[]
  readonly safety?: readonly string[]
  readonly steps?: readonly { readonly order: number; readonly title: string; readonly detail: string }[]
  readonly completion_criteria?: readonly string[]
  readonly sections?: readonly { readonly heading: string; readonly body: string }[]
  readonly conclusion?: string
  readonly approval?: Readonly<Record<string, string>>
}

export interface FinalTestDocumentVersion {
  readonly version: number
  readonly change_summary: string
  readonly document: FinalTestDocument
}

export type FinalTestDocumentType = 'work_order' | 'report'

export interface FinalTestChatAction {
  readonly type: 'preview_document_version'
  readonly document_type: FinalTestDocumentType
  readonly source_version: number
  readonly target_version: number
  readonly confirmation_message: string
  readonly applied_response: string
  readonly cancelled_response: string
}

export interface FinalTestChatRule {
  readonly intent?: string
  readonly category?: string
  readonly patterns: readonly string[]
  readonly response: string
  readonly action?: FinalTestChatAction
}

export interface FinalTestChatScript {
  readonly greeting: string
  readonly suggested_prompts: readonly string[]
  readonly responses: readonly FinalTestChatRule[]
  readonly guardrails: readonly FinalTestChatRule[]
  readonly fallback_response: string
}

export interface FinalTestDemoPackage extends FinalTestDemoPackageSummary {
  readonly scenario_id: string
  readonly normal_payload: FinalTestSnapshot
  readonly fault_payload: FinalTestSnapshot
  readonly work_order_document: FinalTestDocument
  readonly report_document: FinalTestDocument
  readonly work_order_versions: readonly FinalTestDocumentVersion[]
  readonly report_versions: readonly FinalTestDocumentVersion[]
  readonly chat_script: FinalTestChatScript
}

export interface FinalTestDemoPackagePage {
  readonly items: readonly FinalTestDemoPackageSummary[]
}

export interface FinalTestChatHistoryItem {
  readonly role: 'operator' | 'assistant'
  readonly content: string
}

export interface FinalTestChatRequest {
  readonly message: string
  readonly document_type: FinalTestDocumentType
  readonly current_version: number
  readonly history: readonly FinalTestChatHistoryItem[]
}

export interface FinalTestChatResponse {
  readonly answer: string
}
