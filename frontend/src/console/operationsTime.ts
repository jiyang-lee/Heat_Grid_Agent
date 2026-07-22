const KST = 'Asia/Seoul'

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: KST,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  weekday: 'short',
})

const timeFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: KST,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

export function operationsClock(value: Date | string): { readonly date: string; readonly time: string } {
  const date = typeof value === 'string' ? new Date(value) : value
  return { date: dateFormatter.format(date), time: timeFormatter.format(date) }
}

export function operationsDateTime(value: string | null): string {
  if (value == null) return '-'
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: KST,
    dateStyle: 'medium',
    timeStyle: 'short',
    hourCycle: 'h23',
  }).format(new Date(value))
}

export function relativeOperationsTime(value: string, reference: Date | string): string {
  const seconds = Math.round((new Date(value).getTime() - new Date(reference).getTime()) / 1000)
  const absolute = Math.abs(seconds)
  const formatter = new Intl.RelativeTimeFormat('ko-KR', { numeric: 'auto' })
  if (absolute < 60) return formatter.format(seconds, 'second')
  if (absolute < 3600) return formatter.format(Math.round(seconds / 60), 'minute')
  if (absolute < 86_400) return formatter.format(Math.round(seconds / 3600), 'hour')
  return formatter.format(Math.round(seconds / 86_400), 'day')
}

export const OPERATIONS_TIMEZONE = KST
