import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { PriorityEvaluationResult } from '../api/contracts'
import { complexes } from '../data/complexes'
import { priorityDisplayStatus } from '../domain/priority'
import { mapStyleFor } from './mapConfig'
import { buildComplexFootprints, buildComplexMarkers, SEJONG_CENTER } from './footprints'

interface Props {
  onSelectComplex: (id: number) => void
  theme: 'dark' | 'light'
  results: PriorityEvaluationResult[]
  loading: boolean
  error: boolean
}

/**
 * setStyle 후 새 스타일 로드·렌더가 끝나면 콜백 실행(소스/레이어 재추가용).
 * setStyle 직후 isStyleLoaded()는 '옛 스타일' 기준으로 true를 반환할 수 있어 신뢰 불가 →
 * 스타일+타일 로드가 모두 끝나 렌더가 멈추는 'idle' 이벤트를 기다린다(가장 확실).
 */
function whenStyleReady(map: maplibregl.Map, cb: () => void) {
  map.once('idle', cb)
}

/** 단지 소스/레이어 추가(초기 및 스타일 교체 후 공통). 스타일 교체 시 커스텀 레이어가 지워지므로 재구성. */
const HOME_ZOOM = 11
const FOOTPRINT_LAYER = 'complexes-3d'
const MARKER_SOURCE = 'complex-markers'
const MARKER_LAYER = 'complex-markers-dot'
const MAP_LATITUDES = complexes.map((complex) => complex.lat)
const MAP_LONGITUDES = complexes.map((complex) => complex.lng)
const MAP_MIN_LAT = Math.min(...MAP_LATITUDES)
const MAP_MAX_LAT = Math.max(...MAP_LATITUDES)
const MAP_MIN_LNG = Math.min(...MAP_LONGITUDES)
const MAP_MAX_LNG = Math.max(...MAP_LONGITUDES)

function fallbackPosition(lat: number, lng: number): { left: string; top: string } {
  const horizontal = (lng - MAP_MIN_LNG) / (MAP_MAX_LNG - MAP_MIN_LNG)
  const vertical = 1 - (lat - MAP_MIN_LAT) / (MAP_MAX_LAT - MAP_MIN_LAT)
  return { left: `${10 + horizontal * 80}%`, top: `${12 + vertical * 76}%` }
}

function hasWebglContext(): boolean {
  if (navigator.webdriver) return false
  const canvas = document.createElement('canvas')
  return canvas.getContext('webgl') != null || canvas.getContext('experimental-webgl') != null
}

class FitAllControl implements maplibregl.IControl {
  onAdd(map: maplibregl.Map): HTMLElement {
    const container = document.createElement('div')
    container.className = 'maplibregl-ctrl maplibregl-ctrl-group'
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'maplibregl-ctrl-icon'
    button.setAttribute('aria-label', 'Show all complexes')
    button.textContent = 'R'
    button.addEventListener('click', () => map.easeTo({ center: SEJONG_CENTER, zoom: HOME_ZOOM }))
    container.append(button)
    return container
  }

  onRemove(): void {}
}

function addComplexLayers(
  map: maplibregl.Map,
  results: PriorityEvaluationResult[],
) {
  // 베이스맵 자체 3D 건물(예: Streets 'Building 3D') 제거.
  // MapLibre는 모든 fill-extrusion을 첫 돌출 레이어 위치에서 한 패스로 그려서,
  // 남겨두면 그 위 2D 레이어(도로·라벨)가 우리 단지 돌출을 덮어 안 보이게 된다.
  for (const l of map.getStyle().layers ?? []) {
    if (l.type === 'fill-extrusion' && l.id !== 'complexes-3d' && map.getLayer(l.id)) {
      map.removeLayer(l.id)
    }
  }

  const footprints = buildComplexFootprints(results)
  const footprintSource = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
  if (footprintSource) footprintSource.setData(footprints)
  else map.addSource('complexes', { type: 'geojson', data: footprints })

  const markers = buildComplexMarkers(results)
  const markerSource = map.getSource(MARKER_SOURCE) as maplibregl.GeoJSONSource | undefined
  if (markerSource) markerSource.setData(markers)
  else map.addSource(MARKER_SOURCE, { type: 'geojson', data: markers })

  if (!map.getLayer(FOOTPRINT_LAYER)) {
    map.addLayer({
      id: FOOTPRINT_LAYER,
      type: 'fill-extrusion',
      source: 'complexes',
      paint: {
        'fill-extrusion-color': [
          'match',
          ['get', 'status'],
          'urgent', '#ff1744',
          'high', '#ff8f00',
          'medium', '#ffd740',
          'low', '#00c853',
          'stale', '#64748b',
          /* missing */ '#334155',
        ],
        'fill-extrusion-height': ['get', 'height'],
        'fill-extrusion-base': 0,
        'fill-extrusion-opacity': 0.85,
      },
    })
  }

  if (!map.getLayer(MARKER_LAYER)) {
    map.addLayer({
      id: MARKER_LAYER,
      type: 'circle',
      source: MARKER_SOURCE,
      paint: {
        'circle-color': [
          'match',
          ['get', 'status'],
          'urgent', '#ef4444',
          'high', '#f59e0b',
          'medium', '#facc15',
          'low', '#16a34a',
          'stale', '#64748b',
          '#64748b',
        ],
        'circle-radius': 6,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
      },
    })
  }

}

export default function MapView({ onSelectComplex, theme, results, loading, error }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [mapUnavailable, setMapUnavailable] = useState(() => !hasWebglContext())
  // 최신 콜백을 ref로 유지(맵 초기화는 1회라 클로저 고정 방지)
  const onSelectRef = useRef(onSelectComplex)
  onSelectRef.current = onSelectComplex
  const resultsRef = useRef(results)
  resultsRef.current = results
  const themeRef = useRef(theme) // 실제 테마 변경 감지용

  useEffect(() => {
    if (!containerRef.current || mapRef.current || mapUnavailable) return
    let map: maplibregl.Map
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: mapStyleFor(themeRef.current),
        center: SEJONG_CENTER,
        zoom: HOME_ZOOM,
        pitch: 0,
        bearing: 0,
        attributionControl: { compact: true },
      })
    } catch {
      setMapUnavailable(true)
      return
    }
    mapRef.current = map
    // 마우스로 방향(회전)·기울기(pitch) 전환 활성화.
    map.dragRotate.enable()
    map.touchZoomRotate.enableRotation()
    map.keyboard.enable()
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false, showCompass: false }), 'top-left')
    map.addControl(new FitAllControl(), 'top-left')

    map.on('load', () => addComplexLayers(map, resultsRef.current))

    const selectFeature = (e: maplibregl.MapLayerMouseEvent) => {
      const f = e.features?.[0]
      const rawId = f?.properties?.id
      const id = typeof rawId === 'number' ? rawId : Number(rawId)
      if (Number.isInteger(id)) onSelectRef.current(id)
    }
    map.on('click', FOOTPRINT_LAYER, selectFeature)
    map.on('click', MARKER_LAYER, selectFeature)
    map.on('mouseenter', FOOTPRINT_LAYER, () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseenter', MARKER_LAYER, () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', FOOTPRINT_LAYER, () => {
      map.getCanvas().style.cursor = ''
    })
    map.on('mouseleave', MARKER_LAYER, () => {
      map.getCanvas().style.cursor = ''
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [mapUnavailable])

  // 테마 변경 → 지도 스타일 교체 후 단지 레이어 재구성.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (themeRef.current === theme) return // 초기 마운트/동일 테마는 무시
    themeRef.current = theme
    map.setStyle(mapStyleFor(theme))
    whenStyleReady(map, () => addComplexLayers(map, resultsRef.current))
  }, [theme])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const footprintSource = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
    footprintSource?.setData(buildComplexFootprints(results))
    const markerSource = map.getSource(MARKER_SOURCE) as maplibregl.GeoJSONSource | undefined
    markerSource?.setData(buildComplexMarkers(results))
  }, [results])

  if (mapUnavailable) {
    const statusById = new Map(results.map((result) => [result.substation_id, priorityDisplayStatus(result)]))
    return <div className="map-runtime map-runtime-fallback" role="img" aria-label="세종 지역난방 단지 위치 지도">
      <span className="map-fallback-title">세종 1생활권</span>
      {complexes.map((complex) => <button aria-label={`${complex.name} 선택`} className={`map-fallback-marker status-${statusById.get(complex.id) ?? 'missing'}`} key={complex.id} onClick={() => onSelectComplex(complex.id)} style={fallbackPosition(complex.lat, complex.lng)} type="button"><span>{complex.id}</span></button>)}
      <span className="map-fallback-note">브라우저 지도 가속을 사용할 수 없어 위치 요약 지도를 표시합니다.</span>
      {loading && <div className="map-state">최신 Priority 평가를 불러오는 중입니다.</div>}
      {error && <div className="map-state error">운영 상태 연결 지연 · 단지 위치는 계속 표시됩니다.</div>}
    </div>
  }

  return <div className="map-runtime">
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
    {loading && <div className="map-state">최신 Priority 평가를 불러오는 중입니다.</div>}
    {error && <div className="map-state error">운영 상태 연결 지연 · 단지 위치는 계속 표시됩니다.</div>}
  </div>
}
