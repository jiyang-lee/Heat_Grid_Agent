/**
 * API 클라이언트 토대 (골격).
 *
 * fetch 래퍼와 SSE(EventSource) 헬퍼의 시그니처만 제공한다.
 * 실제 화면 훅(예: TanStack Query useQuery/useMutation, 컴포넌트별 데이터 바인딩)은
 * 이 위에서 각 화면을 만드는 쪽이 작성한다.
 *
 * 모든 경로는 상대경로 `/api/...`로 호출한다. 개발 시 Vite dev proxy가
 * http://127.0.0.1:8002 로 전달하고, 배포 시 동일 오리진 또는 리버스 프록시가 처리한다.
 */

import type {
  AgentRunArtifact,
  AgentRunCreateRequest,
  AgentRunResponse,
  OpsAgentResultV4,
  AlertAckRequest,
  AlertAckResponse,
  AlertEnqueueResponse,
  AlertListQuery,
  AlertSummary,
  HealthStatus,
} from './contracts'

export const API_BASE = '/api'

export class ApiError extends Error {
  readonly status: number
  readonly url: string

  constructor(status: number, url: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

/** 공통 JSON fetch 래퍼. 비정상 응답은 ApiError로 던진다. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, url, body || res.statusText)
  }
  return res.json() as Promise<T>
}

/** 서버 루트 경로용(예: /health) — /api prefix를 붙이지 않는다. */
export async function rawFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, path, body || res.statusText)
  }
  return res.json() as Promise<T>
}

function toQueryString(query?: Record<string, string | undefined>): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v != null) params.set(k, v)
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

// ---------------------------------------------------------------------------
// REST 엔드포인트 (계약 표면)
// ---------------------------------------------------------------------------

export const alertsApi = {
  list: (query?: AlertListQuery) =>
    apiFetch<AlertSummary[]>(
      `/alerts${toQueryString(query as Record<string, string | undefined> | undefined)}`,
    ),
  get: (alertId: string) => apiFetch<AlertSummary>(`/alerts/${alertId}`),
  ack: (alertId: string, body: AlertAckRequest) =>
    apiFetch<AlertAckResponse>(`/alerts/${alertId}/ack`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  resolve: (alertId: string, body: AlertAckRequest) =>
    apiFetch<AlertAckResponse>(`/alerts/${alertId}/resolve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  enqueue: () => apiFetch<AlertEnqueueResponse>('/alerts/enqueue', { method: 'POST' }),
}

export const healthApi = {
  get: () => rawFetch<HealthStatus>('/health'),
}

/**
 * GET /cards — 계약(/api) 밖의 읽기 전용 편의 엔드포인트.
 * 알림(AlertSummary)에는 건물명이 없어서, card_id → substation_id 매핑을 얻어
 * 프론트 로컬 단지 데이터(complexes.ts)로 건물명을 붙이는 enrichment 용도로만 쓴다.
 * 계약·백엔드는 무변경이며, 이 엔드포인트가 없거나 실패하면 이름 없이 degrade한다.
 */
export interface CardRef {
  card_id: string
  substation_id: number | null
}

export const cardsApi = {
  list: () => rawFetch<CardRef[]>('/cards'),
}

export const agentRunsApi = {
  create: (body: AgentRunCreateRequest) =>
    apiFetch<AgentRunResponse>('/agent-runs', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  get: (runId: string) => apiFetch<AgentRunResponse>(`/agent-runs/${runId}`),
  result: (runId: string) => apiFetch<OpsAgentResultV4>(`/agent-runs/${runId}/result`),
  artifacts: (runId: string) =>
    apiFetch<AgentRunArtifact[]>(`/agent-runs/${runId}/artifacts`),
}

// ---------------------------------------------------------------------------
// SSE 헬퍼 (골격)
// ---------------------------------------------------------------------------

/**
 * SSE 스트림 구독 헬퍼. native EventSource를 감싼다.
 * onEvent에는 파싱된 SSE envelope({type, message, payload})가 전달된다.
 * 반환된 함수를 호출하면 구독을 해제한다.
 *
 * 사용 예:
 *   const stop = subscribeSse('/agent-runs/<run_id>/events', (evt) => { ... })
 *   // cleanup: stop()
 */
export function subscribeSse(
  path: string,
  onEvent: (data: unknown) => void,
  onError?: (err: Event) => void,
): () => void {
  const source = new EventSource(`${API_BASE}${path}`)
  source.onmessage = (e: MessageEvent) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch {
      onEvent(e.data)
    }
  }
  if (onError) source.onerror = onError
  return () => source.close()
}

export const alertEventsPath = '/alerts/events'
export const agentRunEventsPath = (runId: string) => `/agent-runs/${runId}/events`
