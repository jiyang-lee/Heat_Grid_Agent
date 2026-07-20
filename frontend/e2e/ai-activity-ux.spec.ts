import { expect, test, type Page, type Route } from '@playwright/test'

const createdAt = '2026-07-20T05:00:00.000Z'

const runItem = {
  run_id: 'run-ux-28',
  status: 'completed',
  trigger_type: 'alert',
  parent_run_id: null,
  priority: 'high',
  alert_reason: '순환펌프 진동 증가 · 현장 점검이 필요합니다.',
  manufacturer_id: 'm1',
  substation_id: 28,
  substation_uid: 'substation-28',
  operator_review_status: 'pending',
  created_at: createdAt,
}

const result = {
  schema_version: 'ops_agent_result.v4',
  run_id: runItem.run_id,
  card_id: 'card-run-ux-28',
  evaluation_run_id: null,
  manufacturer_id: 'm1',
  substation_id: 28,
  headline: '순환펌프 이상 대응 계획',
  situation: '진동과 환수온도 변화가 함께 감지되어 현장 확인이 필요합니다.',
  evidence: [{ label: '판단 근거', content: '진동 임계치 초과', source: 'manual' }],
  actions: [{ priority: 1, title: '현장 상태 확인', detail: '펌프 진동과 누수 여부를 확인합니다.' }],
  cautions: ['보호구를 착용하고 전원을 차단합니다.'],
  report: { title: '순환펌프 이상 조치 보고서', format: 'markdown', content: '순환펌프 이상 조치 보고서 본문' },
}

const alert = {
  alert_id: 'alert-ux-28',
  episode_id: 'incident-ux-28',
  card_id: 'card-run-ux-28',
  evaluation_run_id: null,
  as_of_time: createdAt,
  manufacturer_id: 'm1',
  substation_id: 28,
  priority_rank: 1,
  freshness_status: 'fresh',
  priority_level: 'high',
  priority_score: 92,
  status: 'open',
  enqueue_reason: '순환펌프 진동 증가',
  created_at: createdAt,
  acked_at: null,
  acked_by: null,
  read_at: createdAt,
  read_by: 'operator',
}

function workOrderItem() {
  const { status: _status, trigger_type: _triggerType, parent_run_id: _parentRunId, ...item } = runItem
  return item
}

function runDetail(runId = runItem.run_id) {
  return { run_id: runId, status: 'completed', trigger_type: 'alert', error: null }
}

async function fallbackApi(route: Route) {
  const url = new URL(route.request().url())
  if (url.pathname === '/api/me') {
    await route.fulfill({ json: { user_id: 'operator', display_name: '운영자', capabilities: ['admin'], auth_mode: 'fixed' } })
    return
  }
  await route.fulfill({ status: 404, json: { detail: 'not mocked in AI activity UX test' } })
}

async function mockActivityData(page: Page) {
  await page.route(/\/api\/agent-runs(?:\?.*)?$/, (route) => route.fulfill({ json: { items: [runItem], next_cursor: null, total_count: 1 } }))
  await page.route(/\/api\/agent-runs\/run-ux-28$/, (route) => route.fulfill({ json: runDetail() }))
  await page.route('**/api/agent-runs/run-ux-28/result', (route) => route.fulfill({ json: result }))
  await page.route('**/api/agent-runs/run-ux-28/review', (route) => route.fulfill({ json: { snapshot: null } }))
  await page.route('**/api/work-orders*', (route) => route.fulfill({ json: { items: [workOrderItem()], next_cursor: null, total_count: 1 } }))
  await page.route('**/api/agent-reports*', (route) => route.fulfill({ json: { items: [], next_cursor: null, total_count: 0 } }))
  await page.route('**/api/agent-runs/run-ux-28/review-chat/threads', (route) => route.fulfill({ status: 404, json: { detail: 'thread not created' } }))
}

async function openNormalAiAction(page: Page) {
  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
}

function scenarioOrder(version = 1) {
  return {
    version,
    createdAt,
    title: `기계실 28 작업지시서 v${version}`,
    changeSummary: version === 1 ? 'AI 초안 생성' : '안전 확인 보강',
    sourceRunId: version === 1 ? runItem.run_id : `run-ux-28-v${version}`,
    revisionInstruction: version === 1 ? null : '안전 확인을 보강해줘',
    baseVersion: version === 1 ? null : version - 1,
    sections: [
      { title: '위험성 및 근거', items: ['진동 임계치 초과'] },
      { title: '작업 절차', items: ['펌프 상태를 확인합니다.'] },
      { title: '안전 확인', items: [version === 1 ? '보호구 착용' : '절연 보호구 착용'] },
    ],
    content: `기계실 28 작업지시서 v${version}\n\n안전 확인\n${version === 1 ? '보호구 착용' : '절연 보호구 착용'}`,
  }
}

function scenarioGroup() {
  return {
    id: runItem.run_id,
    rootRunId: runItem.run_id,
    alertId: 'scenario-alert-pump-28',
    substationId: 28,
    createdAt,
    workOrders: [scenarioOrder(1)],
    selectedWorkOrderVersion: 1,
    acceptedWorkOrderVersion: 1,
    workOrderRerunCount: 0,
    messages: [],
    proposal: null,
    evaluationRequired: false,
    improvementCandidate: null,
    report: { status: 'completed', createdAt, savedAt: createdAt, completedAt: createdAt, content: '기존 완료 보고서 본문' },
    reportMessages: [],
  }
}

function faultSession(group = scenarioGroup()) {
  return {
    mode: 'fault',
    entryStep: 'console',
    scenarioId: 'heat-exchanger-fault',
    selectedAlertId: 'scenario-alert-pump-28',
    selectedSubstationId: 28,
    incidentState: 'incident-active',
    analyzedAlertIds: [],
    documentGroups: [group],
    activeDocumentGroupId: group.id,
    documentAlertId: group.alertId,
  }
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.clear()
    window.localStorage.removeItem('heatgrid:last-agent-run')
  })
  await page.route(/^https?:\/\/[^/]+\/api\//, fallbackApi)
})

test('normal mode keeps the completed AI task tray available', async ({ page }) => {
  await page.addInitScript((requestedAt) => {
    window.sessionStorage.setItem('heatgrid:agent-analysis-queue', JSON.stringify([
      { runId: 'run-normal-completed', alertId: 'alert-normal-completed', label: '정상 모드 확인 작업', requestedAt },
    ]))
  }, createdAt)
  await page.route('**/api/agent-runs/run-normal-completed', (route) => route.fulfill({ json: { ...runDetail('run-normal-completed'), status: 'completed' } }))

  await page.goto('/?devtools=0')
  const taskTray = page.getByRole('button', { name: 'AI 조치 1건 완료', exact: true })
  await expect(taskTray).toBeVisible()
  const trayBounds = await page.locator('.scenario-analysis-progress').boundingBox()
  const viewport = page.viewportSize()
  expect(trayBounds).not.toBeNull()
  expect(viewport).not.toBeNull()
  if (trayBounds == null || viewport == null) throw new Error('AI 조치 토스트 위치를 확인하지 못했습니다.')
  expect(Math.round(trayBounds.x + trayBounds.width)).toBe(viewport.width - 8)
  expect(Math.round(trayBounds.y + trayBounds.height)).toBe(viewport.height - (viewport.width <= 720 ? 64 : 8))
  await taskTray.click()
  await expect(page.getByText('정상 모드 확인 작업', { exact: true })).toBeVisible()
})

test('fault alert shortcut opens the requested initial run detail', async ({ page }) => {
  await mockActivityData(page)
  const group = scenarioGroup()
  await page.addInitScript((session) => window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session)), faultSession(group))
  await page.route('**/api/scenario-alerts', (route) => route.fulfill({ json: { ...alert, alert_id: 'fault-alert-ux-28' } }))
  await page.route(/\/api\/agent-runs$/, (route) => route.request().method() === 'POST'
    ? route.fulfill({ json: runDetail() })
    : route.fallback())

  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: '알림', exact: true }).click()
  await page.getByRole('row', { name: /환수온도 급락 및 난방 순환펌프 이상/ }).click()
  const scenarioRequest = page.waitForRequest('**/api/scenario-alerts')
  const runRequest = page.waitForRequest((request) => new URL(request.url()).pathname === '/api/agent-runs' && request.method() === 'POST')
  await page.getByRole('button', { name: 'AI 조치 생성', exact: true }).click()
  await scenarioRequest
  await runRequest
  const taskTray = page.getByRole('button', { name: /AI 조치 1건/ })
  await expect(taskTray).toBeVisible({ timeout: 5_000 })
  await taskTray.click()
  await page.getByRole('button', { name: '결과 보기', exact: true }).click()
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '순환펌프 진동 증가' })).toBeVisible()
})

test('fault analysis failure is kept in the AI task tray', async ({ page }) => {
  await page.addInitScript((session) => window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session)), faultSession())
  await page.route('**/api/scenario-alerts', (route) => route.fulfill({ json: { ...alert, alert_id: 'fault-alert-ux-28' } }))
  await page.route(/\/api\/agent-runs$/, (route) => route.request().method() === 'POST'
    ? route.fulfill({ json: { ...runDetail('run-failed-28'), status: 'queued' } })
    : route.fallback())
  await page.route('**/api/agent-runs/run-failed-28', (route) => route.fulfill({ json: { ...runDetail('run-failed-28'), status: 'failed' } }))

  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: '알림', exact: true }).click()
  await page.getByRole('row', { name: /환수온도 급락 및 난방 순환펌프 이상/ }).click()
  await page.getByRole('button', { name: 'AI 조치 생성', exact: true }).click()

  const taskTray = page.getByRole('button', { name: 'AI 조치 1건 확인 필요', exact: true })
  await expect(taskTray).toBeVisible({ timeout: 5_000 })
  await taskTray.click()
  await expect(page.locator('.scenario-analysis-progress-panel')).toContainText('실패')
})

test('AI task tray shows queued and running requests together', async ({ page }) => {
  let queuedRunCancelled = false
  await page.addInitScript((requestedAt) => {
    window.sessionStorage.setItem('heatgrid:agent-analysis-queue', JSON.stringify([
      { runId: 'run-running', alertId: 'alert-running', label: '1호기 압력 이상', requestedAt },
      { runId: 'run-queued', alertId: 'alert-queued', label: '2호기 온도 경보', requestedAt },
    ]))
  }, createdAt)
  await page.route('**/api/agent-runs/run-running', (route) => route.fulfill({ json: { ...runDetail('run-running'), status: 'running' } }))
  await page.route('**/api/agent-runs/run-queued', (route) => route.fulfill({ json: { ...runDetail('run-queued'), status: queuedRunCancelled ? 'cancelled' : 'queued' } }))
  await page.route('**/api/agent-runs/run-queued/cancel', (route) => {
    queuedRunCancelled = true
    return route.fulfill({ json: { ...runDetail('run-queued'), status: 'cancelled' } })
  })

  await page.goto('/?devtools=0')
  const taskTray = page.getByRole('button', { name: 'AI 조치 2건 진행 중', exact: true })
  await expect(taskTray).toBeVisible()
  await taskTray.click()
  await expect(page.getByText('1호기 압력 이상', { exact: true })).toBeVisible()
  await expect(page.getByText('2호기 온도 경보', { exact: true })).toBeVisible()
  await expect(page.locator('.scenario-analysis-progress-panel')).toContainText('분석 중')
  await expect(page.locator('.scenario-analysis-progress-panel')).toContainText('대기 중')
  await page.getByRole('button', { name: '대기 취소', exact: true }).click()
  await expect(page.locator('.scenario-analysis-progress-panel')).toContainText('취소됨')
})

test('failed history reset keeps the selected full work-order detail open', async ({ page }) => {
  await mockActivityData(page)
  await page.route('**/api/demo/ai-history/reset', (route) => route.fulfill({ status: 500, json: { detail: 'fixture reset failure' } }))
  await openNormalAiAction(page)
  await page.getByRole('tab', { name: '작업지시서', exact: true }).click()
  await page.getByRole('row', { name: /순환펌프 진동 증가/ }).click()
  await page.getByRole('button', { name: '상세 보기', exact: true }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '누적 기록 초기화', exact: true }).click()

  await expect(page.locator('.activity-reset-feedback[role="alert"]')).toContainText('AI 기록을 초기화하지 못했습니다. (오류 500)')
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '순환펌프 진동 증가 · 현장 점검이 필요합니다.' })).toBeVisible()
})

test('active analysis blocks history reset without clearing the work-order list or detail', async ({ page }) => {
  await mockActivityData(page)
  await page.route('**/api/demo/ai-history/reset', (route) => route.fulfill({ status: 409, json: { detail: 'active agent runs prevent reset' } }))
  await openNormalAiAction(page)
  await page.getByRole('tab', { name: '작업지시서', exact: true }).click()
  await page.getByRole('row', { name: /순환펌프 진동 증가/ }).click()
  await page.getByRole('button', { name: '상세 보기', exact: true }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '누적 기록 초기화', exact: true }).click()

  await expect(page.locator('.activity-reset-feedback[role="alert"]')).toHaveText('진행 중인 AI 분석이 있어 초기화할 수 없습니다. 완료 후 다시 시도해 주세요.')
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(1)
  await expect(page.locator('.activity-list-card tbody tr')).toContainText('순환펌프 진동 증가')
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '순환펌프 진동 증가 · 현장 점검이 필요합니다.' })).toBeVisible()
})

test('full work-order detail exposes document and AI shortcuts with an always-accessible footer', async ({ page }) => {
  await mockActivityData(page)
  await openNormalAiAction(page)
  await page.getByRole('tab', { name: '작업지시서', exact: true }).click()
  await page.getByRole('row', { name: /순환펌프 진동 증가/ }).click()
  await page.getByRole('button', { name: '상세 보기', exact: true }).click()

  const shortcuts = page.getByRole('navigation', { name: '작업지시서 상세 바로가기' })
  await expect(shortcuts.getByRole('button', { name: '문서 본문', exact: true })).toBeVisible()
  await expect(shortcuts.getByRole('button', { name: 'AI 수정·질문', exact: true })).toBeVisible()
  await shortcuts.getByRole('button', { name: 'AI 수정·질문', exact: true }).click()
  await expect(page.getByRole('region', { name: 'AI 수정 챗봇' })).toBeInViewport()

  const footer = page.locator('.activity-detail-footer')
  await expect(footer).toBeVisible()
  await expect(footer.getByRole('button', { name: 'PDF 다운로드', exact: true })).toBeVisible()
  await expect(footer.getByRole('button', { name: 'v1 실행 검토 승인', exact: true })).toBeVisible()
})

test('fault report memo stays in its local document group without calling review-chat', async ({ page }) => {
  const group = scenarioGroup()
  await page.addInitScript((session) => window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session)), faultSession(group))
  let reviewChatCalls = 0
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.includes('/review-chat')) reviewChatCalls += 1
  })

  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.getByRole('heading', { name: '보고서 검토 메모' })).toBeVisible()
  const callsBeforeMemo = reviewChatCalls

  await page.getByRole('textbox', { name: '검토 메모' }).fill('현장 인계 항목을 다시 확인')
  await page.getByRole('button', { name: '메모 저장', exact: true }).click()
  await expect(page.locator('.scenario-chat-messages')).toContainText('현장 인계 항목을 다시 확인')
  expect(reviewChatCalls).toBe(callsBeforeMemo)

  await expect.poll(() => page.evaluate((groupId) => {
    const session = JSON.parse(window.sessionStorage.getItem('heatgrid:scenario-session') ?? '{}') as {
      documentGroups?: Array<{ id: string; reportMessages?: Array<{ content: string }> }>
    }
    return session.documentGroups?.find((candidate) => candidate.id === groupId)?.reportMessages?.map((message) => message.content) ?? []
  }, group.id)).toEqual([
    '현장 인계 항목을 다시 확인',
    '보고서 검토 의견으로 정리했습니다. 본문은 변경하지 않았으니 운영자가 필요한 문구만 직접 반영해 주세요.',
  ])
})

test('creating v2 keeps the previously adopted version and completed report', async ({ page }) => {
  const group = scenarioGroup()
  await page.addInitScript((session) => window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session)), faultSession(group))
  const proposal = {
    proposal_id: 'proposal-keep-report-v2',
    thread_id: 'thread-keep-report',
    run_id: runItem.run_id,
    expected_review_version: 0,
    context_hash: 'context-keep-report',
    status: 'awaiting_confirmation',
    decision: 'correct',
    next_action: 'targeted_rerun',
    reason: '안전 확인 보강',
    reason_category: 'report_draft_issue',
    disposition: 'inspection_recommended',
    correction: { instruction: '안전 확인을 보강해줘' },
    target_stage: 'report_draft',
    revision: { target_area: 'safety_notes', safety_notes: ['절연 보호구 착용'], change_summary: '안전 확인 보강' },
    draft_content: scenarioOrder(2).content,
    change_summary: '안전 확인 보강',
    expires_at: '2026-07-21T05:00:00.000Z',
  }
  await page.route('**/api/agent-runs/run-ux-28/review-chat/threads', (route) => route.fulfill({ json: {
    thread_id: 'thread-keep-report', run_id: runItem.run_id, status: 'open', context_hash: 'context-keep-report', base_review_version: 0, created_at: createdAt,
  } }))
  await page.route('**/api/review-chat/threads/thread-keep-report/proposals/pending', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/review-chat/threads/thread-keep-report/messages*', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { items: [] } })
      return
    }
    await route.fulfill({ status: 202, json: {
      operator_message: { message_id: 'operator-keep-report', thread_id: 'thread-keep-report', sequence: 1, role: 'operator', message_kind: 'action_request', content: '안전 확인을 보강해줘', structured_payload: {}, citations: [], context_hash: 'context-keep-report', created_at: createdAt },
      assistant_message: { message_id: 'assistant-keep-report', thread_id: 'thread-keep-report', sequence: 2, role: 'assistant', message_kind: 'proposal', content: '안전 확인 수정안을 만들었습니다.', structured_payload: {}, citations: [], context_hash: 'context-keep-report', created_at: createdAt },
      proposal,
    } })
  })
  await page.route('**/api/review-chat/proposals/proposal-keep-report-v2/confirm', (route) => route.fulfill({ json: {
    proposal_id: proposal.proposal_id,
    status: 'executed',
    review_id: 'review-keep-report',
    child_run_id: null,
    target_stage: 'report_draft',
    rerun_status: 'blocked_legacy_input_unavailable',
    blocked_reason: 'blocked_legacy_input_unavailable',
    incident_id: 'incident-ux-28',
    document_version_id: 'document-ux-v2',
    document_version: 2,
    document_content: { title: scenarioOrder(2).title, body: scenarioOrder(2).content, actions: ['펌프 상태를 확인합니다.'], evidence: [], safety_notes: ['절연 보호구 착용'] },
  } }))

  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  const chat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await chat.fill('안전 확인을 보강해줘')
  await page.getByRole('button', { name: '수정 초안 요청', exact: true }).click()
  await page.getByRole('button', { name: '초안 확정 · v2 생성', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'v2', exact: true })).toBeVisible()

  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.scenario-report-content')).toContainText('기존 완료 보고서 본문')
  await expect(page.locator('.scenario-report-meta')).toContainText('작업지시서 v1')
  await expect.poll(() => page.evaluate((groupId) => {
    const session = JSON.parse(window.sessionStorage.getItem('heatgrid:scenario-session') ?? '{}') as {
      documentGroups?: Array<{ id: string; acceptedWorkOrderVersion?: number; report?: { status?: string; content?: string } }>
    }
    const stored = session.documentGroups?.find((candidate) => candidate.id === groupId)
    return { accepted: stored?.acceptedWorkOrderVersion, reportStatus: stored?.report?.status, reportContent: stored?.report?.content }
  }, group.id)).toEqual({ accepted: 1, reportStatus: 'completed', reportContent: '기존 완료 보고서 본문' })
})
