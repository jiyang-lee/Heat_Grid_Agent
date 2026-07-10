import type { StyleSpecification } from 'maplibre-gl'

/**
 * VITE_MAP_STYLE_URL이 전체 MapLibre style URL이면 해당 스타일을 사용한다.
 * 설정이 없거나 예전 MapTiler 키만 있으면 별도 키가 필요 없는 CARTO 타일을 사용한다.
 */
const raw = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()

const defaultMapStyle: StyleSpecification = {
  version: 8,
  sources: {
    'carto-dark': {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#07111f' },
    },
    {
      id: 'carto-dark',
      type: 'raster',
      source: 'carto-dark',
      minzoom: 0,
      maxzoom: 22,
      paint: { 'raster-opacity': 0.92 },
    },
  ],
}

export const mapStyle: string | StyleSpecification = raw.startsWith('http')
  ? raw
  : defaultMapStyle
