from __future__ import annotations

from typing import Literal

from heatgrid_ops.agent.answer_quality import (
    evaluate_against_baseline,
    needs_retrieval_expansion,
    select_answer_variant,
)
from heatgrid_ops.agent.run_models import AnswerQualityEvaluation


def _evaluation(
    value: int,
    *,
    citation_mismatch: bool = False,
    risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] = "NONE",
) -> AnswerQualityEvaluation:
    return AnswerQualityEvaluation(
        correctness=value,
        completeness=value,
        actionability=value,
        evidence_grounding=value,
        calibration=value,
        citation_mismatch=citation_mismatch,
        unsupported_claim_risk=risk,
        judge_confidence="HIGH",
    )


def test_weighted_quality_score_uses_reference_threshold() -> None:
    decision = evaluate_against_baseline(_evaluation(5))

    assert decision.score == 100.0
    assert decision.passed is True
    assert decision.hard_gate_failed is False


def test_hard_gate_rejects_answer_even_when_weighted_score_passes() -> None:
    evaluation = _evaluation(4, risk="MEDIUM")

    decision = evaluate_against_baseline(evaluation, threshold=70.0)

    assert decision.score == 80.0
    assert decision.passed is False
    assert decision.hard_gate_failed is True
    assert "unsupported_claim_risk" in decision.reasons


def test_citation_mismatch_is_recorded_but_not_a_v2_hard_gate() -> None:
    evaluation = _evaluation(5, citation_mismatch=True)

    decision = evaluate_against_baseline(evaluation)

    assert decision.passed is True
    assert decision.hard_gate_failed is False
    assert "citation_mismatch" in decision.reasons


def test_regenerated_answer_must_rank_higher_than_initial() -> None:
    initial = evaluate_against_baseline(_evaluation(2))
    regenerated = evaluate_against_baseline(_evaluation(5))

    selected, reason = select_answer_variant(initial, regenerated)

    assert selected == "regenerated"
    assert reason == "regenerated_answer_ranked_higher"


def test_higher_score_wins_when_both_rag_answers_are_below_baseline() -> None:
    initial = evaluate_against_baseline(_evaluation(3))
    regenerated = evaluate_against_baseline(
        _evaluation(3).model_copy(
            update={"completeness": 4, "actionability": 4, "calibration": 4}
        )
    )

    selected, _reason = select_answer_variant(initial, regenerated)

    assert initial.passed is False
    assert regenerated.passed is False
    assert regenerated.score > initial.score
    assert selected == "regenerated"


def test_tie_keeps_initial_answer() -> None:
    initial = evaluate_against_baseline(_evaluation(5))
    regenerated = evaluate_against_baseline(_evaluation(5))

    selected, _reason = select_answer_variant(initial, regenerated)

    assert selected == "initial"


def test_over_abstention_is_a_validated_hard_rule() -> None:
    evaluation = _evaluation(5).model_copy(update={"over_abstention": True})

    decision = evaluate_against_baseline(evaluation)

    assert decision.passed is False
    assert "over_abstention" in decision.reasons


def test_retrieval_insufficient_triggers_expansion_and_hard_gate() -> None:
    evaluation = _evaluation(5).model_copy(update={"retrieval_insufficient": True})

    decision = evaluate_against_baseline(evaluation)

    assert decision.passed is False
    assert decision.hard_gate_failed is True
    assert "retrieval_insufficient" in decision.reasons
    assert needs_retrieval_expansion(evaluation) is True
