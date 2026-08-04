import { expect, test } from '@playwright/test'

const policy = {
  version: 1,
  timezone: 'Asia/Seoul',
  freshness_threshold_minutes: 10,
  anomaly_confirmations: 3,
  recovery_confirmations: 3,
  shifts: [
    { shift_id: 'day', label: '주간', start_time: '08:00', end_time: '20:00' },
    { shift_id: 'night', label: '야간', start_time: '20:00', end_time: '08:00' },
  ],
  updated_at: '2026-07-19T00:00:00Z',
  updated_by: 'operator',
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.sessionStorage.clear())
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    if (url.pathname === '/api/me') return route.fulfill({ json: { user_id: 'operator', display_name: '운영자', capabilities: ['admin'], auth_mode: 'fixed' } })
    if (url.pathname === '/api/operations-policy') return route.fulfill({ json: { ...policy, ...(method === 'PUT' ? { version: 2 } : {}) } })
    if (url.pathname === '/api/replay-datasets') return route.fulfill({ json: [{ dataset_id: 'dataset-1', dataset_version: 'v1', status: 'available', expected_substations: [1, 3, 10, 31], source_interval_seconds: 3, window_ticks: 12, replay_start: '2020-11-26T00:00:00Z', replay_end: '2020-11-27T00:00:00Z', validated_at: '2026-07-19T00:00:00Z' }] })
    if (url.pathname === '/api/replay-runs' && method === 'POST') return route.fulfill({ json: { run_id: 'run-1', stream_key: 'replay:run-1', state: 'created', version: 1 } })
    if (url.pathname === '/api/replay-runs/run-1/commands') return route.fulfill({ json: { command_id: 'command-1', status: 'accepted' } })
    if (url.pathname === '/api/replay-runs/run-1/snapshot') return route.fulfill({ json: { run_id: 'run-1', stream_key: 'replay:run-1', state: 'running', version: 2, current_simulated_at: '2020-11-26T05:50:00Z', last_emitted_sequence: 1, last_scored_window_end: null, last_evaluation_run_id: null, speed_multiplier: 1, tick_seconds: 3, dataset_version: 'v1', window_ticks: 12, last_event_id: 1, window_progress: 1, synthetic: true, readings: [] } })
    if (url.pathname === '/api/operations-reports/current-shift') return route.fulfill({ json: { period_start: '2026-07-19T08:00:00+09:00', period_end: '2026-07-19T20:00:00+09:00', timezone: 'Asia/Seoul', memo: '', updated_by: null, updated_at: null } })
    if (url.pathname === '/api/operations-reports') return route.fulfill({ json: { items: [] } })
    if (url.pathname === '/api/alerts') return route.fulfill({ json: [] })
    if (url.pathname.includes('/priority-evaluations')) return route.fulfill({ status: 503, json: { detail: 'test fixture' } })
    if (url.pathname === '/api/health') return route.fulfill({ json: { status: 'ok' } })
    return route.fulfill({ status: 404, json: { detail: 'not mocked' } })
  })
})

test('운영 홈에서 관리자 재생과 보고서까지 핵심 흐름이 이어진다', async ({ page }) => {
  test.setTimeout(60_000)
  await page.goto('/?devtools=0')
  await expect(page.locator('.topbar-page-context')).toContainText('홈')
  await expect(page.getByText('운영 환경을 선택하세요')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '관리자', exact: true })).toHaveCount(0)
  await expect(page.locator('.topbar-clock strong')).toHaveText(/^\d{2}:\d{2}$/)

  await page.getByRole('button', { name: '설정', exact: true }).click()
  await page.getByRole('button', { name: '관리자 화면 열기' }).click()
  await expect(page.getByText('운영 판정 정책')).toBeVisible()
  await expect(page.locator('input[type="number"][value="3"]')).toHaveCount(2)
  await page.getByRole('button', { name: '재생 훈련 시작' }).click()
  await expect(page.locator('.topbar-page-context')).toContainText('홈')
  await expect(page.locator('.topbar-clock strong')).toHaveText('14:50')

  await expect(page.getByText('현재 주요 알림 없음', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /열교환기 외부 누수 의심/ })).toBeVisible({ timeout: 12_000 })
  await page.getByRole('button', { name: /열교환기 외부 누수 의심/ }).click()
  await expect(page.locator('.sensor-flow')).toContainText('기계실 31')

  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'AI 분석 목록' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '작업지시서' })).toBeVisible()
  await expect(page.getByRole('tab')).toHaveCount(2)

  await page.getByRole('button', { name: '운영 보고서', exact: true }).click()
  await expect(page.getByRole('heading', { name: '현재 교대 인계 메모' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '공식 운영 기록' })).toBeVisible()
})
