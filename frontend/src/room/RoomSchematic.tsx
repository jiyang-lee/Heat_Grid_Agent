/**
 * 기계실 아이소메트릭 스키매틱 — heating_agent.html renderRoom 이식.
 * 7종 설비 + 배관. 설비 상태색, 센서 미탑재 설비는 회색. 설비 클릭 → 선택.
 */

import type { Complex } from '../data/complexes'
import { MACHINES, PIPES, machineMonitored } from '../domain/machines'
import { machineStatus } from '../domain/model'
import { STATUS, type Tier } from '../domain/status'

const HW = 32
const HH = 16
const iso = (x: number, y: number) => ({ x: (x - y) * HW, y: (x + y) * HH })

interface Point {
  x: number
  y: number
}
interface Geo {
  top: string
  right: string
  left: string
  ctop: Point
  cbase: Point
}

function boxGeom(gx: number, gy: number, w: number, d: number, h: number): Geo {
  const bA = iso(gx, gy)
  const bB = iso(gx + w, gy)
  const bC = iso(gx + w, gy + d)
  const bD = iso(gx, gy + d)
  const up = (p: Point): Point => ({ x: p.x, y: p.y - h })
  const tA = up(bA)
  const tB = up(bB)
  const tC = up(bC)
  const tD = up(bD)
  const P = (p: Point) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`
  return {
    top: `${P(tA)} ${P(tB)} ${P(tC)} ${P(tD)}`,
    right: `${P(tB)} ${P(tC)} ${P(bC)} ${P(bB)}`,
    left: `${P(tD)} ${P(tC)} ${P(bC)} ${P(bD)}`,
    ctop: { x: (tA.x + tC.x) / 2, y: (tA.y + tC.y) / 2 },
    cbase: { x: (bA.x + bC.x) / 2, y: (bA.y + bC.y) / 2 },
  }
}

function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.round(((n >> 16) & 255) * f)
  const g = Math.round(((n >> 8) & 255) * f)
  const b = Math.round((n & 255) * f)
  return `rgb(${r},${g},${b})`
}

function IsoBox({ g, color, cls }: { g: Geo; color: string; cls: string }) {
  return (
    <g className={cls}>
      <polygon points={g.left} fill={shade(color, 0.42)} stroke="rgba(0,0,0,0.35)" strokeWidth={0.6} />
      <polygon points={g.right} fill={shade(color, 0.6)} stroke="rgba(0,0,0,0.35)" strokeWidth={0.6} />
      <polygon points={g.top} fill={shade(color, 0.95)} stroke="rgba(0,229,255,0.35)" strokeWidth={1} />
    </g>
  )
}

function Chip({ cx, cy, text, status }: { cx: number; cy: number; text: string; status: Tier }) {
  const c = STATUS[status].color
  const w = text.length * 12 + 20
  return (
    <g transform={`translate(${cx},${cy})`} style={{ pointerEvents: 'none' }}>
      <rect x={-w / 2} y={-13} width={w} height={24} rx={7} fill="rgba(4,10,26,0.85)" stroke={c} strokeWidth={1.4} />
      <circle cx={-w / 2 + 11} cy={-1} r={4} fill={c} />
      <text x={6} y={4} textAnchor="middle" fontFamily="var(--mono)" fontSize={12.5} fontWeight={700} fill={c}>
        {text}
      </text>
    </g>
  )
}

interface Props {
  complex: Complex
  selMachine: string | null
  onSelectMachine: (key: string) => void
}

export default function RoomSchematic({ complex, selMachine, onSelectMachine }: Props) {
  const OX = 360
  const OY = 140
  const st = machineStatus(complex.id)
  const geomOf: Record<string, Geo> = {}
  MACHINES.forEach((m) => (geomOf[m.key] = boxGeom(m.gx, m.gy, m.w, m.d, m.h)))

  const order = [...MACHINES].sort((m, n) => m.gx + m.gy - (n.gx + n.gy))

  return (
    <svg viewBox="0 0 900 560" preserveAspectRatio="xMidYMid meet">
      <g transform={`translate(${OX},${OY})`}>
        {/* 배관(바닥) */}
        {PIPES.map(([a, c], i) => {
          const p = geomOf[a].cbase
          const q = geomOf[c].cbase
          return (
            <g key={i}>
              <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="rgba(0,229,255,0.28)" strokeWidth={4} strokeLinecap="round" />
              <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="rgba(41,121,255,0.5)" strokeWidth={1.4} strokeDasharray="3 6" />
            </g>
          )
        })}
        {/* 설비 박스 */}
        {order.map((m) => {
          const s = st[m.key] ?? 'normal'
          const g = geomOf[m.key]
          const mon = machineMonitored(complex, m)
          const isU = s === 'urgent'
          const isSel = selMachine === m.key
          const cls = `clickable ${isU ? 'pulse' : ''} ${isSel ? 'sel' : ''}`
          const color = mon ? STATUS[s].color : '#5b6b86'
          return (
            <g key={m.key} className="clickable" onClick={() => onSelectMachine(m.key)}>
              <IsoBox g={g} color={color} cls={cls} />
              <Chip cx={g.ctop.x} cy={g.ctop.y - 12} text={mon ? STATUS[s].ko : '센서없음'} status={mon ? s : 'normal'} />
              <text
                x={g.cbase.x}
                y={g.cbase.y + 16}
                textAnchor="middle"
                fontFamily="var(--mono)"
                fontSize={10.5}
                fill="#9db8de"
                style={{ pointerEvents: 'none' }}
              >
                {m.name}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
