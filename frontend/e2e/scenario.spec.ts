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
  await expect(page.getByText('운영 알림 없음', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /환수온도 급락 및 난방 순환펌프 이상/ })).toBeVisible({ timeout: 12_000 })
}

async function dismissIncidentPopup(page: Page) {
  const popup = page.getByRole('dialog', { name: '우선순위 경보' })
  await expect(popup).toBeVisible()
  await popup.getByRole('button', { name: '경보 팝업 닫기' }).click()
}

test('entry and dashboard keep the viewport fixed with no Replay navigation', async ({ page }) => {
  await openEntry(page)
  await expect(page.getByRole('region', { name: '운영 환경을 선택하세요' })).toBeVisible()
  await expectNoPageScroll(page)

  await page.getByRole('button', { name: /정상 버전 보기/ }).click()
  await expect(page.locator('.metric-grid-five > *')).toHaveCount(5)
  await expect(page.locator('.metric-grid-five').getByRole('article')).toHaveCount(4)
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
  await expect(page.getByRole('dialog', { name: '우선순위 경보' })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '우선순위 경보' })).toContainText('범지기마을')
  await expect(page.getByText('urgent', { exact: true }).first()).toBeVisible()
  await expect(page.locator('.sensor-tile.sf-return')).toHaveCount(0)
  await dismissIncidentPopup(page)

  await page.getByRole('button', { name: /열교환기 외부 누수 의심/ }).click()
  await expect(page.locator('.sensor-flow').getByText(/기계실 31/)).toBeVisible()
  await expectNoPageScroll(page)
})

test('alerts start as a list and analysis completion offers an AI action toast', async ({ page }) => {
  await startFaultScenario(page)
  await waitForIncident(page)
  await dismissIncidentPopup(page)
  await page.getByRole('button', { name: '자세히 보기', exact: true }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: '우선순위 필터' })).toBeVisible()
  await page.getByRole('combobox', { name: '이상 센서 필터' }).selectOption('returnTemperature')
  await expect(page.locator('.scenario-alert-rows > button')).toHaveCount(1)
  await page.getByRole('combobox', { name: '이상 센서 필터' }).selectOption('all')

  await page.getByRole('button', { name: /환수온도 급락 및 난방 순환펌프 이상/ }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toBeVisible()
  await expect(page.getByRole('region', { name: '환수온도 이상 시계열' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '환수온도 이상 감지' })).toBeVisible()
  await page.getByRole('button', { name: '상세 정보 닫기' }).click()
  await expect(page.getByRole('heading', { name: '상세 정보' })).toHaveCount(0)
  await page.getByRole('button', { name: /환수온도 급락 및 난방 순환펌프 이상/ }).click()
  await page.getByRole('button', { name: 'AI 조치 분석' }).click()
  await expect(page.getByRole('status')).toContainText('AI 조치가 활성화되었습니다.', { timeout: 3_000 })
  await page.getByRole('button', { name: 'AI 조치 페이지 이동' }).click()
  await expect(page.locator('.topbar-page-context')).toContainText('AI 조치')
  await expect(page.getByRole('heading', { name: 'AI 권장 조치' })).toBeVisible()
  await expectNoPageScroll(page)
})

test('work order review reaches v3 and the scenario report can be issued', async ({ page }) => {
  await startFaultScenario(page)
  await waitForIncident(page)
  await dismissIncidentPopup(page)
  await page.getByRole('button', { name: '자세히 보기', exact: true }).click()
  await page.getByRole('button', { name: /환수온도 급락 및 난방 순환펌프 이상/ }).click()
  await page.getByRole('button', { name: 'AI 조치 분석' }).click()
  await page.getByRole('button', { name: 'AI 조치 페이지 이동' }).click({ timeout: 3_000 })

  await page.getByRole('button', { name: '작업지시서 생성' }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 v1', exact: true })).toBeVisible()
  await expect.poll(() => page.locator('.scenario-order-document').evaluate((card) => {
    const body = card.querySelector('.scenario-order-body')
    return card.getBoundingClientRect().bottom <= window.innerHeight && body != null && body.scrollHeight > body.clientHeight
  })).toBe(true)
  const review = page.getByRole('textbox', { name: '검토 의견' })
  await review.fill('첫 줄')
  await review.press('Shift+Enter')
  await expect(review).toHaveValue('첫 줄\n')
  await expect(page.getByRole('button', { name: '수정 실행' })).toHaveCount(0)
  await review.fill('참고한 매뉴얼이 오래된 것 같아. 최신 RAG 문서로 다시 확인해줘.')
  await review.press('Enter')
  await page.getByRole('button', { name: '수정 실행' }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 v2', exact: true })).toBeVisible({ timeout: 3_000 })
  await expect(page.getByRole('list', { name: '작업지시서 v1 검토 대화' })).toContainText('참고한 매뉴얼이 오래된 것 같아')

  await review.fill('위험도 평가가 너무 높은 것 같아. 예측 모델 근거를 다시 검증해줘.')
  await page.getByRole('button', { name: '의견 분석' }).click()
  await page.getByRole('button', { name: '수정 실행' }).click()
  await expect(page.getByRole('heading', { name: '작업지시서 v3', exact: true })).toBeVisible({ timeout: 3_000 })

  await page.getByRole('button', { name: '최종 채택' }).click()
  await page.getByRole('tab', { name: '보고서' }).click()
  await page.getByRole('button', { name: '보고서 초안 생성' }).click()
  await expect(page.getByText('2. 사고 타임라인', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '보고서 발행' }).click()
  await expect(page.getByText('발행 완료', { exact: true })).toBeVisible()
  await expectNoPageScroll(page)
})
