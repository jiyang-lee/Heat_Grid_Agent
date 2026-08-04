from heatgrid_ops.agent.report_fidelity import (
    evaluate_report_fidelity,
    judge_unavailable_selection,
    select_best_report_draft,
)


def test_hard_gate_caps_report_fidelity_at_forty() -> None:
    result = evaluate_report_fidelity(
        deterministic_score=100.0,
        judge_score=100.0,
        hard_gate=True,
    )

    assert result.score == 40.0
    assert result.force_review is True
    assert result.passed is False


def test_report_fidelity_uses_minimum_score() -> None:
    result = evaluate_report_fidelity(
        deterministic_score=92.0,
        judge_score=65.0,
    )

    assert result.score == 65.0
    assert result.force_review is True


def test_failed_drafts_select_the_best_available_draft() -> None:
    selected, evaluation = select_best_report_draft(
        [{"summary": "low"}, {"summary": "high"}],
        [
            evaluate_report_fidelity(deterministic_score=41.0, judge_score=41.0),
            evaluate_report_fidelity(deterministic_score=58.0, judge_score=58.0),
        ],
    )

    assert selected == {"summary": "high"}
    assert evaluation.score == 58.0


def test_unavailable_judge_keeps_current_draft_without_retry() -> None:
    draft, evaluation = judge_unavailable_selection(
        {"summary": "current"},
        deterministic_score=90.0,
    )

    assert draft == {"summary": "current"}
    assert evaluation.judge_score is None
    assert evaluation.force_review is True
