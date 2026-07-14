/**
 * MapLibre GL JS 지도: streets 라이트 지도 + 단지 2D 원형 마커.
 *
 * - 배경: MapTiler streets-v2 — mapConfig.mapStyleFor('light')
 * - 내 31개 단지: buildComplexMarkers 포인트를 circle 레이어로 표기
 * - 최신 Priority 평가 상태 → circle-color 데이터 바인딩
 * - 단지 클릭 → onSelectComplex(id)
 */

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { PriorityEvaluationResult } from '../api/contracts'
import { mapStyleFor } from './mapConfig'
import { buildComplexMarkers, SEJONG_CENTER } from './footprints'

interface Props {
  onSelectComplex: (id: number) => void
  results: PriorityEvaluationResult[]
  loading: boolean
  error: boolean
}

const MARKER_LAYER = 'complexes-points'

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
        'circle-color': [
          'match',
          ['get', 'status'],
          'urgent', '#ff1744',
          'high', '#ff8f00',
          'medium', '#ffd740',
          'low', '#00c853',
          'stale', '#64748b',
          /* missing */ '#334155',
        ],
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
      zoom: 13.3,
      pitch: 0, // 원형 마커 가독성을 위한 정사 시점(2D)
      bearing: 0,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.keyboard.enable()
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false, showCompass: false }), 'top-right')

    map.on('load', () => addComplexLayers(map, resultsRef.current))

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
