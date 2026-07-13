from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.decision_policy import (
    DecisionContext,
    DecisionPolicy,
    default_decision_policy,
)
from heatgrid_ops.agent.models import JsonValue, ModelVerificationResult, OpsAgentOutput

LoopDecision = Literal[
    "expand_internal",
    "rerun_model",
    "diagnostic_worker",
    "request_human",
    "finalize",
]


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: LoopDecision
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_score: float = Field(ge=0.0, le=1.0)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: str
    decision_source: Literal["deterministic", "llm_guarded"] = "deterministic"


class OutputValidation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


def assess_evidence(
    *,
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
    model_verification: ModelVerificationResult | None,
    iteration: int,
    max_iterations: int,
    threshold: float,
    policy: DecisionPolicy | None = None,
    diagnostic_available: bool = False,
    force_review: bool = False,
) -> EvidenceAssessment:
    priority_context = _mapping(source_input.get("priority_context"))
    card = _mapping(priority_context.get("card"))
    priority = _mapping(priority_context.get("priority"))
    retrieval = _mapping(external_context.get("retrieval"))
    chunks = _list(retrieval.get("chunks"))
    site = _mapping(external_context.get("site"))
    weather = _mapping(external_context.get("weather"))

    score = 0.0
    missing: list[str] = []
    if card and priority:
        score += 0.35
    else:
        missing.append("우선순위 카드 또는 모델 판단 근거")

    if model_verification is None:
        missing.append("현재 활성 모델 재검증 결과")
    elif model_verification.status == "verified":
        score += 0.25
    elif model_verification.status == "partial":
        score += 0.12
        missing.append("모델 재검증에 필요한 전체 특성")
    else:
        missing.append("모델 재검증 가능 상태")

    if model_verification and model_verification.agreement is True:
        score += 0.1
    elif model_verification and model_verification.agreement is False:
        missing.append("저장된 예측값과 현재 활성 모델의 일치 확인")

    if len(chunks) >= 2:
        score += 0.2
    elif chunks:
        score += 0.1
        missing.append("독립 운영 참고자료")
    else:
        missing.append("고장 유형과 연결되는 운영 참고자료")

    if site.get("status") == "mapped":
        score += 0.05
    else:
        missing.append("설비 위치 및 구성 정보")

    if weather.get("status") == "available":
        score += 0.05
    elif weather.get("status") not in {"disabled", "not_configured"}:
        missing.append("운전 부하를 설명할 기상 정보")

    score = round(min(1.0, score), 4)
    review_required = bool(card.get("review_required")) or force_review
    priority_level = str(priority.get("priority_level") or "").lower()

    selected = (policy or default_decision_policy()).decide(
        DecisionContext(
            model_verification=model_verification,
            rag_chunk_count=len(chunks),
            review_required=review_required,
            evidence_score=score,
            evidence_threshold=threshold,
            iteration=iteration,
            max_iterations=max_iterations,
            diagnostic_available=diagnostic_available,
            priority_level=priority_level,
        )
    )
    if selected == "rerun_model":
        return _assessment(selected, score, missing, _RATIONALES[selected])
    if selected == "expand_internal":
        return _assessment(selected, score, missing, _RATIONALES[selected])
    if selected == "diagnostic_worker":
        return _assessment(selected, score, missing, _RATIONALES[selected])
    if selected == "request_human":
        return _assessment(selected, score, missing, _RATIONALES[selected])
    return _assessment(
        "finalize",
        score,
        missing,
        _RATIONALES["finalize"],
    )


def guard_llm_assessment(
    candidate: EvidenceAssessment,
    deterministic: EvidenceAssessment,
    *,
    iteration: int,
    max_iterations: int,
    model_verification: ModelVerificationResult | None,
) -> EvidenceAssessment:
    if iteration >= max_iterations and candidate.decision in {
        "expand_internal",
        "rerun_model",
    }:
        return deterministic.model_copy(update={"decision": "request_human"})
    if (
        candidate.decision in {"rerun_model", "finalize"}
        and candidate.decision != deterministic.decision
    ):
        return deterministic
    if (
        model_verification is not None
        and model_verification.agreement is False
        and model_verification.attempt < 2
    ):
        return deterministic.model_copy(update={"decision": "rerun_model"})
    return candidate.model_copy(
        update={
            "evidence_score": deterministic.evidence_score,
            "missing_evidence": deterministic.missing_evidence,
        }
    )


def validate_output(output: OpsAgentOutput, *, agent_mode: str) -> OutputValidation:
    issues: list[str] = []
    fields = {
        "상황 요약": output.summary.strip(),
        "조치 계획": output.action_plan.strip(),
        "주의 사항": output.caution.strip(),
    }
    for label, value in fields.items():
        if len(value) < 10:
            issues.append(f"{label}이 너무 짧습니다.")
    if output.summary == output.action_plan:
        issues.append("상황 요약과 조치 계획이 구분되지 않았습니다.")
    if (
        agent_mode == "llm"
        and "확정" in output.summary
        and "추정" not in output.caution
    ):
        issues.append("고장 원인을 확정 표현했지만 불확실성 주의가 없습니다.")
    score = max(0.0, 1.0 - 0.25 * len(issues))
    return OutputValidation(valid=not issues, score=score, issues=issues)


def _assessment(
    decision: LoopDecision,
    score: float,
    missing: list[str],
    rationale: str,
) -> EvidenceAssessment:
    confidence = min(1.0, score + (0.1 if decision == "finalize" else 0.0))
    return EvidenceAssessment(
        decision=decision,
        confidence=round(confidence, 4),
        evidence_score=score,
        missing_evidence=list(dict.fromkeys(missing)),
        rationale=rationale,
    )


def _mapping(value: JsonValue | None) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _list(value: JsonValue | None) -> list[JsonValue]:
    return value if isinstance(value, list) else []


_RATIONALES = {
    "rerun_model": "저장된 예측값과 활성 모델 결과가 달라 모델 입력을 다시 읽고 재검증합니다.",
    "expand_internal": "내부 운영 참고자료가 부족해 검색 범위와 조회 개수를 확장합니다.",
    "diagnostic_worker": "읽기 전용 진단 worker가 제한된 근거에서 고장 가설을 정리합니다.",
    "request_human": "검수 조건이 남아 있어 운영 답변과 함께 사람의 최종 판단을 요청합니다.",
    "finalize": "근거와 모델 재검증 결과가 기준을 충족해 답변 생성을 진행합니다.",
}
