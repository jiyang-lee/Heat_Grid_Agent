import { expect, test } from '@playwright/test'

test('offline sample walkthrough preserves deep links and resets', async ({ page }) => {
  // Given: a demo build, every request must stay on its static origin.
  const unexpected: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.origin !== 'http://127.0.0.1:5173' || /^\/(api|health|cards|simulate)/.test(url.pathname)) unexpected.push(url.href)
  })
  await page.goto('/#equipment')
  await page.getByRole('link', { name: '연결된 알림 확인' }).click()
  await page.getByRole('link', { name: '판단 근거 확인' }).click()
  await page.getByRole('link', { name: '저장된 에이전트 보고서 열기' }).click()
  // When: refreshing a report link.
  await page.reload()
  // Then: the original report remains available without backend traffic.
  await expect(page.getByRole('heading', { name: '순환펌프 점검 보고서' })).toBeVisible()
  expect(unexpected).toEqual([])
  await page.screenshot({ path: `test-results/demo-report-${test.info().project.name}.png`, fullPage: true })
})

test('normal state and reset are usable', async ({ page }) => {
  // Given: the sample equipment screen.
  await page.goto('/#equipment')
  // When: choosing normal state.
  await page.getByRole('button', { name: '정상 상태', exact: true }).click()
  // Then: an empty state appears and reset restores the fault sample.
  await expect(page.getByRole('heading', { name: '열린 알림이 없습니다' })).toBeVisible()
  await page.getByRole('button', { name: '체험 초기화' }).click()
  await expect(page.getByRole('heading', { name: '열공급 연결 개요' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: `test-results/demo-equipment-${test.info().project.name}.png`, fullPage: true })
})
