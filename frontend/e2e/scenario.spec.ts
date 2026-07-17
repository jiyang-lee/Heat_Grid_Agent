import { expect, test, type Page } from '@playwright/test'

async function openEntry(page: Page) {
  await page.addInitScript(() => window.sessionStorage.clear())
  await page.goto('/?devtools=0')
}

async function startFaultScenario(page: Page) {
  await openEntry(page)
  await page.getByRole('button', { name: /고장 버전 보기/ }).click()
  await page.getByRole('button', { name: /환수온도 이상 및 동시다발 설비 고장/ }).click()
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
  await expect(page.getByRole('region', { name: '운영 환경을 선택하세요' })).toBeVisible()
  await expectNoPageScroll(page)

  await page.getByRole('button', { name: /정상 버전 보기/ }).click()
  await expect(page.locator('.metric-grid-five > *')).toHaveCount(5)
  await expect(page.locator('.metric-grid-five').getByRole('article')).toHaveCount(5)
  await expect(page.getByRole('button', { name: 'Replay', exact: true })).toHaveCount(0)
  await expect(page.locator('.topbar-page-context')).toContainText('홈')
  await expect(page.locator('.topbar-page-context > span')).toHaveCount(0)
  await expect(page.locator('.topbar-nav')).toHaveCount(0)
  await expect(page.locator('.sf-charts svg')).toHaveCount(2)
  await expectNoPageScroll(page)
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
  await page.getByRole('button', { name: 'AI 조치 분석' }).click()
  const analysisProgress = page.getByRole('status')
  await expect(analysisProgress).toContainText('예측 모델 판정중')
  await expect(analysisProgress).toContainText('작업지시서 작성 준비중')
  const aiShortcut = page.getByRole('button', { name: 'AI 조치 바로가기' })
  await expect(aiShortcut).toBeVisible({ timeout: 45_000 })
  await expect.poll(() => aiShortcut.evaluate((button) => button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(50)
  await aiShortcut.click()
  await expect(page.locator('.topbar-page-context')).toContainText('AI 조치')
  await expect(page.getByRole('heading', { name: '작업지시서 가이드' })).toBeVisible()
  await expect(page.getByRole('button', { name: '작업지시서 생성' })).toBeVisible()
  await expectNoPageScroll(page)
})

test('refresh keeps the current page and clears resolved alerts', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-375', '새로고침 버튼은 모바일 레이아웃에서 숨김')
  await startFaultScenario(page)
  await waitForIncident(page)
  await page.getByRole('status', { name: '우선순위 1 경보' }).getByRole('button', { name: '알림 바로가기' }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '종결', exact: true }).click()
  await expect(page.getByText('종결', { exact: true }).first()).toBeVisible()

  const refreshButton = page.getByRole('button', { name: '새로고침', exact: true })
  await refreshButton.click()
  await expect(refreshButton).not.toBeFocused()
  await expect(page.locator('.topbar-page-context')).toContainText('알림')
  await expect(page.locator('.topbar-clock strong')).toHaveText('14:50')
  await expect(page.getByRole('combobox', { name: '표시 범위' })).toHaveValue('active')
  await expect(page.getByRole('row', { name: /환수온도 급락 및 난방 순환펌프 이상/ })).toBeVisible({ timeout: 12_000 })
  await expect(page.getByText('종결', { exact: true })).toHaveCount(0)
})

test('AI action guide creates a real LLM work order', async ({ page }) => {
  test.setTimeout(120_000)
  await startFaultScenario(page)
  await waitForIncident(page)
  await dismissIncidentToasts(page)
  await page.getByRole('button', { name: '자세히 보기', exact: true }).click()
  await openAlertDetail(page, /환수온도 급락 및 난방 순환펌프 이상/)
  await page.getByRole('button', { name: 'AI 조치 분석' }).click()
  await page.getByRole('button', { name: 'AI 조치 바로가기' }).click({ timeout: 45_000 })

  await expect(page.getByRole('heading', { name: '작업지시서 가이드' })).toBeVisible()
  await page.getByRole('button', { name: '작업지시서 생성' }).click()
  await expect(page.getByText('LLM이 작업지시서를 생성하고 있습니다.')).toBeVisible()
  await expect(page.getByText('작업지시서 생성이 완료되었습니다. 상단 작업지시서 탭에서 확인할 수 있습니다.')).toBeVisible({ timeout: 60_000 })
})
