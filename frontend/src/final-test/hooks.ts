import { useQuery } from '@tanstack/react-query'
import { finalTestDemoApi } from './api'

export function useFinalTestPackages() {
  return useQuery({
    queryKey: ['final-test-packages'],
    queryFn: finalTestDemoApi.list,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useFinalTestPackage(demoId: string) {
  return useQuery({
    queryKey: ['final-test-package', demoId],
    queryFn: () => finalTestDemoApi.get(demoId),
    staleTime: Number.POSITIVE_INFINITY,
  })
}
