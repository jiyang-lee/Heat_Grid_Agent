/**
 * API 소스 스위치. USE_MOCK이면 mock, 아니면 real client.
 * 훅/화면은 항상 여기서 import한다(계약 표면 단일 진입점).
 */

import { USE_MOCK } from './config'
import * as real from './client'
import * as mock from './mockApi'

export const alertsApi = USE_MOCK ? mock.alertsApi : real.alertsApi
export const agentRunsApi = USE_MOCK ? mock.agentRunsApi : real.agentRunsApi
export const agentRunEvaluationsApi = USE_MOCK ? mock.agentRunEvaluationsApi : real.agentRunEvaluationsApi
export const operatorReviewsApi = USE_MOCK ? mock.operatorReviewsApi : real.operatorReviewsApi
export const policyCandidatesApi = USE_MOCK ? mock.policyCandidatesApi : real.policyCandidatesApi
export const operationsMetricsApi = USE_MOCK ? mock.operationsMetricsApi : real.operationsMetricsApi
export const healthApi = USE_MOCK ? mock.healthApi : real.healthApi
export const priorityEvaluationsApi = USE_MOCK ? mock.priorityEvaluationsApi : real.priorityEvaluationsApi
export const reviewTasksApi = USE_MOCK ? mock.reviewTasksApi : real.reviewTasksApi
export const evidenceCandidatesApi = USE_MOCK ? mock.evidenceCandidatesApi : real.evidenceCandidatesApi
export const trainingFeedbackApi = USE_MOCK ? mock.trainingFeedbackApi : real.trainingFeedbackApi
export const automationPolicyApi = USE_MOCK ? mock.automationPolicyApi : real.automationPolicyApi
export const retrainJobsApi = USE_MOCK ? mock.retrainJobsApi : real.retrainJobsApi
export const modelCandidatesApi = USE_MOCK ? mock.modelCandidatesApi : real.modelCandidatesApi
export const subscribeSse = USE_MOCK ? mock.subscribeSse : real.subscribeSse
export const alertEventsPath = real.alertEventsPath
export const agentRunEventsPath = real.agentRunEventsPath
