import type { StyleSpecification } from 'maplibre-gl'
import type { Feature, FeatureCollection, LineString } from 'geojson'

const configured = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()
const configuredStyleUrl = configured.startsWith('http') ? configured : null
const mapTilerKey = configuredStyleUrl == null ? configured : ''

/** 외부 타일/스타일 없이 단색 배경으로 뜨는 상태(키 미설정) 여부. */
export const isFallbackMapStyle = configuredStyleUrl == null && mapTilerKey.length === 0

function emptyStyle(theme: 'dark' | 'light'): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: {
          'background-color': theme === 'light' ? '#eef2f6' : '#07111f',
        },
      },
    ],
  }
}

export function mapStyleFor(
  theme: 'dark' | 'light',
): string | StyleSpecification {
  if (configuredStyleUrl != null) return configuredStyleUrl
  if (mapTilerKey.length === 0) return emptyStyle(theme)

  const styleId = theme === 'light' ? 'streets-v2' : 'dataviz-dark'
  return (
    'https://api.maptiler.com/maps/' +
    styleId +
    '/style.json?key=' +
    encodeURIComponent(mapTilerKey)
  )
}

/**
 * 키 없는 환경용 밝은 지도형 배경(합성 도로 격자 + 하천 곡선).
 * 실 지리 데이터가 아니라 시안과 유사한 분위기를 내는 장식 지오메트리다.
 */
export function buildFallbackBackdrop(center: [number, number]): FeatureCollection<LineString> {
  const [cx, cy] = center
  const half = 0.032
  const features: Feature<LineString>[] = []
  for (let i = -4; i <= 4; i++) {
    const offset = i * (half / 4)
    const kind = i % 2 === 0 ? 'road-major' : 'road-minor'
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[cx - half, cy + offset], [cx + half, cy + offset]] },
      properties: { kind },
    })
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[cx + offset, cy - half], [cx + offset, cy + half]] },
      properties: { kind },
    })
  }
  // 하천: 좌하 → 우상으로 완만하게 흐르는 곡선 2개(시안의 강 형태 프록시).
  const river = (shift: number): Feature<LineString> => ({
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: Array.from({ length: 13 }, (_, index) => {
        const t = index / 12
        return [
          cx - half + t * half * 2,
          cy - half * 0.55 + shift + Math.sin(t * Math.PI * 1.4) * half * 0.3,
        ]
      }),
    },
    properties: { kind: 'river' },
  })
  features.push(river(0), river(half * 1.05))
  return { type: 'FeatureCollection', features }
}
