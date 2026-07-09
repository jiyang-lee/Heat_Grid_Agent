/** 단지·설비 상세 사이드 — heating_agent.html renderAsideRoom 이식. */

import type { Complex } from '../data/complexes'
import { MACHINES, machineMonitored } from '../domain/machines'
import { machineStatus } from '../domain/model'
import { STATUS, sev } from '../domain/status'
import WorkOrderPanel from './WorkOrderPanel'

interface Props {
  complex: Complex
  selMachine: string | null
  onSelectMachine: (key: string) => void
}

export default function DetailAside({ complex, selMachine, onSelectMachine }: Props) {
  const st = machineStatus(complex.id)
  // 설비 목록: 심각도 높은 순
  const order = [...MACHINES].sort((m, n) => sev(st[n.key] ?? 'normal') - sev(st[m.key] ?? 'normal'))

  return (
    <>
      <div className="aside-meta">
        <div className="bn">
          {complex.id}. {complex.name}
        </div>
        <div className="ba">{complex.addr}</div>
        <div className="statgrid">
          <div className="stat full">
            <div className="k">PreDist 설비 구성 · 센서 {complex.sensorCols}열</div>
            <div className="v sm">
              {complex.cfgKo} · {complex.groupsKo}
            </div>
          </div>
        </div>
      </div>
      <div className="aside-body">
        {order.map((m) => {
          const s = st[m.key] ?? 'normal'
          const mon = machineMonitored(complex, m)
          const active = selMachine === m.key ? 'active' : ''
          return (
            <div
              key={m.key}
              className={`row ${active} ${mon ? '' : 'sensor-off'}`}
              onClick={() => onSelectMachine(m.key)}
            >
              <div className="info">
                <div className="nm">{m.name}</div>
                <div className="ds">{m.desc}</div>
              </div>
              {mon ? (
                <div className={`chip-st st-${s}`}>{STATUS[s].ko}</div>
              ) : (
                <span className="tag-off">센서 미탑재</span>
              )}
            </div>
          )
        })}
        <WorkOrderPanel key={complex.id} complex={complex} />
      </div>
    </>
  )
}
