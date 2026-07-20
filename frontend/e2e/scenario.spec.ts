import { expect, test, type Page } from '@playwright/test'

async function openEntry(page: Page) {
  await page.addInitScript(() => window.sessionStorage.clear())
  await page.goto('/?devtools=0')
}

async function startFaultScenario(page: Page) {
  await openEntry(page)
  await page.getByRole('button', { name: '설정', exact: true }).click()
  await page.getByRole('button', { name: '관리자 화면 열기' }).click()
  await page.getByRole('button', { name: '재생 훈련 시작' }).click()
}

async function expectNoPageScroll(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight && document.body.scrollHeight <= window.innerHeight)).toBe(true)
}

async function waitForIncident(page: Page) {
  await expect(page.getByText('현재 주요 알림 없음', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /환수온도 급락 및 난방 순환펌프 이상/ })).toBeVisible({ timeout: 12_000 })
}

async function dismissIncidentToasts(page: Page) {
  const toastStack = page.locator('.scenario-incident-toasts')
  await expect(toastStack.getByRole('status').first()).toHaveAttribute('aria-label', '우선순위 1 경보')
  await expect(toastStack.getByRole('status')).toHaveCount(3, { timeout: 4_000 })
  for (const rank of [1, 2, 3] as const) {
    await page.getByRole('status', { name: `우선순위 ${rank} 경보` })
      .getByRole('button', { name: `우선순위 ${rank} 경보 닫기` })
      .click()
  }
  await expect(toastStack.getByRole('status')).toHaveCount(0)
}

async function openAlertDetail(page: Page, title: RegExp) {
  await page.getByRole('row', { name: title }).getByRole('button', { name: '상세' }).click()
}

test('entry and dashboard keep the viewport fixed with no Replay navigation', async ({ page }) => {
  await openEntry(page)
  await expect(page.getByText('운영 환경을 선택하세요')).toHaveCount(0)
  await expectNoPageScroll(page)

  await expect(page.locator('.metric-grid-five > *')).toHaveCount(5)
  await expect(page.locator('.metric-grid-five').getByRole('article')).toHaveCount(5)
  await expect(page.locator('.metric-grid-five')).toContainText('관찰')
  await expect(page.locator('.metric-grid-five')).not.toContainText('정기 점검')
  await expect(page.getByRole('button', { name: 'Replay', exact: true })).toHaveCount(0)
  await expect(page.locator('.topbar-page-context')).toContainText('홈')
  await expect(page.locator('.topbar-page-context > span')).toHaveCount(0)
  await expect(page.locator('.topbar-nav')).toHaveCount(0)
  await expect(page.locator('.sensor-flow')).toContainText('기계실 미선택')
  await expect(page.locator('.sf-charts svg')).toHaveCount(0)
  await expectNoPageScroll(page)
})

test('normal AI action entry opens the plan list without a selected detail', async ({ page }, testInfo) => {
  await openEntry(page)
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'AI 분석 목록' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.activity-list-card')).toBeVisible()
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: '대상' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '현재 단계' })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: '결과' })).toHaveCount(0)

  const planRows = page.locator('.activity-list-card tbody tr')
  await expect.poll(() => planRows.count()).toBeGreaterThan(0)
  await planRows.nth(0).click()
  if (testInfo.project.name === 'mobile-375') await expect(page.locator('.activity-main')).toBeHidden()
  else await expect(page.locator('.activity-main')).toBeVisible()
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
})

test('normal report tab lists every generated report and allows re-entry', async ({ page }) => {
  const createdAt = '2026-07-20T03:00:00.000Z'
  const result = (runId: string, title: string, content: string, substationId: number) => ({
    schema_version: 'ops_agent_result.v4', run_id: runId, card_id: `card-${runId}`, evaluation_run_id: null,
    manufacturer_id: 'm1', substation_id: substationId, headline: title, situation: `${title} 상황`,
    evidence: [], actions: [{ priority: 1, title: '현장 확인', detail: '현장 상태를 확인합니다.' }], cautions: ['안전 절차 확인'],
    report: { title, format: 'markdown', content },
  })

  await page.route('**/api/agent-reports*', (route) => route.fulfill({ json: { items: [
    { artifact_id: 'artifact-report-a', run_id: 'run-report-a', kind: 'anomaly_report', name: 'report-a.md', uri: 'memory://report-a', priority: 'urgent', manufacturer_id: 'm1', substation_id: 28, substation_uid: 'substation-28', operator_review_status: 'approved', created_at: createdAt },
    { artifact_id: 'artifact-report-b', run_id: 'run-report-b', kind: 'anomaly_report', name: 'report-b.md', uri: 'memory://report-b', priority: 'high', manufacturer_id: 'm1', substation_id: 31, substation_uid: 'substation-31', operator_review_status: 'pending', created_at: createdAt },
  ], next_cursor: null, total_count: 2 } }))
  await page.route('**/api/agent-runs/run-report-a/result', (route) => route.fulfill({ json: result('run-report-a', '기계실 28 조치 보고서', '기계실 28 보고서 본문', 28) }))
  await page.route('**/api/agent-runs/run-report-b/result', (route) => route.fulfill({ json: result('run-report-b', '기계실 31 조치 보고서', '기계실 31 보고서 본문', 31) }))

  await openEntry(page)
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.getByRole('tab', { name: '보고서', exact: true })).toBeVisible()
  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(2)
  await page.getByRole('row', { name: /기계실 31/ }).click()
  await expect(page.getByRole('heading', { level: 2, name: '기계실 31 조치 보고서' })).toBeVisible()
  await expect(page.locator('.report-single-body')).toContainText('기계실 31 보고서 본문')

  await page.getByRole('button', { name: '홈', exact: true }).click()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(2)
})

test('normal refresh reloads active data without closing the current AI detail', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-375', '새로고침 버튼은 모바일 레이아웃에서 숨김')
  await openEntry(page)
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.locator('.activity-list-card tbody tr').first().click()
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()

  const refreshButton = page.getByRole('button', { name: '새로고침', exact: true })
  await refreshButton.click()
  await expect(refreshButton).not.toBeFocused()
  await expect(page.locator('.topbar-page-context')).toContainText('AI 조치')
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
})

test('normal chatbot keeps version history but separates other machine-room logs', async ({ page }) => {
  const createdAt = '2026-07-20T01:00:00.000Z'
  const baseResult = {
    schema_version: 'ops_agent_result.v4', run_id: 'run-normal', card_id: 'card-normal', evaluation_run_id: null,
    manufacturer_id: 'm1', substation_id: 11, headline: '기존 제목', situation: '기존 상황',
    evidence: [{ label: '기존 근거', content: '유지할 근거', source: 'manual' }],
    actions: [
      { priority: 1, title: '기존 작업 1', detail: '유지할 작업 절차 1' },
      { priority: 2, title: '기존 작업 2', detail: '유지할 작업 절차 2' },
    ],
    cautions: ['기존 안전 1', '기존 안전 2', '기존 안전 3'],
    report: { title: '기존 보고서', format: 'markdown', content: '기존 보고서 본문' },
  }
  const revisedResult = {
    ...baseResult,
    run_id: 'run-normal-child',
    situation: '바뀌면 안 되는 새 상황',
    actions: [{ priority: 1, title: '바뀌면 안 되는 새 작업', detail: '새 작업 절차' }],
    cautions: ['새 안전 1', '정전 작업용 보호구를 착용합니다.', '새 안전 3'],
  }
  const chatMessage = (id: string, role: 'operator' | 'assistant', content: string, sequence: number) => ({
    message_id: id, thread_id: 'thread-normal', sequence, role,
    message_kind: role === 'operator' ? 'action_request' : 'action_proposal', content, structured_payload: {}, citations: [],
    context_hash: 'context-normal', created_at: createdAt,
  })
  const serverMessages: ReturnType<typeof chatMessage>[] = Array.from({ length: 101 }, (_, index) => chatMessage(
    `history-normal-${index + 1}`,
    index === 0 ? 'operator' : 'assistant',
    index === 0 ? '작업 절차를 최신 기준으로 수정해줘' : `이전 검토 기록 ${index + 1}`,
    index + 1,
  ))
  let submittedMessageCount = 0
  let pendingNormalProposal: Record<string, unknown> | null = null

  await page.route('**/api/work-orders*', (route) => route.fulfill({ json: { items: [
    {
      run_id: 'run-normal', priority: 'high', alert_reason: '정상 테스트 작업지시서', manufacturer_id: 'm1',
      substation_id: 11, substation_uid: 'substation-11', operator_review_status: 'pending', created_at: createdAt,
    },
    {
      run_id: 'run-other-room', priority: 'medium', alert_reason: '다른 기계실 작업지시서', manufacturer_id: 'm1',
      substation_id: 29, substation_uid: 'substation-29', operator_review_status: 'pending', created_at: createdAt,
    },
  ], next_cursor: null, total_count: 2 } }))
  await page.route('**/api/agent-runs/run-normal/result', (route) => route.fulfill({ json: baseResult }))
  await page.route('**/api/agent-runs/run-other-room/result', (route) => route.fulfill({ json: { ...baseResult, run_id: 'run-other-room', headline: '다른 기계실 작업지시서' } }))
  await page.route('**/api/agent-runs/run-normal/review-chat/threads', (route) => route.fulfill({ json: {
    thread_id: 'thread-normal', run_id: 'run-normal', status: 'open', context_hash: 'context-normal', base_review_version: 0, created_at: createdAt,
  } }))
  await page.route('**/api/agent-runs/run-other-room/review-chat/threads', (route) => route.fulfill({ json: {
    thread_id: 'thread-other-room', run_id: 'run-other-room', status: 'open', context_hash: 'context-other-room', base_review_version: 0, created_at: createdAt,
  } }))
  await page.route('**/api/review-chat/threads/thread-other-room/messages*', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/review-chat/threads/thread-other-room/proposals/pending', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/review-chat/threads/thread-normal/proposals/pending', (route) => route.fulfill({ json: { items: pendingNormalProposal == null ? [] : [pendingNormalProposal] } }))
  await page.route('**/api/review-chat/threads/thread-normal/messages*', async (route) => {
    if (route.request().method() === 'GET') {
      const url = new URL(route.request().url())
      const limit = Number(url.searchParams.get('limit') ?? 100)
      const beforeSequence = Number(url.searchParams.get('before_sequence') ?? 0)
      const afterSequence = Number(url.searchParams.get('after_sequence') ?? 0)
      const items = beforeSequence > 0
        ? serverMessages.filter((item) => item.sequence < beforeSequence).slice(-limit)
        : afterSequence > 0
          ? serverMessages.filter((item) => item.sequence > afterSequence).slice(0, limit)
          : serverMessages.slice(-limit)
      await route.fulfill({ json: { items } })
      return
    }
    const body = route.request().postDataJSON() as { content: string }
    submittedMessageCount += 1
    const recallQuestion = body.content === '내가 요청한 수정사항이 뭐였지?'
    if (!recallQuestion) expect(body.content).toContain("'안전 확인 2번째 항목'만 수정")
    const nextSequence = (serverMessages.at(-1)?.sequence ?? 0) + 1
    const operatorMessage = chatMessage(`operator-normal-${submittedMessageCount}`, 'operator', body.content, nextSequence)
    const assistantMessage = chatMessage(`assistant-normal-${submittedMessageCount}`, 'assistant', recallQuestion ? '수정 요청을 확인했습니다.' : '부분 수정 제안을 만들었습니다.', nextSequence + 1)
    serverMessages.push(operatorMessage, assistantMessage)
    pendingNormalProposal = {
      proposal_id: `proposal-normal-${submittedMessageCount}`, thread_id: 'thread-normal', run_id: 'run-normal', expected_review_version: 0,
      context_hash: 'context-normal', status: 'awaiting_confirmation', decision: 'correct', next_action: 'targeted_rerun',
      reason: '안전 확인 항목 수정', reason_category: 'report_draft_issue', disposition: 'inspection_recommended',
      correction: { instruction: body.content }, target_stage: 'report_draft',
      revision: { target_area: 'safety_notes', safety_notes: ['기존 안전 1', '정전 작업용 보호구를 착용합니다.', '기존 안전 3'], change_summary: '안전 확인 2번째 항목의 보호구 기준을 갱신' },
      draft_content: '기존 제목\n\n1. 작업 목적\n기존 상황\n\n2. 작업 절차\n기존 작업 1\n기존 작업 2\n\n3. 안전 확인\n- 기존 안전 1\n- 정전 작업용 보호구를 착용합니다.\n- 기존 안전 3',
      change_summary: '안전 확인 2번째 항목의 보호구 기준을 갱신', expires_at: '2026-07-21T00:00:00.000Z',
    }
    await route.fulfill({ status: 202, json: {
      operator_message: operatorMessage,
      assistant_message: assistantMessage,
      proposal: pendingNormalProposal,
    } })
  })
  await page.route('**/api/review-chat/proposals/proposal-normal-1/confirm', (route) => {
    pendingNormalProposal = null
    return route.fulfill({ json: {
      proposal_id: 'proposal-normal-1', status: 'executed', review_id: 'review-normal', child_run_id: 'run-normal-child', target_stage: 'report_draft',
    } })
  })
  await page.route('**/api/review-chat/proposals/*/cancel', (route) => {
    const proposalId = route.request().url().split('/').at(-2) ?? 'proposal-normal'
    pendingNormalProposal = null
    return route.fulfill({ json: { proposal_id: proposalId, status: 'cancelled', review_id: null, child_run_id: null, target_stage: null } })
  })
  await page.route(/\/api\/agent-runs\/run-normal-child$/, (route) => route.fulfill({ json: { run_id: 'run-normal-child', status: 'completed', error: null } }))
  await page.route('**/api/agent-runs/run-normal-child/result', (route) => route.fulfill({ json: revisedResult }))

  await openEntry(page)
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '작업지시서' }).click()
  await page.getByRole('row', { name: /정상 테스트 작업지시서/ }).click()
  await page.getByRole('button', { name: '상세 보기' }).click()
  await expect(page.locator('.work-order-detail-body')).toHaveCSS('overflow-y', 'auto')
  await expect(page.locator('.work-order-detail-body .report-single-body')).toHaveCSS('overflow-y', 'auto')
  await expect(page.locator('.work-order-chat-log')).toContainText('작업 절차를 최신 기준으로 수정해줘')

  const chat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await chat.fill('안전 확인 2번째 항목만 정전 작업용 보호구 기준으로 수정해줘')
  await page.getByRole('button', { name: '수정 초안 요청' }).click()
  await expect(page.getByText('안전 확인 2번째 항목', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: '초안 확정 · v2 생성' }).click()

  await expect(page.getByRole('tab', { name: 'v2' })).toBeVisible()
  const document = page.locator('.activity-report-body')
  await expect(document).toContainText('정전 작업용 보호구를 착용합니다.')
  await expect(document).toContainText('기존 안전 1')
  await expect(document).toContainText('기존 안전 3')
  await expect(document).toContainText('기존 작업 1')
  await expect(document).not.toContainText('바뀌면 안 되는 새 작업')

  await page.getByRole('button', { name: '홈', exact: true }).click()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '작업지시서' }).click()
  await page.getByRole('row', { name: /정상 테스트 작업지시서/ }).click()
  await page.getByRole('button', { name: '상세 보기' }).click()
  await expect(page.getByRole('tab', { name: 'v2' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.activity-report-body')).toContainText('정전 작업용 보호구를 착용합니다.')
  await expect(page.locator('.work-order-review-chat')).toContainText('기계실 11 작업지시서 전용 대화입니다.')
  await expect(page.locator('.work-order-chat-log')).toContainText('안전 확인 2번째 항목만 정전 작업용 보호구 기준으로 수정해줘')

  const restoredChat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await restoredChat.fill('그 항목을 조금 더 짧게 정리해줘')
  await page.getByRole('button', { name: '수정 초안 요청' }).click()
  await expect(page.getByText('안전 확인 2번째 항목', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: '상세 닫기' }).click()
  await page.getByRole('button', { name: '미리보기 닫기' }).click()
  await page.getByRole('row', { name: /다른 기계실 작업지시서/ }).click()
  await page.getByRole('button', { name: '상세 보기' }).click()
  await expect(page.locator('.work-order-review-chat')).toContainText('기계실 29 작업지시서 전용 대화입니다.')
  await expect(page.locator('.work-order-chat-log')).toContainText('AI 검토 대화가 아직 없습니다.')
  await expect(page.locator('.work-order-chat-log')).not.toContainText('안전 확인 2번째 항목만 정전 작업용 보호구 기준으로 수정해줘')

  await page.evaluate(() => window.sessionStorage.removeItem('heatgrid:review-chat-pending:run-normal'))
  await page.getByRole('button', { name: '상세 닫기' }).click()
  await page.getByRole('button', { name: '미리보기 닫기' }).click()
  await page.getByRole('row', { name: /정상 테스트 작업지시서/ }).click()
  await page.getByRole('button', { name: '상세 보기' }).click()
  await expect(page.getByText('확정 전 수정 초안', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '초안 확정 · v3 생성' })).toBeVisible()
  await page.getByRole('button', { name: '초안 취소' }).click()
  const recallChat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await recallChat.fill('내가 요청한 수정사항이 뭐였지?')
  await page.getByRole('button', { name: '질문 보내기' }).click()
  await expect(page.locator('.work-order-chat-log')).toContainText('최근 문서 수정 요청은 다음과 같습니다.')
  await expect(page.locator('.work-order-chat-log')).toContainText('그 항목을 조금 더 짧게 정리해줘')
})

test('normal work-order list keeps the v1 root and restores server v2 only in detail', async ({ page }) => {
  const createdAt = '2026-07-20T02:00:00.000Z'
  const result = {
    schema_version: 'ops_agent_result.v4', run_id: 'run-root', card_id: 'card-root', evaluation_run_id: null,
    manufacturer_id: 'm1', substation_id: 29, headline: '원본 작업지시서', situation: '원본 상황',
    evidence: [], actions: [{ priority: 1, title: '원본 절차', detail: '원본 절차 상세' }], cautions: ['원본 안전 확인'],
    report: { title: '원본 보고서', format: 'markdown', content: '원본 보고서 본문' },
  }
  const workOrder = (runId: string, reason: string) => ({
    run_id: runId, priority: 'medium', alert_reason: reason, manufacturer_id: 'm1', substation_id: 29,
    substation_uid: 'substation-29', operator_review_status: 'pending', created_at: createdAt,
  })
  const runMetadata = (runId: string, triggerType: string) => ({
    run_id: runId, status: 'completed', trigger_type: triggerType, parent_run_id: triggerType === 'targeted_rerun' ? 'run-root' : null,
  })

  await page.route('**/api/work-orders*', (route) => route.fulfill({ json: { items: [
    workOrder('run-child-v2', '챗봇 수정으로 생성된 자식 실행'),
    workOrder('run-root', '목록에 남을 v1 작업지시서'),
  ], next_cursor: null, total_count: 2 } }))
  await page.route(/\/api\/agent-runs\/run-root$/, (route) => route.fulfill({ json: runMetadata('run-root', 'alert') }))
  await page.route(/\/api\/agent-runs\/run-child-v2$/, (route) => route.fulfill({ json: runMetadata('run-child-v2', 'targeted_rerun') }))
  await page.route('**/api/agent-runs/run-root/result', (route) => route.fulfill({ json: result }))
  await page.route('**/api/agent-runs/run-root/review-chat/threads', (route) => route.fulfill({ json: {
    thread_id: 'thread-root', run_id: 'run-root', status: 'open', context_hash: 'context-root', base_review_version: 0,
    created_at: createdAt, incident_id: 'incident-root', document_version_id: 'document-root-v2', document_version: 2,
    document_content: '서버에서 복원된 v2 본문',
  } }))
  await page.route('**/api/review-chat/threads/thread-root/messages*', (route) => route.fulfill({ json: { items: [{
    message_id: 'message-root', thread_id: 'thread-root', sequence: 1, role: 'operator', message_kind: 'action_request',
    content: '상세에서만 보여야 하는 수정 요청', structured_payload: {}, citations: [], context_hash: 'context-root', created_at: createdAt,
  }] } }))
  await page.route('**/api/review-chat/threads/thread-root/proposals/pending', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/incidents/incident-root/documents', (route) => route.fulfill({ json: { items: [
    {
      document_version_id: 'document-root-v1', episode_id: 'incident-root', document_type: 'work_order', version: 1,
      parent_document_version_id: null, status: 'ai_reviewed', review_state: 'operator_noted', retryable: false,
      content: { title: '원본 작업지시서', body: '서버 v1 본문', actions: ['원본 절차'], evidence: [], safety_notes: ['원본 안전 확인'] },
      content_hash: 'document-root-v1-hash', created_by: 'ai', created_at: createdAt, approved_by: null, approved_at: null,
    },
    {
      document_version_id: 'document-root-v2', episode_id: 'incident-root', document_type: 'work_order', version: 2,
      parent_document_version_id: 'document-root-v1', status: 'ai_reviewed', review_state: 'operator_noted', retryable: false,
      content: { title: '수정된 작업지시서', body: '서버에서 복원된 v2 본문', actions: ['수정 절차'], evidence: [], safety_notes: ['수정 안전 확인'] },
      content_hash: 'document-root-v2-hash', created_by: 'ai', created_at: createdAt, approved_by: null, approved_at: null,
    },
  ] } }))

  await openEntry(page)
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '작업지시서' }).click()
  await expect(page.getByRole('row', { name: /목록에 남을 v1 작업지시서/ })).toBeVisible()
  await expect(page.getByRole('row', { name: /챗봇 수정으로 생성된 자식 실행/ })).toHaveCount(0)
  await expect(page.locator('.activity-list-card tbody tr')).toHaveCount(1)

  await page.getByRole('row', { name: /목록에 남을 v1 작업지시서/ }).click()
  await page.getByRole('button', { name: '상세 보기' }).click()
  await expect(page.getByRole('tab', { name: 'v2' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.activity-report-body')).toContainText('서버에서 복원된 v2 본문')
  await expect(page.locator('.work-order-chat-log')).toContainText('상세에서만 보여야 하는 수정 요청')
  await expect(page.locator('.activity-list-card')).not.toContainText('상세에서만 보여야 하는 수정 요청')
})

test('fault AI action keeps one list item and restores detail versions and chat', async ({ page }, testInfo) => {
  await page.addInitScript((session) => {
    window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session))
  }, {
    mode: 'fault',
    entryStep: 'console',
    selectedAlertId: 'scenario-alert-pump-28',
    selectedSubstationId: 28,
    incidentState: 'incident-active',
    documentAlertId: 'scenario-alert-pump-28',
    workOrders: [
      { version: 1, createdAt: '2026-07-20T00:00:00.000Z', changeSummary: 'AI 초안 생성', content: '세션에서 복원된 v1 본문' },
      { version: 2, createdAt: '2026-07-20T00:01:00.000Z', changeSummary: '안전 절차 보강', content: '세션에서 복원된 v2 본문' },
    ],
    selectedWorkOrderVersion: 2,
    acceptedWorkOrderVersion: null,
    workOrderRerunCount: 1,
    messages: [{ id: 'restored-chat-v2', role: 'operator', content: '목록에는 숨기고 상세에서만 보일 대화', createdAt: '2026-07-20T00:01:30.000Z', workOrderVersion: 2 }],
    report: { status: 'idle', createdAt: null, savedAt: null, completedAt: null, content: '' },
    reportMessages: [],
  })
  await page.goto('/?devtools=0')

  const expectRestoredVersion = async () => {
    await expect(page.getByRole('tab', { name: '작업지시서' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tab', { name: 'v2' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText('세션에서 복원된 v2 본문')).toBeVisible()
    await expect(page.locator('.scenario-version-entry')).toHaveCount(1)
    await expect(page.locator('.scenario-version-entry > button > span').first()).toHaveText('v1')
    await expect(page.locator('.scenario-version-thread')).toHaveCount(0)
    await expect(page.locator('.scenario-version-list')).not.toContainText('목록에는 숨기고 상세에서만 보일 대화')
    await expect(page.locator('.scenario-chat-messages')).toContainText('목록에는 숨기고 상세에서만 보일 대화')
  }

  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expectRestoredVersion()
  await page.getByRole('button', { name: '홈', exact: true }).click()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expectRestoredVersion()

  if (testInfo.project.name !== 'mobile-375') {
    await page.getByRole('button', { name: '새로고침', exact: true }).click()
    await expectRestoredVersion()
  }

  await page.reload()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expectRestoredVersion()
})

test('fault chatbot changes only the requested item and keeps version conversation', async ({ page }) => {
  const createdAt = '2026-07-20T00:00:00.000Z'
  let partialMessageCount = 0
  let pendingPartialProposal: Record<string, unknown> | null = null
  const message = (id: string, role: 'operator' | 'assistant', content: string, sequence: number) => ({
    message_id: id,
    thread_id: 'thread-partial',
    sequence,
    role,
    message_kind: role === 'operator' ? 'action_request' : 'proposal',
    content,
    structured_payload: {},
    citations: [],
    context_hash: 'context-partial',
    created_at: createdAt,
  })

  await page.route('**/api/agent-runs/run-base/review-chat/threads', (route) => route.fulfill({ json: {
    thread_id: 'thread-partial', run_id: 'run-base', status: 'open', context_hash: 'context-partial', base_review_version: 0, created_at: createdAt,
  } }))
  await page.route('**/api/review-chat/threads/thread-partial/proposals/pending', (route) => route.fulfill({ json: { items: pendingPartialProposal == null ? [] : [pendingPartialProposal] } }))
  await page.route('**/api/review-chat/threads/thread-partial/messages*', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { items: [] } })
      return
    }
    const body = route.request().postDataJSON() as { content: string }
    partialMessageCount += 1
    expect(body.content).toContain("'안전 확인 2번째 항목'만 수정")
    expect(body.content).toContain(partialMessageCount === 1 ? '최신 보호구 기준으로 수정해줘' : '그 항목을 조금 더 짧게 정리해줘')
    pendingPartialProposal = {
      proposal_id: `proposal-partial-${partialMessageCount}`, thread_id: 'thread-partial', run_id: 'run-base', expected_review_version: 0,
      context_hash: 'context-partial', status: 'awaiting_confirmation', decision: 'correct', next_action: 'targeted_rerun',
      reason: '안전 확인 항목 수정', reason_category: 'report_draft_issue', disposition: 'inspection_recommended',
      correction: { instruction: body.content }, target_stage: 'report_draft',
      revision: { target_area: 'safety_notes', safety_notes: ['기존 안전 확인 1', '최신 보호구 기준 반영 문장', '기존 안전 확인 3'], change_summary: '안전 확인 2번째 항목만 최신 보호구 기준으로 변경' },
      draft_content: '기존 작업지시서 v1\n\n위험성 및 근거\n기존 상황 요약\n기존 판단 근거\n운영자 수동 보완 문장\n\n작업 절차\n기존 작업 절차 1\n기존 작업 절차 2\n\n안전 확인\n기존 안전 확인 1\n최신 보호구 기준 반영 문장\n기존 안전 확인 3',
      change_summary: '안전 확인 2번째 항목만 최신 보호구 기준으로 변경', expires_at: '2026-07-21T00:00:00.000Z',
    }
    await route.fulfill({ status: 202, json: {
      operator_message: message(`operator-partial-${partialMessageCount}`, 'operator', body.content, partialMessageCount * 2 - 1),
      assistant_message: message(`assistant-partial-${partialMessageCount}`, 'assistant', '지정한 항목의 수정 제안을 만들었습니다.', partialMessageCount * 2),
      proposal: pendingPartialProposal,
    } })
  })
  await page.route('**/api/review-chat/proposals/proposal-partial-1/confirm', (route) => {
    pendingPartialProposal = null
    return route.fulfill({ json: {
      proposal_id: 'proposal-partial-1', status: 'executed', review_id: 'review-partial', child_run_id: null, target_stage: 'report_draft',
      rerun_status: 'blocked_legacy_input_unavailable', blocked_reason: 'blocked_legacy_input_unavailable',
      incident_id: 'incident-partial', document_version_id: 'document-partial-v2', document_version: 2,
      document_content: {
        title: '기존 작업지시서 v1',
        body: '기존 작업지시서 v1\n\n위험성 및 근거\n기존 상황 요약\n기존 판단 근거\n운영자 수동 보완 문장\n\n작업 절차\n기존 작업 절차 1\n기존 작업 절차 2\n\n안전 확인\n기존 안전 확인 1\n최신 보호구 기준 반영 문장\n기존 안전 확인 3',
        actions: ['기존 작업 절차 1', '기존 작업 절차 2'], evidence: [], safety_notes: ['기존 안전 확인 1', '최신 보호구 기준 반영 문장', '기존 안전 확인 3'],
      },
    } })
  })
  await page.route('**/api/incidents/incident-partial/documents', (route) => route.fulfill({ json: { items: [{
    document_version_id: 'document-partial-v2', episode_id: 'incident-partial', document_type: 'work_order', version: 2,
    parent_document_version_id: null, status: 'ai_reviewed', review_state: 'operator_noted', retryable: false,
    content: { title: '기존 작업지시서 v1', body: '기존 작업지시서 v1\n\n안전 확인\n기존 안전 확인 1\n최신 보호구 기준 반영 문장\n기존 안전 확인 3', actions: ['기존 작업 절차 1', '기존 작업 절차 2'], evidence: [], safety_notes: '기존 안전 확인 1\n최신 보호구 기준 반영 문장\n기존 안전 확인 3' },
    content_hash: 'document-partial-v2-hash', created_by: 'ai', created_at: createdAt, approved_by: null, approved_at: null,
  }] } }))
  await page.route(/\/api\/agent-runs\/run-child$/, (route) => route.fulfill({ json: { run_id: 'run-child', status: 'completed', error: null } }))
  await page.route('**/api/agent-runs/run-child/result', (route) => route.fulfill({ json: {
    schema_version: 'ops_agent_result.v4', run_id: 'run-child', card_id: 'card-child', evaluation_run_id: null,
    manufacturer_id: 'm1', substation_id: 28, headline: '새 전체 제목', situation: '새로 생성된 상황 요약',
    evidence: [{ label: '새 근거', content: '새로 생성된 근거', source: 'manual' }],
    actions: [{ priority: 1, title: '새 작업 절차', detail: '전체 재생성 결과의 작업 절차' }],
    cautions: ['새 안전 확인 1', '최신 보호구 기준 반영 문장', '새 안전 확인 3'],
    report: { title: '새 보고서', format: 'markdown', content: '새 보고서 본문' },
  } }))

  await page.addInitScript((session) => {
    if (window.sessionStorage.getItem('heatgrid:scenario-session') == null) window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session))
  }, {
    mode: 'fault', entryStep: 'console', selectedAlertId: 'scenario-alert-pump-28', selectedSubstationId: 28,
    incidentState: 'incident-active', documentAlertId: 'scenario-alert-pump-28',
    workOrders: [{
      version: 1, createdAt, title: '기존 작업지시서 v1', changeSummary: 'AI 초안 생성', sourceRunId: 'run-base',
      revisionInstruction: null, baseVersion: null,
      sections: [
        { title: '위험성 및 근거', items: ['기존 상황 요약', '기존 판단 근거'] },
        { title: '작업 절차', items: ['기존 작업 절차 1', '기존 작업 절차 2'] },
        { title: '안전 확인', items: ['기존 안전 확인 1', '기존 안전 확인 2', '기존 안전 확인 3'] },
      ],
      content: '기존 작업지시서 v1\n\n위험성 및 근거\n기존 상황 요약\n기존 판단 근거\n운영자 수동 보완 문장\n\n작업 절차\n기존 작업 절차 1\n기존 작업 절차 2\n\n안전 확인\n기존 안전 확인 1\n기존 안전 확인 2\n기존 안전 확인 3',
    }],
    selectedWorkOrderVersion: 1, acceptedWorkOrderVersion: null, workOrderRerunCount: 0, messages: [],
    report: { status: 'idle', createdAt: null, savedAt: null, completedAt: null, content: '' }, reportMessages: [],
  })
  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.locator('.scenario-order-document')).toHaveCSS('display', 'grid')
  await expect(page.locator('.scenario-order-body')).toHaveCSS('overflow-y', 'auto')

  const chat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await chat.fill('안전 확인 2번째 항목만 최신 보호구 기준으로 수정해줘')
  await page.getByRole('button', { name: '수정 초안 요청' }).click()
  await expect(page.getByText('안전 확인 2번째 항목', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('지정 부분 외 모두 유지', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '초안 확정 · v2 생성' }).click()

  await expect(page.getByRole('tab', { name: 'v2' })).toBeVisible()
  await expect(page.getByText(/문서는 저장됐고 근거 재평가는 생략되었습니다/).first()).toBeVisible()
  const document = page.locator('.scenario-document-content')
  await expect(document).toContainText('최신 보호구 기준 반영 문장')
  await expect(document).toContainText('기존 안전 확인 1')
  await expect(document).toContainText('기존 안전 확인 3')
  await expect(document).toContainText('기존 작업 절차 1')
  await expect(document).toContainText('기존 판단 근거')
  await expect(document).toContainText('운영자 수동 보완 문장')
  await expect(document).not.toContainText('새 작업 절차')
  await expect(document).not.toContainText('새로 생성된 상황 요약')
  await expect(page.locator('.scenario-chat-source')).toContainText('기계실 28 · 선택 v2')
  await expect(page.locator('.scenario-chat-source')).toContainText('이 기계실 작업지시서 전용 대화입니다.')
  await expect(page.locator('.scenario-chat-messages')).toContainText('안전 확인 2번째 항목만 최신 보호구 기준으로 수정해줘')
  await expect(page.locator('.scenario-version-entry')).toHaveCount(1)
  await expect(page.locator('.scenario-version-entry > button > span').first()).toHaveText('v1')
  await expect(page.locator('.scenario-version-thread')).toHaveCount(0)
  await expect(page.locator('.scenario-version-list')).not.toContainText('안전 확인 2번째 항목만 최신 보호구 기준으로 수정해줘')

  await page.reload()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'v2' })).toBeVisible()
  await expect(page.locator('.scenario-document-content')).toContainText('최신 보호구 기준 반영 문장')
  await expect(page.locator('.scenario-chat-source')).toContainText('기계실 28 · 선택 v2')
  await expect(page.locator('.scenario-chat-messages')).toContainText('안전 확인 2번째 항목만 최신 보호구 기준으로 수정해줘')

  const restoredChat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await restoredChat.fill('그 항목을 조금 더 짧게 정리해줘')
  await page.getByRole('button', { name: '수정 초안 요청' }).click()
  await expect(page.getByText('안전 확인 2번째 항목', { exact: true }).first()).toBeVisible()
})

test('fault AI analysis creation appends a new work order and report group', async ({ page }) => {
  const createdAt = '2026-07-20T03:30:00.000Z'
  const existingOrder = {
    version: 1, createdAt, title: '기계실 28 작업지시서 v1', changeSummary: 'AI 초안 생성', sourceRunId: 'run-existing-28',
    revisionInstruction: null, baseVersion: null,
    sections: [{ title: '위험성 및 근거', items: ['기존 위험 근거'] }, { title: '작업 절차', items: ['기존 작업 절차'] }, { title: '안전 확인', items: ['기존 안전 확인'] }],
    content: '기존 작업지시서 본문',
  }
  const existingGroup = {
    id: 'run-existing-28', rootRunId: 'run-existing-28', alertId: 'scenario-alert-pump-28', substationId: 28, createdAt,
    workOrders: [existingOrder], selectedWorkOrderVersion: 1, acceptedWorkOrderVersion: 1, workOrderRerunCount: 0,
    messages: [], proposal: null, evaluationRequired: false, improvementCandidate: null,
    report: { status: 'completed', createdAt, savedAt: createdAt, completedAt: createdAt, content: '기존 보고서 본문' }, reportMessages: [],
  }
  const newResult = {
    schema_version: 'ops_agent_result.v4', run_id: 'run-new-31', card_id: 'card-new-31', evaluation_run_id: null,
    manufacturer_id: 'm1', substation_id: 31, headline: '새 기계실 분석', situation: '새 기계실 이상 상황',
    evidence: [{ label: '근거', content: '새 기계실 판단 근거', source: 'manual' }],
    actions: [{ priority: 1, title: '새 작업', detail: '새 기계실 작업 절차' }], cautions: ['새 기계실 안전 확인'],
    report: { title: '새 기계실 분석 보고서', format: 'markdown', content: '새 분석 보고서 본문' },
  }

  await page.route(/\/api\/agent-runs(?:\?.*)?$/, (route) => route.fulfill({ json: { items: [{
    run_id: 'run-new-31', status: 'completed', trigger_type: 'alert', parent_run_id: null, priority: 'urgent', alert_reason: '새 기계실 분석',
    manufacturer_id: 'm1', substation_id: 31, substation_uid: 'substation-31', operator_review_status: 'pending', created_at: createdAt,
  }], next_cursor: null, total_count: 1 } }))
  await page.route(/\/api\/agent-runs\/run-new-31$/, (route) => route.fulfill({ json: { run_id: 'run-new-31', status: 'completed', error: null } }))
  await page.route('**/api/agent-runs/run-new-31/review', (route) => route.fulfill({ json: { snapshot: null } }))
  await page.route('**/api/agent-runs/run-new-31/result', (route) => route.fulfill({ json: newResult }))
  await page.addInitScript((session) => window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session)), {
    mode: 'fault', entryStep: 'console', selectedAlertId: existingGroup.alertId, selectedSubstationId: 28,
    incidentState: 'incident-active', documentGroups: [existingGroup], activeDocumentGroupId: existingGroup.id,
  })

  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: 'AI 분석 목록', exact: true }).click()
  await page.getByRole('row', { name: /새 기계실 분석/ }).click()
  await page.getByRole('button', { name: '작업지시서 생성', exact: true }).click()
  await expect(page.getByRole('tab', { name: '작업지시서', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.scenario-version-entry')).toHaveCount(2)
  await expect(page.locator('.scenario-document-content')).toContainText('새 기계실 작업 절차')

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '선택 버전 최종 채택', exact: true }).click()
  await page.getByRole('button', { name: '보고서 생성', exact: true }).click()
  await expect(page.getByRole('tab', { name: '보고서', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.scenario-report-list .scenario-version-entry')).toHaveCount(2)
})

test('fault work orders and reports remain grouped by root run and can be reopened', async ({ page }) => {
  const createdAt = '2026-07-20T04:00:00.000Z'
  const workOrder = (runId: string, room: number, marker: string) => ({
    version: 1, createdAt, title: `기계실 ${room} 작업지시서 v1`, changeSummary: 'AI 초안 생성', sourceRunId: runId,
    revisionInstruction: null, baseVersion: null,
    sections: [
      { title: '위험성 및 근거', items: [`${marker} 위험 근거`] },
      { title: '작업 절차', items: [`${marker} 작업 절차`] },
      { title: '안전 확인', items: [`${marker} 안전 확인`] },
    ],
    content: `${marker} 작업지시서 본문`,
  })
  const group = (id: string, alertId: string, room: number, marker: string) => ({
    id, rootRunId: id, alertId, substationId: room, createdAt,
    workOrders: [workOrder(id, room, marker)], selectedWorkOrderVersion: 1, acceptedWorkOrderVersion: 1,
    workOrderRerunCount: 0, messages: [], proposal: null, evaluationRequired: false, improvementCandidate: null,
    report: { status: 'completed', createdAt, savedAt: createdAt, completedAt: createdAt, content: `${marker} 보고서 본문` },
    reportMessages: [],
  })
  const first = group('run-group-28', 'scenario-alert-pump-28', 28, '첫 번째')
  const second = group('run-group-31', 'scenario-alert-leak-31', 31, '두 번째')

  await page.addInitScript((session) => window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify(session)), {
    mode: 'fault', entryStep: 'console', selectedAlertId: first.alertId, selectedSubstationId: 28,
    incidentState: 'incident-active', documentGroups: [first, second], activeDocumentGroupId: first.id,
  })
  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()

  await expect(page.getByRole('tab', { name: '작업지시서', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.scenario-version-entry')).toHaveCount(2)
  await page.getByRole('button', { name: '기계실 31 작업지시서 v1 상세 열기' }).click()
  await expect(page.locator('.scenario-document-content')).toContainText('두 번째 작업지시서 본문')

  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.scenario-report-list .scenario-version-entry')).toHaveCount(2)
  await expect(page.locator('.scenario-report-content')).toContainText('두 번째 보고서 본문')
  await page.getByRole('button', { name: '기계실 28 작업지시서 v1 보고서 상세 열기' }).click()
  await expect(page.locator('.scenario-report-content')).toContainText('첫 번째 보고서 본문')

  await page.getByRole('button', { name: '홈', exact: true }).click()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '보고서', exact: true }).click()
  await expect(page.locator('.scenario-report-list .scenario-version-entry')).toHaveCount(2)
  await expect(page.locator('.scenario-report-content')).toContainText('첫 번째 보고서 본문')

  await page.reload()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.locator('.scenario-version-entry')).toHaveCount(2)
})

test('fault incident starts after five seconds and selects the matching sensor room', async ({ page }) => {
  await startFaultScenario(page)
  await expect(page.locator('.metric-grid-five > *')).toHaveCount(5)
  await waitForIncident(page)
  await expect(page.getByRole('status', { name: '우선순위 1 경보' })).toBeVisible()
  await expect(page.getByRole('status', { name: '우선순위 1 경보' })).toContainText('범지기마을')
  await expect(page.getByText('urgent', { exact: true }).first()).toBeVisible()
  await expect(page.locator('.sensor-tile.sf-return')).toHaveCount(0)
  await dismissIncidentToasts(page)

  await page.getByRole('button', { name: /열교환기 외부 누수 의심/ }).click()
  await expect(page.locator('.sensor-flow').getByText(/기계실 31/)).toBeVisible()
  await expectNoPageScroll(page)
})

test('alerts start as a list and analysis completion offers an AI action shortcut', async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  await startFaultScenario(page)
  await waitForIncident(page)
  await dismissIncidentToasts(page)
  await page.getByRole('button', { name: '자세히 보기', exact: true }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: '우선순위' })).toBeVisible()
  await page.getByRole('combobox', { name: '우선순위' }).selectOption('urgent')
  await expect(page.locator('.alerts-table tbody tr')).toHaveCount(2)
  await page.getByRole('combobox', { name: '우선순위' }).selectOption('all')

  await openAlertDetail(page, /환수온도 급락 및 난방 순환펌프 이상/)
  await expect(page.getByRole('heading', { name: '상세 정보' })).toBeVisible()
  const evidenceChart = page.getByRole('region', { name: '환수온도 이상 시계열' })
  await expect(evidenceChart).toBeVisible()
  await expect(evidenceChart).toHaveCSS('background-image', 'none')
  await expect.poll(() => evidenceChart.locator('.scenario-evidence-point').first().evaluate((point) => getComputedStyle(point).vectorEffect)).toBe('non-scaling-stroke')
  await expect(page.getByRole('heading', { name: '환수온도 이상 감지' })).toBeVisible()
  await page.getByRole('button', { name: '상세 정보 닫기' }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toHaveCount(0)
  await openAlertDetail(page, /환수온도 급락 및 난방 순환펌프 이상/)
  await page.getByRole('button', { name: 'AI 조치 바로가기' }).click()
  const analysisProgress = page.getByRole('status')
  await expect(analysisProgress).toContainText('기존 예측 결과 확인중')
  await expect(analysisProgress).toContainText('계획서 정리중')
  await expect(analysisProgress).not.toContainText('예측 모델 검토중')
  await expect(analysisProgress.getByRole('button', { name: 'AI 조치에서 진행 보기' })).toBeVisible()
  const aiShortcut = page.getByRole('button', { name: '완료된 AI 조치 열기' })
  await expect(aiShortcut).toBeVisible({ timeout: 75_000 })
  await expect.poll(() => aiShortcut.evaluate((button) => button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(50)
  await aiShortcut.click()
  await expect(page.locator('.topbar-page-context')).toContainText('AI 조치')
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
  await expect(page.getByRole('button', { name: '작업지시서 생성' })).toBeVisible()
  if (testInfo.project.name === 'mobile-375') {
    await expect(page.locator('.activity-main')).toBeHidden()
    await expect(page.getByRole('columnheader', { name: '대상' })).toBeHidden()
  } else {
    await expect(page.locator('.activity-main')).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '대상' })).toBeVisible()
  }
  await expect(page.getByRole('tab', { name: '실행 추적' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: '재실행' })).toHaveCount(0)
  await expectNoPageScroll(page)
})

test('refresh resets the fault scenario and returns to the initial dashboard', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-375', '새로고침 버튼은 모바일 레이아웃에서 숨김')
  await startFaultScenario(page)
  await waitForIncident(page)
  await page.getByRole('status', { name: '우선순위 1 경보' }).getByRole('button', { name: '알림 상세 열기' }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toBeVisible()

  const refreshButton = page.getByRole('button', { name: '새로고침', exact: true })
  await refreshButton.click()
  await expect(refreshButton).not.toBeFocused()
  await expect(page.locator('.topbar-page-context')).toContainText('홈')
  await expect(page.locator('.topbar-clock strong')).toHaveText('14:50')
  await expect(page.getByText('현재 주요 알림 없음', { exact: true })).toBeVisible()
  await expect(page.getByRole('row', { name: /환수온도 급락 및 난방 순환펌프 이상/ })).toHaveCount(0)
})

test('incident document flow supports edits, two AI reruns, adoption, report completion and PDF names', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-375', '전체 문서 편집 흐름은 데스크톱에서 검증')
  test.setTimeout(240_000)
  await startFaultScenario(page)
  await waitForIncident(page)
  await dismissIncidentToasts(page)
  await page.getByRole('button', { name: '자세히 보기', exact: true }).click()
  await openAlertDetail(page, /환수온도 급락 및 난방 순환펌프 이상/)
  await page.getByRole('button', { name: 'AI 조치 바로가기' }).click()
  await page.getByRole('button', { name: '완료된 AI 조치 열기' }).click({ timeout: 75_000 })

  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
  await page.getByRole('button', { name: '작업지시서 생성' }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'v1' })).toBeVisible()
  const orderHeader = page.locator('.scenario-order-document .surface-heading')
  const documentToolbar = page.locator('.scenario-document-toolbar')
  await expect(orderHeader).toBeVisible()
  await expect(documentToolbar).toBeVisible()
  await expect.poll(async () => {
    const header = await orderHeader.boundingBox()
    const toolbar = await documentToolbar.boundingBox()
    return header != null && toolbar != null && header.y + header.height <= toolbar.y
  }).toBe(true)

  const directEditButton = page.getByRole('button', { name: '세션 본문 직접 편집', exact: true })
  if (await directEditButton.count()) {
    await directEditButton.click()
    const orderEditor = page.getByRole('textbox', { name: '작업지시서 본문 편집' })
    await orderEditor.fill(`${await orderEditor.inputValue()}\n운영자 직접 수정 문장`)
    await page.getByRole('button', { name: '세션 편집 저장', exact: true }).click()
    await expect(page.getByText('운영자 직접 수정 문장')).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: '서버 정본은 AI 수정 사용', exact: true })).toBeVisible()
  }

  const orderDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'PDF 다운로드' }).click()
  await expect((await orderDownload).suggestedFilename()).toMatch(/^heatgrid-work-order-HG-\d{8}-\d+-v1-v1\.pdf$/)

  const chat = page.getByRole('textbox', { name: '문서 질문 또는 수정 요청' })
  await chat.fill('최신 RAG 문서로 안전 절차를 다시 작성해줘')
  await page.getByRole('button', { name: '수정 초안 요청' }).click()
  await expect(page.getByText('확정 전 수정 초안', { exact: true })).toBeVisible()
  await expect(page.locator('.scenario-chat')).not.toContainText('**')
  await page.getByRole('button', { name: '초안 확정 · v2 생성' }).click()
  const v2Tab = page.getByRole('tab', { name: 'v2' })
  const existingVersionLimit = page.getByRole('alert').filter({ hasText: 'document_version_limit_reached' })
  await expect(v2Tab.or(existingVersionLimit)).toBeVisible({ timeout: 5_000 })
  test.skip(await existingVersionLimit.isVisible(), '공유 테스트 서버의 해당 incident가 이미 v3 한도에 도달함')
  await chat.fill('외부 기상 데이터를 다시 확인해서 현장 절차를 보강해줘')
  await page.getByRole('button', { name: '수정 초안 요청' }).click()
  await page.getByRole('button', { name: '초안 확정 · v3 생성' }).click()
  await expect(page.getByRole('tab', { name: 'v3' })).toBeVisible({ timeout: 5_000 })
  await expect(chat).toBeEnabled()
  await expect(page.getByText(/AI 문서 수정 2회를 모두 사용했습니다/)).toBeVisible()

  await page.getByRole('button', { name: '홈', exact: true }).click()
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.getByRole('tab', { name: '작업지시서' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tab', { name: 'v3' })).toBeVisible()

  await page.getByRole('tab', { name: 'v2' }).click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '선택 버전 최종 채택', exact: true }).click()
  await expect(page.getByText('이 버전이 보고서 생성 기준입니다.')).toBeVisible()
  await page.getByRole('button', { name: '보고서 생성' }).click()
  await expect(page.getByRole('heading', { name: '보고서 상세' })).toBeVisible()

  const reportChat = page.getByRole('textbox', { name: '검토 메모' })
  await reportChat.fill('현장 인계 전에 빠진 확인 항목을 검토해줘')
  await page.getByRole('button', { name: '메모 저장', exact: true }).click()
  await expect(page.getByText('현장 인계 전에 빠진 확인 항목을 검토해줘')).toBeVisible()

  const reportEditor = page.getByRole('textbox', { name: '보고서 본문 편집' })
  await reportEditor.fill(`${await reportEditor.inputValue()}\n운영자 최종 확인 완료`)
  await page.getByRole('button', { name: '임시 저장' }).click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '완료', exact: true }).click()
  await expect(page.getByText('운영자 최종 확인 완료')).toBeVisible()
  const reportDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'PDF 저장' }).click()
  await expect((await reportDownload).suggestedFilename()).toMatch(/^heatgrid-report-.+-\d{4}-\d{2}-\d{2}\.pdf$/)
})
