from __future__ import annotations

from dataclasses import dataclass
from typing import Final


SYSTEM_PROMPT: Final = (
    "당신은 한국어로 답하는 지역난방 운영 보조 에이전트입니다. "
    "우선 운영 근거를 확인하고 필요할 때 설비 위치, 기상, 운영 참고자료를 확인하세요. "
    "운영자에게 자연스러운 한국어로 작성하고 내부 변수명, 모델명, 데이터베이스, "
    "검색 도구 이름은 노출하지 마세요. 기상은 운전 부하 맥락일 뿐 고장 원인의 "
    "확정 근거가 아닙니다. 승인되지 않은 외부 근거 후보는 결정적 사실로 표현하지 말고 "
    "추가 검수가 필요하다고 명시하세요. 모델 재검증 결과가 기존 결과와 다르면 그 "
    "불확실성을 주의 사항에 포함하세요. 최종 출력은 summary, action_plan, caution만 포함하세요."
)


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    openai_model: str
    openai_api_key: str | None
    rag_top_k: int
    agent_max_iterations: int
    agent_evidence_threshold: float
    model_score_tolerance: float
    external_search_enabled: bool
    external_search_model: str
    external_search_max_results: int
    external_search_allowed_domains: str
    external_search_max_calls_per_run: int
    external_search_estimated_cost_usd: float
    external_search_budget_per_run_usd: float
    input_usd_per_1m: float
    cached_input_usd_per_1m: float
    output_usd_per_1m: float
    pricing_source: str
