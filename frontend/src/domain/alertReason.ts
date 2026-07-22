const SCENARIO_ML_MARKER = '[ML 결과: 모델 '
const SCENARIO_ALERT_TITLES = [
  '공급온도 저하 및 순환 유량 급변',
  '순환 유량 급감 및 펌프 부하 이상',
  '환수온도 저하 및 열교환 효율 이상',
] as const

function firstSentence(value: string): string {
  const normalized = value.trim()
  return normalized.match(/^.*?[.!?](?=\s|$)/u)?.[0] ?? normalized
}

/** 고장 시나리오 알림을 제목과 요약 첫 문장만으로 구성한다. */
export function compactScenarioAlertReason(title: string, summary: string): string {
  return `${title.trim()} · ${firstSentence(summary)}`
}

/** 이미 저장된 시나리오 알림도 신규 알림과 같은 짧은 형식으로 표시한다. */
export function displayAlertReason(reason: string | null | undefined): string {
  const normalized = reason?.trim()
  if (!normalized) return '-'
  const isScenarioAlert = normalized.includes(SCENARIO_ML_MARKER)
    || SCENARIO_ALERT_TITLES.some((title) => normalized.startsWith(`${title} ·`))
  if (!isScenarioAlert) return normalized

  const withoutMlResult = normalized.replace(/\s*\[ML 결과:.*$/u, '').trim()
  const separatorIndex = withoutMlResult.indexOf('·')
  if (separatorIndex < 0) return firstSentence(withoutMlResult)

  return compactScenarioAlertReason(
    withoutMlResult.slice(0, separatorIndex),
    withoutMlResult.slice(separatorIndex + 1),
  )
}
