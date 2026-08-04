from __future__ import annotations

from dataclasses import dataclass

from heatgrid_ops.agent.run_models import AnswerQualityEvaluation


ANSWER_QUALITY_BASELINE_VERSION = "answer-quality-policy.v2-100-rag-single-judge-draft"
DEFAULT_ANSWER_QUALITY_THRESHOLD = 75.0
ANSWER_QUALITY_WEIGHTS = {
    "correctness": 0.30,
    "completeness": 0.15,
    "actionability": 0.20,
    "evidence_grounding": 0.25,
    "calibration": 0.10,
}


@dataclass(frozen=True, slots=True)
class AnswerQualityDecision:
    score: float
    passed: bool
    hard_gate_failed: bool
    reasons: tuple[str, ...]


def evaluate_against_baseline(
    evaluation: AnswerQualityEvaluation,
    *,
    threshold: float = DEFAULT_ANSWER_QUALITY_THRESHOLD,
) -> AnswerQualityDecision:
    weighted = sum(
        getattr(evaluation, name) * weight
        for name, weight in ANSWER_QUALITY_WEIGHTS.items()
    )
    score = round(weighted / 5.0 * 100.0, 2)
    reasons: list[str] = []
    if score < threshold:
        reasons.append("score_below_baseline")
    if evaluation.correctness <= 2:
        reasons.append("low_correctness")
    if evaluation.evidence_grounding <= 2:
        reasons.append("low_evidence_grounding")
    if evaluation.citation_mismatch:
        reasons.append("citation_mismatch")
    if evaluation.over_abstention:
        reasons.append("over_abstention")
    if evaluation.retrieval_insufficient:
        reasons.append("retrieval_insufficient")
    if evaluation.unsupported_claim_risk in {"MEDIUM", "HIGH"}:
        reasons.append("unsupported_claim_risk")
    reasons.extend(
        reason.strip()
        for reason in evaluation.failure_reasons
        if reason.strip() and reason.strip() not in reasons
    )
    hard_gate_failed = any(
        reason in reasons
        for reason in (
            "low_correctness",
            "low_evidence_grounding",
            "over_abstention",
            "retrieval_insufficient",
            "unsupported_claim_risk",
        )
    )
    return AnswerQualityDecision(
        score=score,
        passed=score >= threshold and not hard_gate_failed,
        hard_gate_failed=hard_gate_failed,
        reasons=tuple(reasons),
    )


def needs_retrieval_expansion(evaluation: AnswerQualityEvaluation) -> bool:
    return evaluation.retrieval_insufficient


def select_answer_variant(
    initial: AnswerQualityDecision,
    regenerated: AnswerQualityDecision,
) -> tuple[str, str]:
    initial_rank = (not initial.hard_gate_failed, initial.score)
    regenerated_rank = (not regenerated.hard_gate_failed, regenerated.score)
    if regenerated_rank > initial_rank:
        return "regenerated", "regenerated_answer_ranked_higher"
    return "initial", "initial_answer_kept_on_tie_or_regression"


def strict_revision_feedback(evaluation: AnswerQualityEvaluation) -> list[str]:
    feedback = [
        "Support every factual and operational claim with the supplied stage evidence.",
        "Clearly distinguish candidate causes from confirmed diagnoses.",
        "Provide concrete verification steps and operator actions without inventing facts.",
        "State uncertainty and missing evidence explicitly.",
    ]
    feedback.extend(
        f"Correct this quality issue: {reason}"
        for reason in evaluation.failure_reasons
        if reason.strip()
    )
    if evaluation.over_abstention:
        feedback.append(
            "Answer supported parts directly instead of abstaining from the whole question."
        )
    if evaluation.retrieval_insufficient:
        feedback.append(
            "Use the expanded and reranked evidence, while stating any remaining gap."
        )
    return feedback
