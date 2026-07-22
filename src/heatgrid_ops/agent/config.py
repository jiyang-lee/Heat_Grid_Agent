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
class ModelPricing:
    model: str
    input_usd_per_1m: float
    cached_input_usd_per_1m: float
    output_usd_per_1m: float
    pricing_source: str


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    openai_model: str
    rag_top_k: int
    agent_max_iterations: int
    agent_evidence_threshold: float
    model_score_tolerance: float
    input_usd_per_1m: float
    cached_input_usd_per_1m: float
    output_usd_per_1m: float
    pricing_source: str
    rag_expanded_top_k: int = 10
    rag_max_top_k: int = 20
    rag_jsonl_min_top_score: float = 6.0
    rag_jsonl_min_unique_matches: int = 2
    answer_quality_enabled: bool = False
    answer_quality_threshold: float = 75.0
    answer_quality_baseline_version: str = (
        "answer-quality-policy.v2-100-rag-single-judge-draft"
    )
    model_pricing_overrides: tuple[ModelPricing, ...] = ()
