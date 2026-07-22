const configured = (import.meta.env.VITE_MAP_STYLE_URL ?? '').trim()
const configuredStyleUrl = configured.startsWith('http') ? configured : null
const mapTilerKey = configuredStyleUrl == null ? configured : ''

export function mapStyleFor(
  theme: 'dark' | 'light',
): string {
  if (configuredStyleUrl != null) return configuredStyleUrl
  if (mapTilerKey.length === 0) {
    const cartoStyle = theme === 'light' ? 'positron' : 'dark-matter'
    return `https://basemaps.cartocdn.com/gl/${cartoStyle}-gl-style/style.json`
  }

  const styleId = theme === 'light' ? 'streets-v2' : 'dataviz-dark'
  return (
    'https://api.maptiler.com/maps/' +
    styleId +
    '/style.json?key=' +
    encodeURIComponent(mapTilerKey)
  )
}
