/**
 * MapLibre GL JS 지도: streets 라이트 지도 + 단지 2D 원형 마커.
 *
 * - 배경: MapTiler streets-v2 — mapConfig.mapStyleFor('light')
 *   키가 없으면 합성 도로/하천 backdrop(buildFallbackBackdrop)으로 밝은 지도형 유지
 * - 내 31개 단지: buildComplexMarkers 포인트를 circle 레이어로 표기
 * - 최신 Priority 평가 상태 → circle-color 데이터 바인딩
 * - 좌측 상단 +/− 줌과 전체 위치 맞춤 버튼, 단지 클릭 → onSelectComplex(id)
 */

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { PriorityEvaluationResult } from '../api/contracts'
import { buildFallbackBackdrop, isFallbackMapStyle, mapStyleFor } from './mapConfig'
import { buildComplexMarkers, SEJONG_CENTER } from './footprints'

interface Props {
  onSelectComplex: (id: number) => void
  results: PriorityEvaluationResult[]
  loading: boolean
  error: boolean
}

const MARKER_LAYER = 'complexes-points'
const HOME_ZOOM = 13.3

/** 홈 범례(정상/주의/위험)와 같은 토큰 색. medium/low는 홈 집계상 정상으로 묶인다. */
const MARKER_COLORS = [
  'match',
  ['get', 'status'],
  'urgent', '#ff3b30',
  'high', '#ff7a00',
  'medium', '#16a34a',
  'low', '#16a34a',
  'stale', '#94a3b8',
  /* missing */ '#64748b',
] as const

/** 좌측 상단 '전체 위치 맞춤' 커스텀 컨트롤(현재 위치 아이콘). */
class FitAllControl implements maplibregl.IControl {
  private container: HTMLElement | null = null

  onAdd(map: maplibregl.Map): HTMLElement {
    const container = document.createElement('div')
    container.className = 'maplibregl-ctrl maplibregl-ctrl-group'
    const button = document.createElement('button')
    button.type = 'button'
    button.setAttribute('aria-label', '전체 설비 위치로 이동')
    button.innerHTML =
      '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="5.5"/><path d="M12 2.5v3.5M12 18v3.5M2.5 12H6M18 12h3.5"/></svg>'
    button.style.display = 'grid'
    button.style.placeItems = 'center'
    button.addEventListener('click', () => map.flyTo({ center: SEJONG_CENTER, zoom: HOME_ZOOM }))
    container.appendChild(button)
    this.container = container
    return container
  }

  onRemove(): void {
    this.container?.remove()
    this.container = null
  }
}

/** 키 없는 환경: 마커 아래 깔리는 합성 도로/하천 backdrop 레이어. */
function addFallbackBackdrop(map: maplibregl.Map) {
  if (map.getSource('fallback-backdrop')) return
  map.addSource('fallback-backdrop', { type: 'geojson', data: buildFallbackBackdrop(SEJONG_CENTER) })
  map.addLayer({
    id: 'fallback-river',
    type: 'line',
    source: 'fallback-backdrop',
    filter: ['==', ['get', 'kind'], 'river'],
    paint: { 'line-color': '#c9ddf2', 'line-width': 16, 'line-opacity': 0.9 },
    layout: { 'line-cap': 'round', 'line-join': 'round' },
  })
  map.addLayer({
    id: 'fallback-road-minor',
    type: 'line',
    source: 'fallback-backdrop',
    filter: ['==', ['get', 'kind'], 'road-minor'],
    paint: { 'line-color': '#e3eaf2', 'line-width': 1.4 },
  })
  map.addLayer({
    id: 'fallback-road-major',
    type: 'line',
    source: 'fallback-backdrop',
    filter: ['==', ['get', 'kind'], 'road-major'],
    paint: { 'line-color': '#ffffff', 'line-width': 3 },
  })
}

/** 단지 마커 소스/레이어 추가(초기 로드 공통). */
function addComplexLayers(map: maplibregl.Map, results: PriorityEvaluationResult[]) {
  const markers = buildComplexMarkers(results)
  const source = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
  if (source) source.setData(markers)
  else map.addSource('complexes', { type: 'geojson', data: markers })

  if (!map.getLayer(MARKER_LAYER)) {
    map.addLayer({
      id: MARKER_LAYER,
      type: 'circle',
      source: 'complexes',
      paint: {
        'circle-color': [...MARKER_COLORS] as unknown as maplibregl.ExpressionSpecification,
        'circle-radius': 8,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
        'circle-opacity': 0.95,
      },
    })
  }
}

export default function MapView({ onSelectComplex, results, loading, error }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // 최신 콜백을 ref로 유지(맵 초기화는 1회라 클로저 고정 방지)
  const onSelectRef = useRef(onSelectComplex)
  onSelectRef.current = onSelectComplex
  const resultsRef = useRef(results)
  resultsRef.current = results

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapStyleFor('light'),
      center: SEJONG_CENTER,
      zoom: HOME_ZOOM,
      pitch: 0, // 원형 마커 가독성을 위한 정사 시점(2D)
      bearing: 0,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.keyboard.enable()
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false, showCompass: false }), 'top-left')
    map.addControl(new FitAllControl(), 'top-left')

    map.on('load', () => {
      if (isFallbackMapStyle) addFallbackBackdrop(map)
      addComplexLayers(map, resultsRef.current)
    })

    const selectFeature = (e: maplibregl.MapLayerMouseEvent) => {
      const f = e.features?.[0]
      const rawId = f?.properties?.id
      const id = typeof rawId === 'number' ? rawId : Number(rawId)
      if (Number.isInteger(id)) onSelectRef.current(id)
    }
    map.on('click', MARKER_LAYER, selectFeature)
    map.on('mouseenter', MARKER_LAYER, () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', MARKER_LAYER, () => {
      map.getCanvas().style.cursor = ''
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const source = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
    source?.setData(buildComplexMarkers(results))
  }, [results])

  return <div className="map-runtime">
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
    {loading && <div className="map-state">최신 Priority 평가를 불러오는 중입니다.</div>}
    {error && <div className="map-state error">Priority 평가 API에 연결할 수 없습니다.</div>}
  </div>
}
