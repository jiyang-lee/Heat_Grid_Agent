/**
 * 토큰·비용 지표 박스 — 에이전트 실행 결과의 token_usage를 표시. 상세 박스와 분리되어 위에 배치된다.
 * 박스 골격은 항상 고정 표시하고, 값이 아직 없으면(선택 직후/실행 중) 자리표시자(—)만 보여준다.
 */

import type { TokenUsage } from '../api/contracts'

interface Props {
  usage: TokenUsage | null
}

const DASH = '—'

export default function AgentStats({ usage }: Props) {
  const cost = usage?.cost_estimate

  return (
    <div className="aside-body">
      <div className="statgrid">
        <div className="stat">
          <div className="k">모델 호출</div>
          <div className="v">{usage ? usage.model_calls : DASH}</div>
        </div>
        <div className="stat">
          <div className="k">총 토큰</div>
          <div className="v">{usage ? usage.total_tokens.toLocaleString() : DASH}</div>
        </div>
        <div className="stat">
          <div className="k">입력 / 출력</div>
          <div className="v">
            {usage ? `${usage.input_tokens.toLocaleString()} / ${usage.output_tokens.toLocaleString()}` : DASH}
          </div>
        </div>
        <div className="stat">
          <div className="k">예상 비용</div>
          <div className="v">{usage ? `$${cost ? cost.total_cost_usd.toFixed(5) : '0'}` : DASH}</div>
        </div>
        <div className="stat full">
          <div className="k">단가 출처</div>
          <div className="v sm">{cost ? `${cost.model} · ${cost.pricing_source}` : DASH}</div>
        </div>
      </div>
    </div>
  )
}
