/** 계약 소비 훅 (TanStack Query). alertsApi/agentRunsApi/healthApi는 backend.ts 스위치. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  agentRunEvaluationsApi,
  agentRunsApi,
  alertsApi,
  automationPolicyApi,
  evidenceCandidatesApi,
  healthApi,
  modelCandidatesApi,
  operationsMetricsApi,
  operatorReviewsApi,
  policyCandidatesApi,
  priorityEvaluationsApi,
  retrainJobsApi,
  reviewTasksApi,
  trainingFeedbackApi,
} from './backend'
import type {
  AlertListQuery,
  AutomationPolicyUpdateRequest,
  EvidenceCandidateReviewRequest,
  ModelPromotionRequest,
  OperatorReviewSubmitRequest,
  PolicyCandidateDecisionRequest,
  RetrainJobActionRequest,
  RetrainJobCreateRequest,
  ReviewTaskSubmitRequest,
} from './contracts'

export const qk = {
  alerts: (q?: AlertListQuery) => ['alerts', q?.status ?? 'open', q?.priority_level ?? 'all'] as const,
  artifacts: (id: string) => ['artifacts', id] as const,
  runs: ['agent-runs'] as const,
  run: (id: string) => ['agent-run', id] as const,
  reviewSnapshot: (id: string) => ['agent-run-review-snapshot', id] as const,
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
  runEvaluation: (id: string) => ['agent-run-evaluation', id] as const,
  operatorReviews: (id: string) => ['operator-reviews', id] as const,
  policyCandidates: ['agent-policy-candidates'] as const,
  operationsMetrics: ['agent-operations-metrics'] as const,
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

export function useAgentRuns() {
  return useQuery({
    queryKey: qk.runs,
    queryFn: () => agentRunsApi.list(),
    refetchInterval: 5000,
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

export function useAgentRunReviewSnapshot(runId: string | null) {
  return useQuery({
    queryKey: qk.reviewSnapshot(runId ?? ''),
    queryFn: () => {
      if (runId == null) throw new Error('run_id가 없습니다.')
      return agentRunsApi.review(runId)
    },
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

/* ===== v3-02 운영자 검토·평가·정책 후보·운영 지표 훅 ===== */

/** 선택 실행의 parent/worker 결정적 평가 projection (1건) */
export function useAgentRunEvaluation(runId: string | null) {
  return useQuery({
    queryKey: qk.runEvaluation(runId ?? ''),
    queryFn: async () => {
      const page = await agentRunEvaluationsApi.list({ run_id: runId as string, limit: 1 })
      return page.items[0] ?? null
    },
    enabled: runId != null,
  })
}

export function useOperatorReviews(runId: string | null) {
  return useQuery({
    queryKey: qk.operatorReviews(runId ?? ''),
    queryFn: () => operatorReviewsApi.history(runId as string),
    enabled: runId != null,
  })
}

export function useSubmitOperatorReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: { runId: string; body: OperatorReviewSubmitRequest }) =>
      operatorReviewsApi.submit(value.runId, value.body),
    onSuccess: (_record, value) => {
      qc.invalidateQueries({ queryKey: qk.operatorReviews(value.runId) })
      qc.invalidateQueries({ queryKey: qk.runEvaluation(value.runId) })
      qc.invalidateQueries({ queryKey: qk.runs })
      // correct 검토는 정책 후보를 만들 수 있다 → 후보/지표 갱신.
      qc.invalidateQueries({ queryKey: qk.policyCandidates })
      qc.invalidateQueries({ queryKey: qk.operationsMetrics })
    },
  })
}

export function usePolicyCandidates() {
  return useQuery({
    queryKey: qk.policyCandidates,
    queryFn: () => policyCandidatesApi.list(),
    refetchInterval: 10000,
  })
}

export function useDecidePolicyCandidate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: { candidateId: string; approve: boolean; body: PolicyCandidateDecisionRequest }) =>
      value.approve
        ? policyCandidatesApi.approve(value.candidateId, value.body)
        : policyCandidatesApi.reject(value.candidateId, value.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.policyCandidates })
      qc.invalidateQueries({ queryKey: qk.operationsMetrics })
    },
  })
}

export function useOperationsMetrics() {
  return useQuery({
    queryKey: qk.operationsMetrics,
    queryFn: () => operationsMetricsApi.get(),
    refetchInterval: 15000,
  })
}
