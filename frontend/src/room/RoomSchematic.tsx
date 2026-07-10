/**
 * 기계실 관제 — 설비별 이미지 배치 뷰.
 *
 * 7종 설비를 각자의 이미지(없으면 kind 플레이스홀더)로 스테이지 폭 전반에 분산 배치.
 * 상태(정상/주의/긴급)·센서 미탑재(회색) 동적 반영, 설비 클릭 → 선택(DetailAside와 동기화).
 * 모든 단지 공통 1세트 이미지, 상태만 동적.
 */

import type { Complex } from '../data/complexes'
import { MACHINES, machineMonitored } from '../domain/machines'
import { useModel } from '../domain/ModelProvider'
import { STATUS } from '../domain/status'
import { machineImg } from './machineArt'

const BASE = 168 // 타일 기준 폭(px). scale로 설비별 조정.

interface Props {
  complex: Complex
  selMachine: string | null
  onSelectMachine: (key: string) => void
}

export default function RoomSchematic({ complex, selMachine, onSelectMachine }: Props) {
  const { machineStatus } = useModel()
  const st = machineStatus(complex.id)
  // 뒤(위)에 있는 타일이 먼저, 앞(아래) 타일이 나중에 그려지도록 ay 오름차순.
  const order = [...MACHINES].sort((m, n) => m.ay - n.ay)

  return (
    <div className="room2">
      {order.map((m) => {
        const s = st[m.key] ?? 'normal'
        const mon = machineMonitored(complex, m)
        const isU = mon && s === 'urgent'
        const isSel = selMachine === m.key
        const color = mon ? STATUS[s].color : '#5b6b86'
        const cls = `mtile clickable ${isU ? 'pulse' : ''} ${isSel ? 'sel' : ''} ${mon ? '' : 'sensor-off'}`.replace(/\s+/g, ' ').trim()
        return (
          <button
            key={m.key}
            type="button"
            className={cls}
            style={{ left: `${m.ax}%`, top: `${m.ay}%`, width: BASE * m.scale }}
            onClick={() => onSelectMachine(m.key)}
            title={m.name}
          >
            <span className="mchip" style={{ borderColor: color, color }}>
              <i className="mdot" style={{ background: color }} />
              {mon ? STATUS[s].ko : '센서없음'}
            </span>
            <img className="mimg" src={machineImg(m.key, m.kind)} alt={m.name} draggable={false} />
            <span className="mcap">{m.name}</span>
          </button>
        )
      })}
    </div>
  )
}
