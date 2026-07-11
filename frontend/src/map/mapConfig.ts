import type { StyleSpecification } from 'maplibre-gl'

/**
 * 지도 스타일 소스 해석.
 *
 * .env 의 VITE_MAP_STYLE_URL 에는 다음 중 하나가 들어올 수 있다:
 *   - 전체 style JSON URL (https://...) → 그대로 사용(이 경우 다크/라이트 전환 불가, 그대로 고정)
 *   - 빈 값 또는 예전 MapTiler 키 → 별도 키가 필요 없는 CARTO 다크/라이트 타일 사용
 *
 * URL이 없을 때는 테마별 CARTO 타일로 전환한다.
 */
const raw = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()
const isFullUrl = raw.startsWith('http')

function defaultMapStyle(theme: 'dark' | 'light'): StyleSpecification {
  const light = theme === 'light'
  const sourceId = light ? 'carto-light' : 'carto-dark'
  const tileVariant = light ? 'light_all' : 'dark_all'

  return {
    version: 8,
    sources: {
      [sourceId]: {
        type: 'raster',
        tiles: [
          `https://a.basemaps.cartocdn.com/${tileVariant}/{z}/{x}/{y}.png`,
          `https://b.basemaps.cartocdn.com/${tileVariant}/{z}/{x}/{y}.png`,
          `https://c.basemaps.cartocdn.com/${tileVariant}/{z}/{x}/{y}.png`,
        ],
        tileSize: 256,
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      },
    },
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': light ? '#eef2f6' : '#07111f' },
      },
      {
        id: sourceId,
        type: 'raster',
        source: sourceId,
        minzoom: 0,
        maxzoom: 22,
        paint: { 'raster-opacity': 0.92 },
      },
    ],
  }
}

/** 테마별 지도 스타일. 전체 URL은 고정 사용하고, 나머지는 CARTO fallback을 쓴다. */
export function mapStyleFor(theme: 'dark' | 'light'): string | StyleSpecification {
  if (isFullUrl) return raw
  return defaultMapStyle(theme)
}
