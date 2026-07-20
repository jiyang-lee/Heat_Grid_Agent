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

function axisLabelsFromTopbar(timeText: string | null): readonly string[] {
  const [hourText = '0', minuteText = '0'] = timeText?.split(':') ?? []
  const roundedCurrent = Number(hourText) * 60 + Math.floor(Number(minuteText) / 10) * 10
  return [-120, -90, -60, -10, 0, 60].map((offset) => {
    const minutesInDay = 24 * 60
    const total = (roundedCurrent + offset + minutesInDay) % minutesInDay
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
  })
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

test('normal mode renders sensor charts as empty two-hour axes', async ({ page }) => {
  await page.addInitScript(`
    const fixedNow = new Date('2026-07-20T14:43:00+09:00').valueOf()
    const RealDate = Date
    class FixedDate extends RealDate {
      constructor(...args) {
        if (args.length === 0) super(fixedNow)
        else super(...args)
      }
      static now() {
        return fixedNow
      }
    }
    globalThis.Date = FixedDate
  `)
  await openEntry(page)
  await page.locator('.map-fallback-marker').first().evaluate((element: HTMLButtonElement) => element.click())

  const charts = page.locator('.sf-history-chart')
  await expect(charts).toHaveCount(2)
  await expect(charts.locator('polyline')).toHaveCount(0)
  await expect(charts.locator('.sf-chart-point')).toHaveCount(0)
  await expect(charts.locator('.sf-current-line')).toHaveCount(0)
  await expect(charts.locator('.sf-x-label')).toHaveCount(12)
  const topbarTime = await page.locator('.topbar-clock strong').textContent()
  const firstChartLabels = await charts.first().locator('.sf-x-label').allTextContents()
  expect(topbarTime).toBe('14:43')
  expect(firstChartLabels).toEqual(['12:40', '13:10', '13:40', '14:30', '14:40', '15:40'])
  expect(firstChartLabels).toEqual(axisLabelsFromTopbar(topbarTime))
})

test('sidebar brand mark remains visible after a theme change', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('heatgrid:theme-preference', 'light'))
  await page.goto('/?devtools=0')

  const brandMark = page.locator('.brand-mark img')
  await expect(brandMark).toBeVisible()
  await expect(brandMark).toHaveAttribute('src', /heatgrid-mark/)

  await page.getByRole('button', { name: '설정', exact: true }).click()
  await page.getByRole('tab', { name: '화면 및 알림' }).click()
  await page.getByLabel('다크 모드').check()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(brandMark).toBeVisible()
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

test('security settings keep the action footer visible while the long body scrolls internally', async ({ page }) => {
  await openEntry(page)
  await page.getByRole('button', { name: '설정', exact: true }).click()
  await page.getByRole('tab', { name: '로그인 및 보안' }).click()

  const view = page.locator('.settings-profile-view')
  const body = page.locator('.settings-sec-card .sec-body')
  const footer = page.locator('.settings-sec-card .profile-footer')
  await expect.poll(async () => {
    const [viewBox, footerBox] = await Promise.all([view.boundingBox(), footer.boundingBox()])
    return viewBox != null && footerBox != null && footerBox.y >= viewBox.y && footerBox.y + footerBox.height <= viewBox.y + viewBox.height
  }).toBe(true)
  await expect.poll(() => body.evaluate((element) => getComputedStyle(element).overflowY === 'auto' && element.scrollHeight > element.clientHeight)).toBe(true)
  await expect.poll(() => body.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  const currentDevices = body.locator('.sec-section').first()
  await expect(currentDevices.getByText('Windows Chrome', { exact: true })).toBeVisible()
  await expect(currentDevices.getByText('현재 사용 중', { exact: true })).toBeVisible()
})

test('all settings tabs use the profile card frame with a visible action footer', async ({ page }) => {
  await openEntry(page)
  await page.getByRole('button', { name: '설정', exact: true }).click()

  for (const [tabName, bodySelector] of [
    ['내 프로필', '.settings-profile-card .profile-body'],
    ['화면 및 알림', '.settings-sn-card .settings-sn-content'],
    ['로그인 및 보안', '.settings-sec-card .sec-body'],
  ] as const) {
    await page.getByRole('tab', { name: tabName }).click()
    const view = page.locator('.settings-profile-view')
    const tabbar = page.locator('.settings-tabbar')
    const card = view.locator('> .ops-surface')
    const body = page.locator(bodySelector)
    const footer = card.locator('.profile-footer')
    await expect(body).toBeVisible()
    await expect.poll(async () => {
      const [viewBox, tabbarBox, cardBox, footerBox] = await Promise.all([view.boundingBox(), tabbar.boundingBox(), card.boundingBox(), footer.boundingBox()])
      return viewBox != null && tabbarBox != null && cardBox != null && footerBox != null
        && tabbarBox.height >= 20
        && tabbarBox.height <= 50
        && Math.abs(cardBox.height - viewBox.height) < 1
        && footerBox.y >= viewBox.y
        && footerBox.y + footerBox.height <= viewBox.y + viewBox.height
    }).toBe(true)
  }
})

test('switching settings tabs always opens the new tab at its top', async ({ page }) => {
  await openEntry(page)
  await page.getByRole('button', { name: '설정', exact: true }).click()

  const profileBody = page.locator('.settings-profile-card .profile-body')
  await profileBody.evaluate((element) => { element.scrollTop = element.scrollHeight })
  await expect.poll(() => profileBody.evaluate((element) => element.scrollTop > 0)).toBe(true)

  await page.getByRole('tab', { name: '화면 및 알림' }).click()
  const screenBody = page.locator('.settings-sn-card .settings-sn-content')
  await expect.poll(() => screenBody.evaluate((element) => element.scrollTop)).toBe(0)

  await screenBody.evaluate((element) => { element.scrollTop = element.scrollHeight })
  await expect.poll(() => screenBody.evaluate((element) => element.scrollTop > 0)).toBe(true)
  await page.getByRole('tab', { name: '로그인 및 보안' }).click()
  await expect.poll(() => page.locator('.settings-sec-card .sec-body').evaluate((element) => element.scrollTop)).toBe(0)
})

test('fault incident starts after five seconds and selects the matching sensor room', async ({ page }) => {
  await startFaultScenario(page)
  await expect(page.locator('.metric-grid-five > *')).toHaveCount(5)
  await waitForIncident(page)
  const metrics = page.locator('.metric-grid-five .home-metric')
  await expect(metrics.filter({ hasText: '긴급' })).toContainText('2')
  await expect(metrics.filter({ hasText: '주의' })).toContainText('1')
  await expect(metrics.filter({ hasText: '관찰' })).toContainText('0')
  await expect(metrics.filter({ hasText: '정상' })).toContainText('28')
  await expect(page.locator('.map-fallback-marker.status-low')).toHaveCount(28)
  await expect(page.getByRole('status', { name: '우선순위 1 경보' })).toBeVisible()
  await expect(page.getByRole('status', { name: '우선순위 1 경보' })).toContainText('범지기마을')
  await expect(page.getByText('urgent', { exact: true }).first()).toBeVisible()
  await expect(page.locator('.sensor-tile.sf-return')).toHaveCount(0)
  await dismissIncidentToasts(page)
  const toMinutes = (value: string | null) => {
    const [hours = '0', minutes = '0'] = value?.split(':') ?? []
    return Number(hours) * 60 + Number(minutes)
  }
  await expect.poll(async () => toMinutes(await page.locator('.topbar-clock strong').textContent())).toBeGreaterThanOrEqual(15 * 60 + 20)
  const timeBeforeAlertSelection = await page.locator('.topbar-clock strong').textContent()

  await page.getByRole('button', { name: /열교환기 외부 누수 의심/ }).click()
  await page.waitForTimeout(100)
  const timeAfterAlertSelection = await page.locator('.topbar-clock strong').textContent()
  expect(timeAfterAlertSelection).toBe(timeBeforeAlertSelection)
  await expect(page.locator('.sensor-flow').getByText(/기계실 31/)).toBeVisible()
  await expect(page.locator('.sf-data-status')).toHaveCount(0)
  await expect(page.locator('.sf-history-chart polyline')).toHaveCount(3)
  await expect(page.locator('.sf-history-chart .sf-chart-point')).toHaveCount(39)
  await expect(page.locator('.sf-chart-legend')).toHaveCount(2)
  await page.locator('.map-fallback-marker').evaluateAll((markers) => {
    const marker = markers.find((element) => element.textContent?.trim() === '1') as HTMLButtonElement | undefined
    marker?.click()
  })
  await page.waitForTimeout(100)
  const timeAfterRoomSelection = await page.locator('.topbar-clock strong').textContent()
  expect(timeAfterRoomSelection).toBe(timeAfterAlertSelection)
  await expect(page.locator('.sensor-flow').getByText(/기계실 1/)).toBeVisible()
  await expect(page.locator('.sf-current-value')).toContainText(['76.1', '41.5', '116.0'])
  await expect.poll(() => page.locator('.sf-current-value').allTextContents()).not.toContain('34.1')
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

test('fault-mode work-order tab keeps the scenario document workspace after navigation', async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('heatgrid:scenario-session', JSON.stringify({
      mode: 'fault',
      entryStep: 'console',
      scenarioId: 'return-temperature-2020-01-13',
      selectedAlertId: 'scenario-alert-pump-28',
      selectedSubstationId: 28,
      incidentState: 'incident-active',
      analyzedAlertIds: ['scenario-alert-pump-28'],
      dismissedIncidentAlertIds: [],
      resolvedAlertTimes: {},
      alertSensorSnapshots: {},
      documentAlertId: 'scenario-alert-pump-28',
      workOrders: [{ version: 1, createdAt: '2020-01-13T15:10:00+09:00', changeSummary: 'AI 초안 생성', content: '초기 작업지시서' }],
      selectedWorkOrderVersion: 1,
      acceptedWorkOrderVersion: null,
      workOrderRerunCount: 0,
      messages: [],
      evaluationCategory: null,
      report: { status: 'idle', createdAt: null, savedAt: null, completedAt: null, content: '' },
      reportMessages: [],
    }))
  })
  await page.goto('/?devtools=0')
  await page.getByRole('button', { name: 'AI 조치', exact: true }).click()
  await page.getByRole('tab', { name: '작업지시서' }).click()

  await expect(page.locator('.scenario-order-layout')).toBeVisible()
  await expect(page.getByRole('heading', { name: '작업지시서 상세' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'AI 수정 챗봇' })).toBeVisible()
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
