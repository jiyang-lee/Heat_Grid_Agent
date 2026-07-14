import type { StyleSpecification } from 'maplibre-gl'

const configured = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()
const configuredStyleUrl = configured.startsWith('http') ? configured : null
const mapTilerKey = configuredStyleUrl == null ? configured : ''

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
