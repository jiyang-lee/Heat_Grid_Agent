/**
 * 설비 이미지 소스.
 *
 * 실제 이미지를 받으면 `src/assets/machines/`에 넣고 아래 MACHINE_IMG에 매핑한다.
 *   예) import hex from '../assets/machines/hex.png'
 *       export const MACHINE_IMG = { hex, pump1: pump, pump2: pump, ... }
 * 매핑이 없는 설비는 kind별 임시 플레이스홀더(강철 실루엣 SVG data URI)로 대체된다.
 */

import type { MachineKind } from '../domain/machines'
import exp from '../assets/machines/exp.png'
import hex from '../assets/machines/hex.png'
import pump1 from '../assets/machines/pump1.png'
import pump2 from '../assets/machines/pump2.png'
import makeup from '../assets/machines/makeup.png'
import prv from '../assets/machines/prv.png'
import ctrl from '../assets/machines/ctrl.png'

/** 실제 이미지 매핑. key = Machine.key */
export const MACHINE_IMG: Partial<Record<string, string>> = { exp, hex, pump1, pump2, makeup, prv, ctrl }

// --- kind별 임시 플레이스홀더 (배경 투명, 강철 톤) ---------------------------

const STEEL = '#8fa4bd'
const STEEL_D = '#5b6c85'
const STEEL_L = '#c7d4e6'
const EDGE = '#3a4762'

function uri(inner: string): string {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>` +
    `<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>` +
    `<stop offset='0' stop-color='${STEEL_L}'/><stop offset='0.5' stop-color='${STEEL}'/><stop offset='1' stop-color='${STEEL_D}'/>` +
    `</linearGradient></defs>${inner}</svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

const PLACEHOLDER: Record<MachineKind, string> = {
  tank: uri(
    `<rect x='66' y='30' width='68' height='150' rx='30' fill='url(#g)' stroke='${EDGE}' stroke-width='3'/>` +
      `<ellipse cx='100' cy='36' rx='34' ry='12' fill='${STEEL_L}' stroke='${EDGE}' stroke-width='2'/>` +
      `<rect x='84' y='14' width='32' height='18' rx='4' fill='${STEEL_D}'/>`,
  ),
  hex: uri(
    `<rect x='40' y='40' width='120' height='120' rx='8' fill='url(#g)' stroke='${EDGE}' stroke-width='3'/>` +
      [56, 76, 96, 116, 136].map((y) => `<line x1='48' y1='${y}' x2='152' y2='${y}' stroke='${EDGE}' stroke-width='3' opacity='0.55'/>`).join('') +
      `<circle cx='40' cy='60' r='9' fill='${STEEL_D}'/><circle cx='160' cy='140' r='9' fill='${STEEL_D}'/>`,
  ),
  pump: uri(
    `<rect x='96' y='96' width='84' height='58' rx='8' fill='url(#g)' stroke='${EDGE}' stroke-width='3'/>` +
      `<circle cx='72' cy='118' r='46' fill='url(#g)' stroke='${EDGE}' stroke-width='3'/>` +
      `<circle cx='72' cy='118' r='18' fill='${STEEL_D}'/>` +
      `<rect x='40' y='158' width='140' height='16' rx='4' fill='${STEEL_D}'/>`,
  ),
  valve: uri(
    `<rect x='30' y='104' width='140' height='30' rx='6' fill='url(#g)' stroke='${EDGE}' stroke-width='3'/>` +
      `<rect x='86' y='60' width='28' height='50' fill='${STEEL_D}'/>` +
      `<circle cx='100' cy='50' r='26' fill='none' stroke='${STEEL_L}' stroke-width='7'/>` +
      `<line x1='74' y1='50' x2='126' y2='50' stroke='${STEEL_L}' stroke-width='5'/>` +
      `<line x1='100' y1='24' x2='100' y2='76' stroke='${STEEL_L}' stroke-width='5'/>`,
  ),
  panel: uri(
    `<rect x='52' y='24' width='96' height='152' rx='8' fill='url(#g)' stroke='${EDGE}' stroke-width='3'/>` +
      `<rect x='64' y='40' width='72' height='90' rx='4' fill='${STEEL_D}'/>` +
      `<circle cx='80' cy='150' r='7' fill='#00e676'/><circle cx='100' cy='150' r='7' fill='#ffc400'/><circle cx='120' cy='150' r='7' fill='#00e5ff'/>`,
  ),
}

/** 설비 이미지 URL — 실제 매핑 우선, 없으면 kind 플레이스홀더. */
export function machineImg(key: string, kind: MachineKind): string {
  return MACHINE_IMG[key] ?? PLACEHOLDER[kind]
}
