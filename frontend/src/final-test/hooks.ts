import { useQuery } from '@tanstack/react-query'
import { finalTestDemoApi } from './api'

export function useFinalTestPackages(enabled = true) {
  return useQuery({
    queryKey: ['final-test-packages'],
    queryFn: finalTestDemoApi.list,
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useFinalTestPackage(demoId: string, enabled = true) {
  return useQuery({
    queryKey: ['final-test-package', demoId],
    queryFn: () => finalTestDemoApi.get(demoId),
    enabled: enabled && demoId !== '',
    staleTime: Number.POSITIVE_INFINITY,
  })
}
