/** 수리 우선순위 사이드 — heating_agent.html renderAsideCity 이식. */

import { complexes } from '../data/complexes'
import { useModel } from '../domain/ModelProvider'
import { STATUS } from '../domain/status'

interface Props {
  selectedId: number | null
  onSelect: (id: number) => void
}

export default function PriorityAside({ selectedId, onSelect }: Props) {
  const { overall, counts } = useModel()
  // 종합상태 정상 제외, [긴급 수 → 주의 수 → 관리비단가] 내림차순
  const list = complexes
    .filter((b) => overall(b.id) !== 'normal')
    .map((b) => ({ b, c: counts(b.id), ov: overall(b.id) }))
    .sort((x, y) => y.c.urgent - x.c.urgent || y.c.caution - x.c.caution || y.b.unit - x.b.unit)

  if (!list.length) return <div className="empty">모든 단지 정상 운영 중</div>

  return (
    <>
      {list.map((it, i) => (
        <div
          key={it.b.id}
          className={`row ${selectedId === it.b.id ? 'active' : ''}`}
          title={it.b.name}
          onClick={() => onSelect(it.b.id)}
        >
          <div className="rank">{i + 1}</div>
          <div className="info">
            <div className="nm">
              {it.b.id}. {it.b.name}
            </div>
            <div className="ad">{it.b.addr}</div>
          </div>
          <div className="cnt">
            <span className="pill u">긴급 {it.c.urgent}</span>
            <span className="pill c">주의 {it.c.caution}</span>
          </div>
          <div className={`chip-st st-${it.ov}`}>{STATUS[it.ov].ko}</div>
        </div>
      ))}
    </>
  )
}
