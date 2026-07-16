/**
 * 단지 → MapLibre 3D 돌출용 GeoJSON.
 *
 * 데이터: 정적 위치는 complexes.ts, 운영 상태는 Priority 평가 API 결과를 사용한다.
 *
 * ⚠️ 실제 건물 footprint/층수가 없어 footprint는 정사각형 합성, 높이는 세대수 비례
 *    (heating_agent.html의 heightOf 이식)한 "시각 프록시"다. 실 GIS 확보 시 여기만 교체.
 */

import type { Feature, FeatureCollection, Point, Polygon } from 'geojson'
import type { PriorityEvaluationResult } from '../api/contracts'
import { complexes } from '../data/complexes'
import { priorityDisplayStatus } from '../domain/priority'

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

export function buildComplexFootprints(results: readonly PriorityEvaluationResult[]): FeatureCollection<Polygon> {
  const byId = new Map(results.map((result) => [result.substation_id, result]))
  return {
  type: 'FeatureCollection',
  features: complexes.map((c): Feature<Polygon> => {
    const result = byId.get(c.id)
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
        status: priorityDisplayStatus(result),
        priorityLevel: result?.priority_level ?? null,
        priorityScore: result?.priority_score ?? null,
        priorityRank: result?.priority_rank ?? null,
        freshness: result?.freshness_status ?? 'missing',
      },
    }
  }),
  }
}

export function buildComplexMarkers(results: readonly PriorityEvaluationResult[]): FeatureCollection<Point> {
  const byId = new Map(results.map((result) => [result.substation_id, result]))
  return {
    type: 'FeatureCollection',
    features: complexes.map((complex): Feature<Point> => {
      const result = byId.get(complex.id)
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [complex.lng, complex.lat] },
        properties: {
          id: complex.id,
          name: complex.name,
          status: priorityDisplayStatus(result),
          priorityLevel: result?.priority_level ?? null,
          priorityScore: result?.priority_score ?? null,
          priorityRank: result?.priority_rank ?? null,
          freshness: result?.freshness_status ?? 'missing',
        },
      }
    }),
  }
}
