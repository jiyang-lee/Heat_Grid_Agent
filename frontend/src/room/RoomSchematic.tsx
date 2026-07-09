/**
 * 기계실 아이소메트릭 스키매틱 — heating_agent.html renderRoom 이식 + 3D 렌더 느낌 업그레이드.
 * 7종 설비 + 배관. 설비 상태색, 센서 미탑재 설비는 회색. 설비 클릭 → 선택.
 *
 * 업그레이드: 금속 하이라이트(#spec) + 접지 그림자(#softShadow) + 바닥 반사 +
 *   설비 종류별 심볼/애니메이션(펌프 임펠러 회전 · 제어반 LED 점멸 · 열교환기 히트밴드).
 *   배관은 정적(긴급 연결 배관만 빨간 강조). 애니메이션은 감시되는 설비만.
 */

import type { Complex } from '../data/complexes'
import { MACHINES, PIPES, machineMonitored, type MachineKind } from '../domain/machines'
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
  /** 바닥 접지 타원 반경(px) */
  fw: number
  fh: number
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
    fw: (w + d) * HW * 0.5,
    fh: (w + d) * HH * 0.62,
  }
}

function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.round(((n >> 16) & 255) * f)
  const g = Math.round(((n >> 8) & 255) * f)
  const b = Math.round((n & 255) * f)
  return `rgb(${r},${g},${b})`
}

/** 3면 아이소 박스 + 금속 하이라이트 오버레이(#spec). */
function IsoBox({ g, color, cls }: { g: Geo; color: string; cls?: string }) {
  return (
    <g className={cls}>
      <polygon points={g.left} fill={shade(color, 0.42)} stroke="rgba(0,0,0,0.35)" strokeWidth={0.6} />
      <polygon points={g.right} fill={shade(color, 0.6)} stroke="rgba(0,0,0,0.35)" strokeWidth={0.6} />
      <polygon points={g.top} fill={shade(color, 0.95)} stroke="rgba(0,229,255,0.35)" strokeWidth={1} />
      {/* 금속 스펙큘러 하이라이트 (모든 상태색 공용) */}
      <polygon points={g.right} fill="url(#spec)" style={{ pointerEvents: 'none' }} />
      <polygon points={g.top} fill="url(#specTop)" style={{ pointerEvents: 'none' }} />
    </g>
  )
}

/** 설비 종류별 상단 심볼. animate=true(감시 중)일 때만 회전/점멸. */
function MachineSymbol({ kind, g, color, animate }: { kind: MachineKind; g: Geo; color: string; animate: boolean }) {
  const R = Math.max(7, g.fw * 0.34)
  if (kind === 'pump') {
    const bladeW = R * 0.34
    return (
      <g transform={`translate(${g.ctop.x.toFixed(1)},${g.ctop.y.toFixed(1)})`} style={{ pointerEvents: 'none' }}>
        <circle r={R * 1.05} fill="rgba(4,10,26,0.55)" stroke="rgba(0,229,255,0.3)" strokeWidth={0.8} />
        <g className={animate ? 'impeller' : undefined}>
          {[0, 45, 90, 135].map((a) => (
            <ellipse key={a} cx={0} cy={-R * 0.55} rx={bladeW} ry={R * 0.62} transform={`rotate(${a})`} fill="#cdd8ea" opacity={0.92} />
          ))}
          <circle r={R * 0.26} fill={color} stroke="rgba(0,0,0,0.4)" strokeWidth={0.6} />
        </g>
      </g>
    )
  }
  if (kind === 'panel') {
    const leds: { c: string; d: number }[] = [
      { c: color, d: 0 },
      { c: '#00e5ff', d: 0.4 },
      { c: '#00e676', d: 0.8 },
    ]
    return (
      <g transform={`translate(${g.ctop.x.toFixed(1)},${g.ctop.y.toFixed(1)})`} style={{ pointerEvents: 'none' }}>
        <rect x={-R} y={-R * 0.5} width={R * 2} height={R} rx={2} fill="rgba(4,10,26,0.6)" stroke="rgba(0,229,255,0.3)" strokeWidth={0.7} />
        {leds.map((l, i) => (
          <circle
            key={i}
            cx={-R * 0.6 + i * R * 0.6}
            cy={0}
            r={R * 0.2}
            fill={l.c}
            className={animate ? 'led' : undefined}
            style={{ animationDelay: `${l.d}s` }}
          />
        ))}
      </g>
    )
  }
  if (kind === 'hex') {
    return (
      <g transform={`translate(${g.ctop.x.toFixed(1)},${g.ctop.y.toFixed(1)})`} style={{ pointerEvents: 'none' }}>
        <ellipse rx={g.fw * 0.6} ry={g.fh * 0.55} fill={color} opacity={0.16} className={animate ? 'heatband' : undefined} />
      </g>
    )
  }
  if (kind === 'valve') {
    // 정적 핸드휠
    return (
      <g transform={`translate(${g.ctop.x.toFixed(1)},${g.ctop.y.toFixed(1)})`} style={{ pointerEvents: 'none' }}>
        <circle r={R * 0.8} fill="none" stroke="#cdd8ea" strokeWidth={1.6} opacity={0.85} />
        {[0, 60, 120].map((a) => (
          <line key={a} x1={0} y1={-R * 0.8} x2={0} y2={R * 0.8} stroke="#cdd8ea" strokeWidth={1.2} opacity={0.85} transform={`rotate(${a})`} />
        ))}
        <circle r={R * 0.18} fill={color} />
      </g>
    )
  }
  // tank: 심볼 없음
  return null
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
  const colorOf = (m: (typeof MACHINES)[number]): string =>
    machineMonitored(complex, m) ? STATUS[st[m.key] ?? 'normal'].color : '#5b6b86'

  const order = [...MACHINES].sort((m, n) => m.gx + m.gy - (n.gx + n.gy))
  const urgentSet = new Set(MACHINES.filter((m) => machineMonitored(complex, m) && (st[m.key] ?? 'normal') === 'urgent').map((m) => m.key))

  return (
    <svg viewBox="0 0 900 560" preserveAspectRatio="xMidYMid meet">
      <defs>
        {/* 금속 스펙큘러 — 우측면(대각) / 상단면 */}
        <linearGradient id="spec" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.34" />
          <stop offset="0.45" stopColor="#ffffff" stopOpacity="0.05" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="specTop" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.5" />
          <stop offset="0.5" stopColor="#ffffff" stopOpacity="0.1" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <filter id="softShadow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="4" />
        </filter>
      </defs>

      <g transform={`translate(${OX},${OY})`}>
        {/* 바닥 접지 그림자 */}
        {order.map((m) => {
          const g = geomOf[m.key]
          return <ellipse key={m.key} cx={g.cbase.x} cy={g.cbase.y + 3} rx={g.fw} ry={g.fh} fill="rgba(0,0,0,0.5)" filter="url(#softShadow)" />
        })}
        {/* 바닥 반사(설비를 base 기준 세로 미러, 저투명) */}
        {order.map((m) => {
          const g = geomOf[m.key]
          return (
            <g key={m.key} opacity={0.12} transform={`translate(0 ${(2 * g.cbase.y).toFixed(1)}) scale(1 -1)`} style={{ pointerEvents: 'none' }}>
              <IsoBox g={g} color={colorOf(m)} />
            </g>
          )
        })}
        {/* 배관(바닥) — 정적. 긴급 연결 배관만 빨간 강조. */}
        {PIPES.map(([a, c], i) => {
          const p = geomOf[a].cbase
          const q = geomOf[c].cbase
          const hot = urgentSet.has(a) || urgentSet.has(c)
          return (
            <g key={i}>
              <line
                x1={p.x}
                y1={p.y}
                x2={q.x}
                y2={q.y}
                stroke={hot ? 'rgba(255,23,68,0.45)' : 'rgba(0,229,255,0.28)'}
                strokeWidth={4}
                strokeLinecap="round"
              />
              <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke={hot ? 'rgba(255,90,110,0.7)' : 'rgba(41,121,255,0.5)'} strokeWidth={1.4} strokeDasharray="3 6" />
            </g>
          )
        })}
        {/* 설비 박스 + 심볼 */}
        {order.map((m) => {
          const s = st[m.key] ?? 'normal'
          const g = geomOf[m.key]
          const mon = machineMonitored(complex, m)
          const isU = mon && s === 'urgent'
          const isSel = selMachine === m.key
          const cls = `${isU ? 'pulse' : ''} ${isSel ? 'sel' : ''}`.trim()
          const color = mon ? STATUS[s].color : '#5b6b86'
          return (
            <g key={m.key} className="clickable" onClick={() => onSelectMachine(m.key)}>
              <g className={cls || undefined}>
                <IsoBox g={g} color={color} />
                <MachineSymbol kind={m.kind} g={g} color={color} animate={mon} />
              </g>
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
