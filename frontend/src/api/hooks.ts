/** 계약 소비 훅 (TanStack Query). alertsApi/agentRunsApi/healthApi는 backend.ts 스위치. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentRunsApi, alertsApi, healthApi } from './backend'
import type { AlertListQuery } from './contracts'

export const qk = {
  alerts: (q?: AlertListQuery) => ['alerts', q?.status ?? 'open', q?.priority_level ?? 'all'] as const,
  artifacts: (id: string) => ['artifacts', id] as const,
  health: ['health'] as const,
}

export function useAlerts(query?: AlertListQuery) {
  return useQuery({ queryKey: qk.alerts(query), queryFn: () => alertsApi.list(query) })
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => healthApi.get(), refetchInterval: 15000 })
}

export function useAckAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { alertId: string; ackedBy?: string }) =>
      alertsApi.ack(v.alertId, { acked_by: v.ackedBy ?? 'operator' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useResolveAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { alertId: string; ackedBy?: string }) =>
      alertsApi.resolve(v.alertId, { acked_by: v.ackedBy ?? 'operator' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useCreateAgentRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { alertId: string }) => agentRunsApi.create({ alert_id: v.alertId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useArtifacts(runId: string | null) {
  return useQuery({
    queryKey: qk.artifacts(runId ?? ''),
    queryFn: () => agentRunsApi.artifacts(runId as string),
    enabled: runId != null,
  })
}
