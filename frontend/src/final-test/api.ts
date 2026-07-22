import { apiFetch } from '../api/client'
import type { FinalTestDemoPackage, FinalTestDemoPackagePage } from './contracts'

export const finalTestDemoApi = {
  list: () => apiFetch<FinalTestDemoPackagePage>('/final-test/packages'),
  get: (demoId: string) => apiFetch<FinalTestDemoPackage>(`/final-test/packages/${encodeURIComponent(demoId)}`),
}
