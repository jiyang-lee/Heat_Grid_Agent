"""Attribute RAG evaluation failures to retrieval, generation, or both."""

from __future__ import annotations

from collections import Counter
from typing import Any


FAILURE_ORIGINS = {
    "none",
    "retrieval",
    "generation",
    "mixed",
}

GENERATION_STATUSES = {
    "passed",
    "needs_review",
    "failed",
}


def _rule_failures(rule: dict[str, Any], *, answerable: bool, retrieval_hit: bool) -> list[str]:
    failures: list[str] = []
    if rule.get("json_valid") is False:
        failures.append("invalid_generation_json")
    if int(rule.get("error_count") or 0) > 0:
        failures.append("generation_error")
    if rule.get("citation_valid") is False:
        failures.append("invalid_citation")
    if rule.get("forbidden_claim_detected") is True:
        failures.append("forbidden_claim_detected")
    if rule.get("internal_label_leak_detected") is True:
        failures.append("internal_label_leak_detected")
    if not answerable and rule.get("answerable_policy_passed") is False:
        failures.append("unanswerable_policy_failed")
    if answerable and not retrieval_hit and rule.get("retrieval_miss_policy_passed") is False:
        failures.append("retrieval_miss_policy_failed")
    return failures


def _judge_failures(judge: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    review_reasons: list[str] = []
    recommendation = str(judge.get("overall_recommendation") or "").upper()
    hallucination = str(judge.get("hallucination_severity") or "").upper()

    if recommendation == "FAIL":
        failures.append("judge_recommendation_fail")
    elif recommendation == "REVISE":
        review_reasons.append("judge_recommendation_revise")

    if hallucination in {"MAJOR", "CRITICAL"}:
        failures.append(f"hallucination_{hallucination.lower()}")
    elif hallucination == "MINOR":
        review_reasons.append("hallucination_minor")

    for field in (
        "faithfulness",
        "operational_usefulness",
        "citation_accuracy_semantic",
        "answer_relevance",
    ):
        value = judge.get(field)
        if isinstance(value, (int, float)) and value < 3:
            review_reasons.append(f"low_{field}")
    return failures, review_reasons


def classify_case(
    dataset_row: dict[str, Any],
    automatic_row: dict[str, Any],
    judge_row: dict[str, Any],
) -> dict[str, Any]:
    """Classify one case while keeping retrieval and generation decisions separate."""

    case_id = str(dataset_row.get("case_id") or "")
    answerable = bool(dataset_row.get("answerable"))
    retrieval_hit = bool(dataset_row.get("retrieval_hit_at_5")) if answerable else False
    retrieval_status = "hit" if retrieval_hit else "miss"
    if not answerable:
        retrieval_status = "not_applicable"

    rule = automatic_row.get("rule_evaluation") or {}
    rule_failures = _rule_failures(rule, answerable=answerable, retrieval_hit=retrieval_hit)
    judge_failures, review_reasons = _judge_failures(judge_row)
    failure_reasons = [*rule_failures, *judge_failures]

    if failure_reasons:
        generation_status = "failed"
    elif review_reasons:
        generation_status = "needs_review"
    else:
        generation_status = "passed"

    safe_abstention = False
    if not answerable:
        safe_abstention = rule.get("answerable_policy_passed") is True
    elif not retrieval_hit:
        safe_abstention = rule.get("retrieval_miss_policy_passed") is True

    if not answerable:
        failure_origin = "none" if generation_status == "passed" and safe_abstention else "generation"
    elif retrieval_hit:
        failure_origin = "none" if generation_status == "passed" else "generation"
    elif safe_abstention and not failure_reasons:
        failure_origin = "retrieval"
    else:
        failure_origin = "mixed"

    return {
        "case_id": case_id,
        "answerable": answerable,
        "retrieval_status": retrieval_status,
        "generation_status": generation_status,
        "failure_origin": failure_origin,
        "safe_abstention": safe_abstention,
        "human_review_required": failure_origin != "none" or generation_status == "needs_review",
        "failure_reasons": failure_reasons,
        "review_reasons": review_reasons,
        "evidence": {
            "retrieval_hit_at_5": dataset_row.get("retrieval_hit_at_5"),
            "retrieval_miss_policy_passed": rule.get("retrieval_miss_policy_passed"),
            "answerable_policy_passed": rule.get("answerable_policy_passed"),
            "judge_recommendation": judge_row.get("overall_recommendation"),
            "hallucination_severity": judge_row.get("hallucination_severity"),
            "judge_confidence": judge_row.get("judge_confidence"),
        },
    }


def summarize_attributions(records: list[dict[str, Any]]) -> dict[str, Any]:
    origin_counts = Counter(record["failure_origin"] for record in records)
    generation_counts = Counter(record["generation_status"] for record in records)
    retrieval_counts = Counter(record["retrieval_status"] for record in records)
    return {
        "total_case_count": len(records),
        "failure_origin_counts": {key: origin_counts.get(key, 0) for key in sorted(FAILURE_ORIGINS)},
        "generation_status_counts": {key: generation_counts.get(key, 0) for key in sorted(GENERATION_STATUSES)},
        "retrieval_status_counts": dict(sorted(retrieval_counts.items())),
        "safe_abstention_count": sum(1 for record in records if record["safe_abstention"]),
        "human_review_required_count": sum(1 for record in records if record["human_review_required"]),
        "human_review_case_ids": [record["case_id"] for record in records if record["human_review_required"]],
    }
