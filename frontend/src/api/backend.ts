/**
 * API 소스 스위치. USE_MOCK이면 mock, 아니면 real client.
 * 훅/화면은 항상 여기서 import한다(계약 표면 단일 진입점).
 */

import { USE_MOCK } from './config'
import * as real from './client'
import * as mock from './mockApi'

export const alertsApi = USE_MOCK ? mock.alertsApi : real.alertsApi
export const agentRunsApi = USE_MOCK ? mock.agentRunsApi : real.agentRunsApi
export const healthApi = USE_MOCK ? mock.healthApi : real.healthApi
// /cards는 계약 밖 enrichment 전용(mock 없음). mock 모드에선 훅에서 호출 자체를 끈다.
export const cardsApi = real.cardsApi
export const subscribeSse = USE_MOCK ? mock.subscribeSse : real.subscribeSse
export const alertEventsPath = real.alertEventsPath
export const agentRunEventsPath = real.agentRunEventsPath
