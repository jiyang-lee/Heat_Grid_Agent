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

test('normal AI action entry opens the plan list without a selected detail', async ({ page }) => {
  await openEntry(page)
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'AI 분석 목록' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.activity-list-card')).toBeVisible()
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: '대상' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '현재 단계' })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: '결과' })).toHaveCount(0)

  const planRows = page.locator('.activity-list-card tbody tr')
  await expect(planRows).toHaveCount(3)
  await planRows.nth(0).click()
  await expect(page.locator('.activity-main')).toBeVisible()
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
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

test('alerts start as a list and analysis completion offers an AI action shortcut', async ({ page }) => {
  test.setTimeout(60_000)
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
  const aiShortcut = page.getByRole('button', { name: 'AI 조치 바로가기' })
  await expect(aiShortcut).toBeVisible({ timeout: 45_000 })
  await expect.poll(() => aiShortcut.evaluate((button) => button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(50)
  await aiShortcut.click()
  await expect(page.locator('.topbar-page-context')).toContainText('AI 조치')
  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
  await expect(page.getByRole('button', { name: '작업지시서 생성' })).toBeVisible()
  await expect(page.locator('.activity-main')).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '대상' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '실행 추적' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: '재실행' })).toHaveCount(0)
  await expectNoPageScroll(page)
})

test('refresh keeps the current page and clears resolved alerts', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-375', '새로고침 버튼은 모바일 레이아웃에서 숨김')
  await startFaultScenario(page)
  await waitForIncident(page)
  await page.getByRole('status', { name: '우선순위 1 경보' }).getByRole('button', { name: '알림 상세 열기' }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '종결', exact: true }).click()
  await expect(page.getByText('종결', { exact: true }).first()).toBeVisible()
  const frozenChart = page.locator('.scenario-evidence-line')
  const frozenPoints = await frozenChart.getAttribute('points')
  await page.waitForTimeout(5_500)
  await expect(frozenChart).toHaveAttribute('points', frozenPoints ?? '')

  const refreshButton = page.getByRole('button', { name: '새로고침', exact: true })
  await refreshButton.click()
  await expect(refreshButton).not.toBeFocused()
  await expect(page.locator('.topbar-page-context')).toContainText('알림')
  await expect(page.locator('.topbar-clock strong')).toHaveText('12:00')
  await expect(page.getByRole('combobox', { name: '표시 범위' })).toHaveValue('active')
  await expect(page.getByRole('row', { name: /환수온도 급락 및 난방 순환펌프 이상/ })).toBeVisible({ timeout: 12_000 })
  await expect(page.getByText('종결', { exact: true })).toHaveCount(0)
})

test('incident document flow supports edits, two AI reruns, adoption, report completion and PDF names', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-375', '전체 문서 편집 흐름은 데스크톱에서 검증')
  test.setTimeout(120_000)
  await startFaultScenario(page)
  await waitForIncident(page)
  await dismissIncidentToasts(page)
  await page.getByRole('button', { name: '자세히 보기', exact: true }).click()
  await openAlertDetail(page, /환수온도 급락 및 난방 순환펌프 이상/)
  await page.getByRole('button', { name: 'AI 조치 바로가기' }).click()
  await page.getByRole('button', { name: 'AI 조치 바로가기' }).click({ timeout: 45_000 })

  await expect(page.getByRole('heading', { name: '계획서 상세' })).toBeVisible()
  await page.getByRole('button', { name: '작업지시서 생성' }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'v1' })).toBeVisible()
  const orderHeader = page.locator('.scenario-order-document .ops-surface-header')
  const documentToolbar = page.locator('.scenario-document-toolbar')
  await expect(orderHeader).toBeVisible()
  await expect(documentToolbar).toBeVisible()
  await expect.poll(async () => {
    const header = await orderHeader.boundingBox()
    const toolbar = await documentToolbar.boundingBox()
    return header != null && toolbar != null && header.y + header.height <= toolbar.y
  }).toBe(true)

  await page.getByRole('button', { name: '수정', exact: true }).click()
  const orderEditor = page.getByRole('textbox', { name: '작업지시서 본문 편집' })
  await orderEditor.fill(`${await orderEditor.inputValue()}\n운영자 직접 수정 문장`)
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByText('운영자 직접 수정 문장')).toBeVisible()

  const orderDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'PDF 다운로드' }).click()
  await expect((await orderDownload).suggestedFilename()).toMatch(/^heatgrid-work-order-HG-\d{8}-\d+-v1-v1\.pdf$/)

  const chat = page.getByRole('textbox', { name: '수정 요청' })
  await chat.fill('최신 RAG 문서로 안전 절차를 다시 작성해줘')
  await page.getByRole('button', { name: '제안 확인' }).click()
  await expect(page.getByText('수정 제안', { exact: true })).toBeVisible()
  await expect(page.locator('.scenario-chat')).not.toContainText('**')
  await page.getByRole('button', { name: '새 버전 생성' }).click()
  await expect(page.getByRole('tab', { name: 'v2' })).toBeVisible({ timeout: 5_000 })
  await chat.fill('외부 기상 데이터를 다시 확인해서 현장 절차를 보강해줘')
  await page.getByRole('button', { name: '제안 확인' }).click()
  await page.getByRole('button', { name: '새 버전 생성' }).click()
  await expect(page.getByRole('tab', { name: 'v3' })).toBeVisible({ timeout: 5_000 })
  await expect(chat).toBeDisabled()
  await expect(page.getByText('AI 재실행 2회를 모두 사용했습니다.')).toBeVisible()

  await page.getByRole('tab', { name: 'v2' }).click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '최종 채택', exact: true }).click()
  await expect(page.getByText('이 버전이 보고서 생성 기준입니다.')).toBeVisible()
  await page.getByRole('button', { name: '보고서 생성' }).click()
  await expect(page.getByRole('heading', { name: '보고서 상세' })).toBeVisible()

  const reportChat = page.getByRole('textbox', { name: '검토 질문' })
  await reportChat.fill('현장 인계 전에 빠진 확인 항목을 검토해줘')
  await page.getByRole('button', { name: '질문', exact: true }).click()
  await expect(page.getByText('본문은 변경하지 않았으니 운영자가 필요한 문구만 직접 반영해 주세요.')).toBeVisible()

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
