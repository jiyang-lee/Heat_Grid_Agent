/** 계약 소비 훅 (TanStack Query). alertsApi/agentRunsApi/healthApi는 backend.ts 스위치. */

import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  agentRunsApi,
  alertsApi,
  automationPolicyApi,
  demoReplayApi,
  demoReplayEventsPath,
  evidenceCandidatesApi,
  healthApi,
  modelCandidatesApi,
  priorityEvaluationsApi,
  retrainJobsApi,
  reviewTasksApi,
  subscribeDemoReplaySse,
  trainingFeedbackApi,
} from './backend'
import type {
  AlertListQuery,
  AutomationPolicyUpdateRequest,
  DemoReplayEvent,
  DemoReplaySnapshot,
  DemoReplayStatus,
  EvidenceCandidateReviewRequest,
  ModelPromotionRequest,
  ReplaySensorTickEvent,
  RetrainJobActionRequest,
  RetrainJobCreateRequest,
  ReviewTaskSubmitRequest,
} from './contracts'

export const qk = {
  alerts: (q?: AlertListQuery) => ['alerts', q?.status ?? 'open', q?.priority_level ?? 'all'] as const,
  artifacts: (id: string) => ['artifacts', id] as const,
  run: (id: string) => ['agent-run', id] as const,
  result: (id: string) => ['agent-run-result', id] as const,
  iterations: (id: string) => ['agent-run-iterations', id] as const,
  reviews: (status: string) => ['review-tasks', status] as const,
  evidence: (status: string) => ['evidence-candidates', status] as const,
  feedback: ['training-feedback'] as const,
  policy: ['automation-policy'] as const,
  retrain: ['retrain-jobs'] as const,
  candidates: ['model-candidates'] as const,
  activeModel: ['active-model-deployment'] as const,
  health: ['health'] as const,
  prioritySnapshot: ['priority-evaluation-latest'] as const,
  replayStatus: ['demo-replay-status'] as const,
  replaySnapshot: ['demo-replay-snapshot'] as const,
}

export function useAlerts(query?: AlertListQuery) {
  return useQuery({ queryKey: qk.alerts(query), queryFn: () => alertsApi.list(query) })
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => healthApi.get(), refetchInterval: 15000 })
}

export function usePrioritySnapshot() {
  return useQuery({
    queryKey: qk.prioritySnapshot,
    queryFn: () => priorityEvaluationsApi.latest(),
    refetchInterval: 15000,
  })
}

export function useDemoReplayStatus() {
  return useQuery({
    queryKey: qk.replayStatus,
    queryFn: () => demoReplayApi.status(),
    refetchInterval: 10000,
  })
}

export function useDemoReplaySnapshot() {
  return useQuery({
    queryKey: qk.replaySnapshot,
    queryFn: () => demoReplayApi.snapshot(),
  })
}

export function useDemoReplayControl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: demoReplayApi.control,
    onSuccess: (status) => {
      qc.setQueryData(qk.replayStatus, status)
      void qc.invalidateQueries({ queryKey: qk.replaySnapshot })
    },
  })
}

function replayEvent(value: unknown): DemoReplayEvent | null {
  if (typeof value !== 'object' || value === null || !('type' in value)) return null
  const type = (value as { type?: unknown }).type
  if (type !== 'sensor_tick' && type !== 'window_scored' && type !== 'replay_state' && type !== 'error') {
    return null
  }
  return value as DemoReplayEvent
}

function withSensorTick(
  previous: DemoReplayStatus | undefined,
  event: ReplaySensorTickEvent,
): DemoReplayStatus | undefined {
  if (!previous) return previous
  return {
    ...previous,
    state: 'running',
    dataset_version: event.dataset_version,
    current_simulated_at: event.simulated_at,
    window_progress: event.window_progress,
    total_progress: event.total_progress,
    error: null,
  }
}

/** Keep raw sensor values live and refresh model-derived queries only after a scored window. */
export function useDemoReplayStream() {
  const qc = useQueryClient()

  useEffect(() => {
    return subscribeDemoReplaySse(
      demoReplayEventsPath,
      (raw) => {
        const event = replayEvent(raw)
        if (!event) return

        if (event.type === 'sensor_tick') {
          qc.setQueryData<DemoReplayStatus>(qk.replayStatus, (previous) =>
            withSensorTick(previous, event),
          )
          qc.setQueryData<DemoReplaySnapshot>(qk.replaySnapshot, (previous) => {
            const previousStatus = previous ?? qc.getQueryData<DemoReplayStatus>(qk.replayStatus)
            if (!previousStatus) return previous
            const status = withSensorTick(previousStatus, event) ?? previousStatus
            return {
              ...status,
              readings: event.readings,
            }
          })
          return
        }

        if (event.type === 'window_scored') {
          qc.setQueryData<DemoReplayStatus>(qk.replayStatus, (previous) =>
            previous ? { ...previous, has_scored_window: true } : previous,
          )
          qc.setQueryData<DemoReplaySnapshot>(qk.replaySnapshot, (previous) =>
            previous ? { ...previous, has_scored_window: true } : previous,
          )
          void qc.invalidateQueries({ queryKey: qk.prioritySnapshot })
          void qc.invalidateQueries({ queryKey: ['alerts'] })
          return
        }

        if (event.type === 'replay_state') {
          const { type: _type, ...status } = event
          qc.setQueryData<DemoReplayStatus>(qk.replayStatus, status)
          qc.setQueryData<DemoReplaySnapshot>(qk.replaySnapshot, (previous) => ({
            ...status,
            readings: status.current_simulated_at == null ? [] : (previous?.readings ?? []),
          }))
          return
        }

        qc.setQueryData<DemoReplayStatus>(qk.replayStatus, (previous) =>
          previous ? { ...previous, state: 'error', error: event.message } : previous,
        )
      },
      () => {
        void qc.invalidateQueries({ queryKey: qk.replayStatus })
        void qc.invalidateQueries({ queryKey: qk.replaySnapshot })
      },
    )
  }, [qc])
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
    mutationFn: (v: { alertId: string; forceNew?: boolean; requestedBy?: string; reason?: string }) =>
      agentRunsApi.create({
        alert_id: v.alertId,
        force_new: v.forceNew,
        requested_by: v.requestedBy,
        reason: v.reason,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useGenerateDailyReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { runId: string; requestedBy?: string }) =>
      agentRunsApi.dailyReport(v.runId, { requested_by: v.requestedBy ?? 'operator' }),
    onSuccess: (_artifact, value) =>
      qc.invalidateQueries({ queryKey: qk.artifacts(value.runId) }),
  })
}

export function useArtifacts(runId: string | null) {
  return useQuery({
    queryKey: qk.artifacts(runId ?? ''),
    queryFn: () => agentRunsApi.artifacts(runId as string),
    enabled: runId != null,
  })
}

export function useAgentRun(runId: string | null) {
  return useQuery({
    queryKey: qk.run(runId ?? ''),
    queryFn: () => agentRunsApi.get(runId as string),
    enabled: runId != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 1000 : false
    },
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

export function useAgentIterations(runId: string | null) {
  return useQuery({
    queryKey: qk.iterations(runId ?? ''),
    queryFn: () => agentRunsApi.iterations(runId as string),
    enabled: runId != null,
  })
}

export function useReviewTasks(status = 'pending') {
  return useQuery({
    queryKey: qk.reviews(status),
    queryFn: () => reviewTasksApi.list({ status: status === 'all' ? undefined : status }),
    refetchInterval: 10000,
  })
}

export function useSubmitReviewTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: { taskId: string; body: ReviewTaskSubmitRequest }) =>
      reviewTasksApi.submit(value.taskId, value.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['review-tasks'] })
      qc.invalidateQueries({ queryKey: qk.feedback })
      qc.invalidateQueries({ queryKey: ['agent-run-result'] })
      qc.invalidateQueries({ queryKey: qk.policy })
      qc.invalidateQueries({ queryKey: qk.retrain })
    },
  })
}

export function useEvidenceCandidates(status = 'pending') {
  return useQuery({
    queryKey: qk.evidence(status),
    queryFn: () => evidenceCandidatesApi.list({ status: status === 'all' ? undefined : status }),
    refetchInterval: 10000,
  })
}

export function useReviewEvidenceCandidate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: { candidateId: string; body: EvidenceCandidateReviewRequest }) =>
      evidenceCandidatesApi.review(value.candidateId, value.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['evidence-candidates'] })
      qc.invalidateQueries({ queryKey: ['review-tasks'] })
    },
  })
}

export function useTrainingFeedback() {
  return useQuery({ queryKey: qk.feedback, queryFn: () => trainingFeedbackApi.list() })
}

export function useAutomationPolicy() {
  return useQuery({ queryKey: qk.policy, queryFn: () => automationPolicyApi.get() })
}

export function useUpdateAutomationPolicy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AutomationPolicyUpdateRequest) => automationPolicyApi.update(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.policy }),
  })
}

export function useRetrainJobs() {
  return useQuery({
    queryKey: qk.retrain,
    queryFn: () => retrainJobsApi.list(),
    refetchInterval: 5000,
  })
}

export function useCreateRetrainJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RetrainJobCreateRequest) => retrainJobsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.retrain })
      qc.invalidateQueries({ queryKey: ['review-tasks'] })
    },
  })
}

export function useReviewRetrainJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: { jobId: string; approve: boolean; body: RetrainJobActionRequest }) =>
      value.approve
        ? retrainJobsApi.approve(value.jobId, value.body)
        : retrainJobsApi.reject(value.jobId, value.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.retrain })
      qc.invalidateQueries({ queryKey: ['review-tasks'] })
    },
  })
}

export function useModelCandidates() {
  return useQuery({
    queryKey: qk.candidates,
    queryFn: () => modelCandidatesApi.list(),
    refetchInterval: 5000,
  })
}

export function usePromoteModelCandidate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: { candidateId: string; body: ModelPromotionRequest }) =>
      modelCandidatesApi.promote(value.candidateId, value.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.candidates })
      qc.invalidateQueries({ queryKey: qk.activeModel })
      qc.invalidateQueries({ queryKey: ['review-tasks'] })
    },
  })
}

export function useActiveModelDeployment() {
  return useQuery({ queryKey: qk.activeModel, queryFn: () => modelCandidatesApi.active() })
}
