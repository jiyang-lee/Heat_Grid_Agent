import { apiFetch } from '../api/client'
import type { FinalTestChatRequest, FinalTestChatResponse, FinalTestDemoPackage, FinalTestDemoPackagePage } from './contracts'

export const finalTestDemoApi = {
  list: () => apiFetch<FinalTestDemoPackagePage>('/final-test/packages'),
  get: (demoId: string) => apiFetch<FinalTestDemoPackage>(`/final-test/packages/${encodeURIComponent(demoId)}`),
  chat: (demoId: string, body: FinalTestChatRequest) => apiFetch<FinalTestChatResponse>(
    `/final-test/packages/${encodeURIComponent(demoId)}/chat`,
    { method: 'POST', body: JSON.stringify(body) },
  ),
}
