import { expect, test, type Page, type Route } from '@playwright/test'

const createdAt = '2026-07-20T05:00:00.000Z'

function runListItem(runId: string, reason: string, substationId: number) {
  return {
    run_id: runId,
    status: 'completed',
    trigger_type: 'alert',
    parent_run_id: null,
    priority: 'high',
    alert_reason: reason,
    manufacturer_id: 'm1',
    substation_id: substationId,
    substation_uid: `substation-${substationId}`,
    operator_review_status: 'pending',
    created_at: createdAt,
  }
}

function workOrder(runId: string, reason: string, substationId: number) {
  const { status: _status, trigger_type: _triggerType, parent_run_id: _parentRunId, ...item } = runListItem(runId, reason, substationId)
  return item
}

function report(runId: string, artifactId: string, substationId: number) {
  return {
    artifact_id: artifactId,
    run_id: runId,
    kind: 'anomaly_report',
    name: `${artifactId}.md`,
    uri: `memory://${artifactId}`,
    priority: 'high',
    manufacturer_id: 'm1',
    substation_id: substationId,
    substation_uid: `substation-${substationId}`,
    operator_review_status: 'pending',
    created_at: createdAt,
  }
}

function result(runId: string, substationId: number, marker: string) {
  return {
    schema_version: 'ops_agent_result.v4',
    run_id: runId,
    card_id: `card-${runId}`,
    evaluation_run_id: null,
    manufacturer_id: 'm1',
    substation_id: substationId,
    headline: `${marker} 작업지시서`,
    situation: `${marker} 이상 상황`,
    evidence: [{ label: '판단 근거', content: `${marker} 판단 근거`, source: 'manual' }],
    actions: [{ priority: 1, title: `${marker} 현장 조치`, detail: `${marker} 작업 절차` }],
    cautions: [`${marker} 안전 확인`],
    report: { title: `${marker} 조치 보고서`, format: 'markdown', content: `${marker} 보고서 본문` },
  }
}

async function mockRunDetail(route: Route) {
  const runId = new URL(route.request().url()).pathname.split('/').at(-1) ?? ''
  await route.fulfill({ json: { ...runListItem(runId, runId, runId.includes('31') ? 31 : 28), error: null } })
}

async function openNormalAiAction(page: Page) {
  await page.addInitScript(() => window.sessionStorage.clear())
  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
}

test('normal mode clears all accumulated AI documents and can accumulate from one fresh run', async ({ page }) => {
  let resetCalls = 0
  let historyCleared = false
  let freshDocumentsReady = false
  const oldOrders = [workOrder('old-run-28', '이전 기계실 28 지시서', 28), workOrder('old-run-31', '이전 기계실 31 지시서', 31)]
  const oldReports = [report('old-run-28', 'old-report-28', 28), report('old-run-31', 'old-report-31', 31)]

  await page.route('**/api/demo/ai-history/reset', async (route) => {
    resetCalls += 1
    historyCleared = true
    await route.fulfill({ json: { reset_at: createdAt } })
  })
  await page.route(/\/api\/agent-runs(?:\?.*)?$/, (route) => route.fulfill({ json: {
    items: historyCleared ? [runListItem('fresh-run-28', '초기화 후 새 분석', 28)] : [],
    next_cursor: null,
    total_count: historyCleared ? 1 : 0,
  } }))
  await page.route(/\/api\/agent-runs\/[^/?]+$/, mockRunDetail)
  await page.route('**/api/agent-runs/fresh-run-28/review', (route) => route.fulfill({ json: { snapshot: null } }))
  await page.route('**/api/agent-runs/fresh-run-28/result', (route) => {
    freshDocumentsReady = true
    return route.fulfill({ json: result('fresh-run-28', 28, '새 분석') })
  })
  await page.route('**/api/work-orders*', (route) => route.fulfill({ json: {
    items: historyCleared ? (freshDocumentsReady ? [workOrder('fresh-run-28', '초기화 후 새 지시서', 28)] : []) : oldOrders,
    next_cursor: null,
    total_count: historyCleared ? (freshDocumentsReady ? 1 : 0) : oldOrders.length,
  } }))
  await page.route('**/api/agent-reports*', (route) => route.fulfill({ json: {
    items: historyCleared ? (freshDocumentsReady ? [report('fresh-run-28', 'fresh-report-28', 28)] : []) : oldReports,
    next_cursor: null,
    total_count: historyCleared ? (freshDocumentsReady ? 1 : 0) : oldReports.length,
  } }))

  await openNormalAiAction(page)
  await page.getByRole('tab', { name: '작업지시서', exact: true }).click()
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(2)
  await page.evaluate(() => {
    window.sessionStorage.setItem('heatgrid:review-chat-pending:old-run-28', '{}')
    window.sessionStorage.setItem('heatgrid:work-order-revisions:old-run-28', '[]')
    window.localStorage.setItem('heatgrid:last-agent-run', 'old-run-28')
  })

  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: '누적 기록 초기화', exact: true }).click()
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(2)
  expect(resetCalls).toBe(0)

  let confirmation = ''
  page.once('dialog', (dialog) => {
    confirmation = dialog.message()
    return dialog.accept()
  })
  await page.getByRole('button', { name: '누적 기록 초기화', exact: true }).click()
  await expect(page.getByText('누적 기록을 모두 지웠습니다. 알림에서 새 AI 분석을 시작할 수 있습니다.')).toBeVisible()
  expect(confirmation).toContain('AI 분석, 작업지시서, 보고서와 검토 대화')
  expect(resetCalls).toBe(1)
  await expect.poll(() => page.evaluate(() => ({
    proposal: window.sessionStorage.getItem('heatgrid:review-chat-pending:old-run-28'),
    revisions: window.sessionStorage.getItem('heatgrid:work-order-revisions:old-run-28'),
    lastRun: window.localStorage.getItem('heatgrid:last-agent-run'),
  }))).toEqual({ proposal: null, revisions: null, lastRun: null })

  await page.getByRole('row', { name: /초기화 후 새 분석/ }).click()
  await page.getByRole('button', { name: '작업지시서 생성', exact: true }).click()
  await expect(page.getByRole('tab', { name: '작업지시서', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(1)
  await expect(page.locator('.activity-list-card')).toContainText('초기화 후 새 지시서')
  await expect(page.locator('.activity-list-card')).not.toContainText('이전 기계실')

  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(1)
  await expect(page.locator('.activity-list-card')).not.toContainText('old-report')
})

test('fault mode clears scenario document groups and starts again without restoring old groups', async ({ page }) => {
  let historyCleared = false
  const oldOrder = (runId: string, room: number, marker: string) => ({
    version: 1,
    createdAt,
    title: `기계실 ${room} 작업지시서 v1`,
    changeSummary: 'AI 초안 생성',
    sourceRunId: runId,
    revisionInstruction: null,
    baseVersion: null,
    sections: [{ title: '위험성 및 근거', items: [`${marker} 근거`] }, { title: '작업 절차', items: [`${marker} 절차`] }, { title: '안전 확인', items: [`${marker} 안전`] }],
    content: `${marker} 작업지시서 본문`,
  })
  const group = (runId: string, alertId: string, room: number, marker: string) => ({
    id: runId,
    rootRunId: runId,
    alertId,
    substationId: room,
    createdAt,
    workOrders: [oldOrder(runId, room, marker)],
    selectedWorkOrderVersion: 1,
    acceptedWorkOrderVersion: 1,
    workOrderRerunCount: 0,
    messages: [{ id: `${runId}-message`, role: 'operator', content: `${marker} 과거 대화`, createdAt, workOrderVersion: 1 }],
    proposal: null,
    evaluationRequired: false,
    improvementCandidate: null,
    report: { status: 'completed', createdAt, savedAt: createdAt, completedAt: createdAt, content: `${marker} 과거 보고서` },
    reportMessages: [],
  })
  const first = group('old-fault-28', 'scenario-alert-pump-28', 28, '첫 번째')
  const second = group('old-fault-31', 'scenario-alert-leak-31', 31, '두 번째')

  await page.route('**/api/demo/ai-history/reset', (route) => {
    historyCleared = true
    return route.fulfill({ json: { reset_at: createdAt } })
  })
  await page.route(/\/api\/agent-runs(?:\?.*)?$/, (route) => route.fulfill({ json: {
    items: historyCleared ? [runListItem('fresh-fault-28', '초기화 후 고장 분석', 28)] : [],
    next_cursor: null,
    total_count: historyCleared ? 1 : 0,
  } }))
  await page.route(/\/api\/agent-runs\/[^/?]+$/, mockRunDetail)
  await page.route('**/api/agent-runs/fresh-fault-28/review', (route) => route.fulfill({ json: { snapshot: null } }))
  await page.route('**/api/agent-runs/fresh-fault-28/result', (route) => route.fulfill({ json: result('fresh-fault-28', 28, '새 고장 분석') }))
  await page.route('**/api/work-orders*', (route) => route.fulfill({ json: { items: [], next_cursor: null, total_count: 0 } }))
  await page.route('**/api/agent-reports*', (route) => route.fulfill({ json: { items: [], next_cursor: null, total_count: 0 } }))
  await page.route('**/api/agent-runs/fresh-fault-28/review-chat/threads', (route) => route.fulfill({ status: 404, json: { detail: 'not found' } }))
  await page.addInitScript((session) => {
    if (window.sessionStorage.getItem('heatgrid:history-reset-seeded') != null) return
    window.sessionStorage.setItem('heatgrid:history-reset-seeded', '1')
    window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session))
    window.sessionStorage.setItem('heatgrid:review-chat-pending:old-fault-28', '{}')
    window.sessionStorage.setItem('heatgrid:work-order-revisions:old-fault-28', '[]')
  }, {
    mode: 'fault',
    entryStep: 'console',
    scenarioId: 'heat-exchanger-fault',
    selectedAlertId: first.alertId,
    selectedSubstationId: 28,
    incidentState: 'incident-active',
    analyzedAlertIds: [first.alertId],
    documentGroups: [first, second],
    activeDocumentGroupId: first.id,
  })

  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.locator('.scenario-version-entry')).toHaveCount(2)

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '누적 기록 초기화', exact: true }).click()
  await expect(page.getByText('누적 기록을 모두 지웠습니다. 알림에서 새 AI 분석을 시작할 수 있습니다.')).toBeVisible()

  await page.getByRole('tab', { name: '작업지시서', exact: true }).click()
  await expect(page.locator('.scenario-version-entry')).toHaveCount(0)
  await expect(page.locator('.scenario-report-empty')).toBeVisible()
  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.scenario-report-list .scenario-version-entry')).toHaveCount(0)
  await expect(page.locator('.scenario-list-empty')).toBeVisible()
  await expect.poll(() => page.evaluate(() => {
    const state = JSON.parse(window.sessionStorage.getItem('heatgrid:scenario-session') ?? '{}') as Record<string, unknown>
    return {
      groups: Array.isArray(state.documentGroups) ? state.documentGroups.length : -1,
      workOrders: Array.isArray(state.workOrders) ? state.workOrders.length : -1,
      analyzed: Array.isArray(state.analyzedAlertIds) ? state.analyzedAlertIds.length : -1,
      incidentState: state.incidentState,
      proposal: window.sessionStorage.getItem('heatgrid:review-chat-pending:old-fault-28'),
      revisions: window.sessionStorage.getItem('heatgrid:work-order-revisions:old-fault-28'),
    }
  })).toEqual({ groups: 0, workOrders: 0, analyzed: 0, incidentState: 'incident-active', proposal: null, revisions: null })

  await page.getByRole('tab', { name: 'AI 분석 목록', exact: true }).click()
  await page.getByRole('row', { name: /초기화 후 고장 분석/ }).click()
  await page.getByRole('button', { name: '작업지시서 생성', exact: true }).click()
  await expect(page.locator('.scenario-version-entry')).toHaveCount(1)
  await expect(page.locator('.scenario-document-content')).toContainText('새 고장 분석 작업 절차')
  await expect(page.locator('.scenario-document-content')).not.toContainText('첫 번째 작업지시서 본문')

  await page.reload()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.locator('.scenario-version-entry')).toHaveCount(1)
  await expect(page.locator('.scenario-document-content')).toContainText('새 고장 분석 작업 절차')
})
