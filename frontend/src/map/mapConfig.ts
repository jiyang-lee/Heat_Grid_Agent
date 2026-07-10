/**
 * 지도 스타일 소스 해석.
 *
 * .env 의 VITE_MAP_STYLE_URL 에는 다음 중 하나가 들어올 수 있다:
 *   - MapTiler 키 문자열만 (예: YOUR_MAPTILER_KEY) → 테마별 스타일 URL을 조립
 *   - 전체 style JSON URL (https://...) → 그대로 사용(이 경우 다크/라이트 전환 불가, 그대로 고정)
 *
 * 테마별 MapTiler 스타일: 다크=dataviz-dark, 라이트=streets-v2(Streets).
 */

const raw = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()
const isFullUrl = raw.startsWith('http')

/** 테마별 지도 스타일 URL. 키 문자열이면 스타일 조립, 전체 URL이면 그대로. */
export function mapStyleUrlFor(theme: 'dark' | 'light'): string {
  if (isFullUrl) return raw
  if (!raw) return ''
  const style = theme === 'light' ? 'streets-v2' : 'dataviz-dark'
  return `https://api.maptiler.com/maps/${style}/style.json?key=${raw}`
}

export const mapStyleUrl: string = mapStyleUrlFor('dark')
export const hasMapStyle = mapStyleUrl.length > 0
