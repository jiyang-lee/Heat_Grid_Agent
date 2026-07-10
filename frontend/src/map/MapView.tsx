/**
 * MapLibre GL JS 지도: 다크 타일 + "내 단지만" 3D 돌출.
 *
 * - 배경: 기본 CARTO 다크 타일 또는 VITE_MAP_STYLE_URL의 사용자 지정 스타일
 * - 내 31개 단지: complexFootprints를 fill-extrusion으로 3D 돌출
 * - 상태(tier) → fill-extrusion-color 데이터 바인딩(긴급 빨강/주의 노랑/정상 초록)
 * - 단지 클릭 → onSelectComplex(id), 선택 단지는 시안 외곽선 강조
 */

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { PriorityEvaluationResult } from '../api/contracts'
import { mapStyle } from './mapConfig'
import { buildComplexFootprints, buildComplexMarkers, SEJONG_CENTER } from './footprints'

interface Props {
  selectedId: number | null
  onSelectComplex: (id: number) => void
  results: PriorityEvaluationResult[]
  loading: boolean
  error: boolean
}

export default function MapView({ selectedId, onSelectComplex, results, loading, error }: Props) {
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
      style: mapStyle,
      center: SEJONG_CENTER,
      zoom: 13.3,
      pitch: 45,
      bearing: 0,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    // 마우스로 방향(회전)·기울기(pitch) 전환 활성화.
    //  - 오른쪽 버튼 드래그 또는 Ctrl + 왼쪽 드래그: 회전 + 기울이기
    //  - 우상단 나침반: 드래그로 회전, 클릭하면 정북(N)으로 리셋
    map.dragRotate.enable()
    map.touchZoomRotate.enableRotation()
    map.keyboard.enable()
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true }), 'top-right')

    map.on('load', () => {
      map.addSource('complexes', { type: 'geojson', data: buildComplexFootprints(resultsRef.current) })
      map.addSource('complex-markers', { type: 'geojson', data: buildComplexMarkers(resultsRef.current) })
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
      // 선택 단지 외곽선(시안). 초기엔 아무것도 매칭 안 되게.
      map.addLayer({
        id: 'complexes-sel',
        type: 'line',
        source: 'complexes',
        filter: ['==', ['get', 'id'], -1],
        paint: {
          'line-color': '#00e5ff',
          'line-width': 3,
          'line-blur': 1,
        },
      })
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
    })

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
