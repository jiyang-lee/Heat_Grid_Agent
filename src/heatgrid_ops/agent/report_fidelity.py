from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from heatgrid_ops.agent.models import JsonObject


@dataclass(frozen=True, slots=True)
class ReportFidelityEvaluation:
    deterministic_score: float
    judge_score: float | None
    score: float
    passed: bool
    force_review: bool
    reasons: tuple[str, ...] = ()


def evaluate_report_fidelity(
    *,
    deterministic_score: float,
    judge_score: float | None,
    hard_gate: bool = False,
    judge_available: bool = True,
    threshold: float = 70.0,
) -> ReportFidelityEvaluation:
    bounded_deterministic = max(0.0, min(100.0, deterministic_score))
    bounded_judge = None if judge_score is None else max(0.0, min(100.0, judge_score))
    score = 40.0 if hard_gate else bounded_deterministic
    if bounded_judge is not None:
        score = min(score, bounded_judge)
    reasons: list[str] = []
    if hard_gate:
        reasons.append("hard_gate")
    if not judge_available:
        reasons.append("judge_unavailable")
    passed = score >= threshold and not hard_gate and judge_available
    return ReportFidelityEvaluation(
        deterministic_score=bounded_deterministic,
        judge_score=bounded_judge,
        score=score,
        passed=passed,
        force_review=not passed,
        reasons=tuple(reasons),
    )


def select_best_report_draft(
    drafts: Sequence[JsonObject],
    evaluations: Sequence[ReportFidelityEvaluation],
) -> tuple[JsonObject, ReportFidelityEvaluation]:
    if not drafts or not evaluations or len(drafts) != len(evaluations):
        raise ValueError("drafts and evaluations must contain matching entries")
    index = max(range(len(drafts)), key=lambda item: evaluations[item].score)
    return drafts[index], evaluations[index]


def judge_unavailable_selection(
    draft: JsonObject,
    *,
    deterministic_score: float,
) -> tuple[JsonObject, ReportFidelityEvaluation]:
    evaluation = evaluate_report_fidelity(
        deterministic_score=deterministic_score,
        judge_score=None,
        judge_available=False,
    )
    return draft, evaluation
