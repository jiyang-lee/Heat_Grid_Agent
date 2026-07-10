/**
 * 지도 스타일 소스 해석.
 *
 * .env 의 VITE_MAP_STYLE_URL 에는 다음 중 하나가 들어올 수 있다:
 *   - MapTiler 키 문자열만 (예: YOUR_MAPTILER_KEY) → 다크 스타일 URL을 조립
 *   - 전체 style JSON URL (https://...) → 그대로 사용
 */

const MAPTILER_DARK_STYLE = 'dataviz-dark'

const raw = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()

export const mapStyleUrl: string = raw.startsWith('http')
  ? raw
  : raw
    ? `https://api.maptiler.com/maps/${MAPTILER_DARK_STYLE}/style.json?key=${raw}`
    : ''

export const hasMapStyle = mapStyleUrl.length > 0
