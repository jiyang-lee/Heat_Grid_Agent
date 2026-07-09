/**
 * 단지 → MapLibre 3D 돌출용 GeoJSON.
 *
 * 데이터: src/data/complexes.ts (31개 단지), 상태색: domain/model.ts의 tier(overall).
 *
 * ⚠️ 실제 건물 footprint/층수가 없어 footprint는 정사각형 합성, 높이는 세대수 비례
 *    (heating_agent.html의 heightOf 이식)한 "시각 프록시"다. 실 GIS 확보 시 여기만 교체.
 */

import type { Feature, FeatureCollection, Polygon } from 'geojson'
import { complexes } from '../data/complexes'
import { overall } from '../domain/model'

/** 지도 초기 중심: 단지 좌표 평균 (세종 1생활권) */
export const SEJONG_CENTER: [number, number] = (() => {
  const n = complexes.length || 1
  let x = 0
  let y = 0
  for (const c of complexes) {
    x += c.lng
    y += c.lat
  }
  return [x / n, y / n]
})()

const households = complexes.map((c) => c.households)
const hhMin = Math.min(...households)
const hhMax = Math.max(...households)
const hhSpan = hhMax - hhMin || 1

const M_PER_DEG_LAT = 111320

function squareFootprint(lng: number, lat: number, halfMeters: number): number[][] {
  const dLat = halfMeters / M_PER_DEG_LAT
  const dLng = halfMeters / (M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180))
  return [
    [lng - dLng, lat - dLat],
    [lng + dLng, lat - dLat],
    [lng + dLng, lat + dLat],
    [lng - dLng, lat + dLat],
    [lng - dLng, lat - dLat],
  ]
}

export const complexFootprints: FeatureCollection<Polygon> = {
  type: 'FeatureCollection',
  features: complexes.map((c): Feature<Polygon> => {
    const norm = (c.households - hhMin) / hhSpan
    const height = Math.round(22 + norm * 62) // heightOf 이식
    const halfMeters = 30 + norm * 30
    return {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [squareFootprint(c.lng, c.lat, halfMeters)],
      },
      properties: {
        id: c.id,
        name: c.name,
        height,
        tier: overall(c.id),
      },
    }
  }),
}
