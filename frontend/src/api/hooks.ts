/** 계약 소비 훅 (TanStack Query). alertsApi/agentRunsApi/healthApi는 backend.ts 스위치. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentRunsApi, alertsApi, cardsApi, healthApi } from './backend'
import { USE_MOCK } from './config'
import type { AlertListQuery } from './contracts'

export const qk = {
  alerts: (q?: AlertListQuery) => ['alerts', q?.status ?? 'open', q?.priority_level ?? 'all'] as const,
  artifacts: (id: string) => ['artifacts', id] as const,
  result: (id: string) => ['agent-run-result', id] as const,
  health: ['health'] as const,
}

export function useAlerts(query?: AlertListQuery) {
  return useQuery({ queryKey: qk.alerts(query), queryFn: () => alertsApi.list(query) })
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => healthApi.get(), refetchInterval: 15000 })
}

/**
 * card_id → substation_id 매핑(계약 밖 읽기전용 /cards). mock 모드에선 비활성.
 * 건물명 enrichment와 지도 모델-tier 산출이 공유한다.
 */
export function useCardSubstationMap() {
  return useQuery({
    queryKey: ['cards-substation-map'],
    queryFn: async () => {
      const rows = await cardsApi.list()
      const map = new Map<string, number>()
      for (const row of rows) {
        if (row.substation_id != null) map.set(row.card_id, row.substation_id)
      }
      return map
    },
    enabled: !USE_MOCK,
    staleTime: 5 * 60_000,
    retry: false,
  })
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

export function useAgentRunResult(runId: string | null) {
  return useQuery({
    queryKey: qk.result(runId ?? ''),
    queryFn: () => {
      if (runId == null) throw new Error('run_id가 없습니다.')
      return agentRunsApi.result(runId)
    },
    enabled: runId != null,
  })
}
