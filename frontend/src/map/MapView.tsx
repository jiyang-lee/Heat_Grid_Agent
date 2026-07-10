/**
 * MapLibre GL JS 지도: 다크/라이트 타일 + "내 단지만" 3D 돌출.
 *
 * - 배경: MapTiler dataviz-dark/light 스타일(mapConfig.ts, .env의 VITE_MAP_STYLE_URL). 테마에 따라 전환.
 * - 내 31개 단지: complexFootprints를 fill-extrusion으로 3D 돌출
 * - 상태(tier) → fill-extrusion-color 데이터 바인딩(긴급 빨강/주의 노랑/정상 초록)
 * - 단지 클릭 → onSelectComplex(id), 선택 단지는 시안 외곽선 강조
 */

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { hasMapStyle, mapStyleUrlFor } from './mapConfig'
import { SEJONG_CENTER, buildComplexFootprints } from './footprints'
import { useModel } from '../domain/ModelProvider'
import type { Tier } from '../domain/status'

interface Props {
  selectedId: number | null
  onSelectComplex: (id: number) => void
  theme: 'dark' | 'light'
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
function addComplexLayers(map: maplibregl.Map, overallFn: (id: number) => Tier, selId: number | null) {
  // 베이스맵 자체 3D 건물(예: Streets 'Building 3D') 제거.
  // MapLibre는 모든 fill-extrusion을 첫 돌출 레이어 위치에서 한 패스로 그려서,
  // 남겨두면 그 위 2D 레이어(도로·라벨)가 우리 단지 돌출을 덮어 안 보이게 된다.
  for (const l of map.getStyle().layers ?? []) {
    if (l.type === 'fill-extrusion' && l.id !== 'complexes-3d' && map.getLayer(l.id)) {
      map.removeLayer(l.id)
    }
  }

  const data = buildComplexFootprints(overallFn)
  const src = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
  if (src) src.setData(data)
  else map.addSource('complexes', { type: 'geojson', data })

  if (!map.getLayer('complexes-3d')) {
    map.addLayer({
      id: 'complexes-3d',
      type: 'fill-extrusion',
      source: 'complexes',
      paint: {
        'fill-extrusion-color': [
          'match',
          ['get', 'tier'],
          'urgent', '#ff1744',
          'caution', '#ffc400',
          /* normal */ '#00e676',
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
      filter: ['==', ['get', 'id'], selId ?? -1],
      paint: { 'line-color': '#00e5ff', 'line-width': 3, 'line-blur': 1 },
    })
  } else {
    map.setFilter('complexes-sel', ['==', ['get', 'id'], selId ?? -1])
  }
}

export default function MapView({ selectedId, onSelectComplex, theme }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const { overall } = useModel()
  // 최신 값을 ref로 유지(맵 초기화는 1회라 클로저 고정 방지)
  const onSelectRef = useRef(onSelectComplex)
  onSelectRef.current = onSelectComplex
  const overallRef = useRef(overall)
  overallRef.current = overall
  const selIdRef = useRef(selectedId)
  selIdRef.current = selectedId
  const themeRef = useRef(theme) // 실제 테마 변경 감지용

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    if (!hasMapStyle) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapStyleUrlFor(themeRef.current),
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

    map.on('load', () => addComplexLayers(map, overallRef.current, selIdRef.current))

    map.on('click', 'complexes-3d', (e) => {
      const f = e.features?.[0]
      const id = f?.properties?.id
      if (typeof id === 'number') onSelectRef.current(id)
    })
    map.on('mouseenter', 'complexes-3d', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'complexes-3d', () => {
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
    map.setStyle(mapStyleUrlFor(theme))
    whenStyleReady(map, () => addComplexLayers(map, overallRef.current, selIdRef.current))
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

  // 모델 tier(백엔드 우선순위) 변경 시 지도 색 데이터 갱신
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => {
      const src = map.getSource('complexes') as maplibregl.GeoJSONSource | undefined
      if (src) src.setData(buildComplexFootprints(overall))
    }
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
  }, [overall])

  if (!hasMapStyle) {
    return (
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--app-text)' }}>
        <p>
          지도 스타일이 설정되지 않았습니다. <code>.env</code>의 <code>VITE_MAP_STYLE_URL</code>를 확인하세요.
        </p>
      </div>
    )
  }

  return <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
}
