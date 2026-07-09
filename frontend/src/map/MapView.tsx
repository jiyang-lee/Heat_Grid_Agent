/**
 * MapLibre GL JS 지도: 다크 타일 + "내 단지만" 3D 돌출.
 *
 * - 배경: MapTiler 다크 스타일(mapConfig.ts, .env의 VITE_MAP_STYLE_URL)
 * - 내 31개 단지: complexFootprints를 fill-extrusion으로 3D 돌출
 * - 상태(tier) → fill-extrusion-color 데이터 바인딩(긴급 빨강/주의 노랑/정상 초록)
 * - 단지 클릭 → onSelectComplex(id), 선택 단지는 시안 외곽선 강조
 */

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { hasMapStyle, mapStyleUrl } from './mapConfig'
import { SEJONG_CENTER, complexFootprints } from './footprints'

interface Props {
  selectedId: number | null
  onSelectComplex: (id: number) => void
}

export default function MapView({ selectedId, onSelectComplex }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // 최신 콜백을 ref로 유지(맵 초기화는 1회라 클로저 고정 방지)
  const onSelectRef = useRef(onSelectComplex)
  onSelectRef.current = onSelectComplex

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    if (!hasMapStyle) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapStyleUrl,
      center: SEJONG_CENTER,
      zoom: 14,
      pitch: 55,
      bearing: -18,
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
      map.addSource('complexes', { type: 'geojson', data: complexFootprints })
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
    })

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

  if (!hasMapStyle) {
    return (
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: '#e5e7eb' }}>
        <p>
          지도 스타일이 설정되지 않았습니다. <code>.env</code>의 <code>VITE_MAP_STYLE_URL</code>를 확인하세요.
        </p>
      </div>
    )
  }

  return <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
}
