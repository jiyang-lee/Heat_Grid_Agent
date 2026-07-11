/**
 * MapLibre GL JS 지도: 다크/라이트 타일 + "내 단지만" 3D 돌출.
 *
 * - 배경: CARTO 또는 VITE_MAP_STYLE_URL 기반 스타일. 테마에 따라 전환.
 * - 내 31개 단지: complexFootprints를 fill-extrusion으로 3D 돌출
 * - 최신 Priority 평가 상태 → fill-extrusion-color 데이터 바인딩
 * - 단지 클릭 → onSelectComplex(id), 선택 단지는 시안 외곽선 강조
 */

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { PriorityEvaluationResult } from '../api/contracts'
import { mapStyleFor } from './mapConfig'
import { buildComplexFootprints, buildComplexMarkers, SEJONG_CENTER } from './footprints'

interface Props {
  selectedId: number | null
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
function addComplexLayers(
  map: maplibregl.Map,
  results: PriorityEvaluationResult[],
  selectedId: number | null,
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
  const markers = buildComplexMarkers(results)
  const footprintSource = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
  const markerSource = map.getSource('complex-markers') as maplibregl.GeoJSONSource | undefined
  if (footprintSource) footprintSource.setData(footprints)
  else map.addSource('complexes', { type: 'geojson', data: footprints })
  if (markerSource) markerSource.setData(markers)
  else map.addSource('complex-markers', { type: 'geojson', data: markers })

  if (!map.getLayer('complexes-3d')) {
    map.addLayer({
      id: 'complexes-3d',
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
  if (!map.getLayer('complexes-sel')) {
    map.addLayer({
      id: 'complexes-sel',
      type: 'line',
      source: 'complexes',
      filter: ['==', ['get', 'id'], selectedId ?? -1],
      paint: { 'line-color': '#00e5ff', 'line-width': 3, 'line-blur': 1 },
    })
  } else {
    map.setFilter('complexes-sel', ['==', ['get', 'id'], selectedId ?? -1])
  }

  if (!map.getLayer('complex-markers')) {
    map.addLayer({
      id: 'complex-markers',
      type: 'circle',
      source: 'complex-markers',
      paint: {
        'circle-radius': 7,
        'circle-color': [
          'match', ['get', 'status'],
          'urgent', '#ff1744',
          'high', '#ff8f00',
          'medium', '#ffd740',
          'low', '#00c853',
          'stale', '#64748b',
          '#334155',
        ],
        'circle-stroke-color': '#e2e8f0',
        'circle-stroke-width': 1.5,
        'circle-opacity': 0.95,
      },
    })
  }
}

export default function MapView({ selectedId, onSelectComplex, theme, results, loading, error }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // 최신 콜백을 ref로 유지(맵 초기화는 1회라 클로저 고정 방지)
  const onSelectRef = useRef(onSelectComplex)
  onSelectRef.current = onSelectComplex
  const resultsRef = useRef(results)
  resultsRef.current = results
  const selIdRef = useRef(selectedId)
  selIdRef.current = selectedId
  const themeRef = useRef(theme) // 실제 테마 변경 감지용

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapStyleFor(themeRef.current),
      center: SEJONG_CENTER,
      zoom: 13.3,
      pitch: 45,
      bearing: 0,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    // 마우스로 방향(회전)·기울기(pitch) 전환 활성화.
    map.dragRotate.enable()
    map.touchZoomRotate.enableRotation()
    map.keyboard.enable()
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true }), 'top-right')

    map.on('load', () => addComplexLayers(map, resultsRef.current, selIdRef.current))

    const selectFeature = (e: maplibregl.MapLayerMouseEvent) => {
      const f = e.features?.[0]
      const rawId = f?.properties?.id
      const id = typeof rawId === 'number' ? rawId : Number(rawId)
      if (Number.isInteger(id)) onSelectRef.current(id)
    }
    map.on('click', 'complexes-3d', selectFeature)
    map.on('click', 'complex-markers', selectFeature)
    map.on('mouseenter', 'complexes-3d', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'complexes-3d', () => {
      map.getCanvas().style.cursor = ''
    })
    map.on('mouseenter', 'complex-markers', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'complex-markers', () => {
      map.getCanvas().style.cursor = ''
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // 테마 변경 → 지도 스타일 교체 후 단지 레이어 재구성.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (themeRef.current === theme) return // 초기 마운트/동일 테마는 무시
    themeRef.current = theme
    map.setStyle(mapStyleFor(theme))
    whenStyleReady(map, () => addComplexLayers(map, resultsRef.current, selIdRef.current))
  }, [theme])

  // 선택 변경 시 외곽선 갱신
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => {
      if (map.getLayer('complexes-sel')) {
        map.setFilter('complexes-sel', ['==', ['get', 'id'], selectedId ?? -1])
      }
    }
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
  }, [selectedId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const footprintSource = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
    const markerSource = map.getSource('complex-markers') as maplibregl.GeoJSONSource | undefined
    footprintSource?.setData(buildComplexFootprints(results))
    markerSource?.setData(buildComplexMarkers(results))
  }, [results])

  return <div className="map-runtime">
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
    {loading && <div className="map-state">최신 Priority 평가를 불러오는 중입니다.</div>}
    {error && <div className="map-state error">Priority 평가 API에 연결할 수 없습니다.</div>}
  </div>
}
