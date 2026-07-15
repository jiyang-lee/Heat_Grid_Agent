"""Rule-based automatic answer evaluation utilities.

This module evaluates only mechanically checkable signals. It does not call an
LLM and does not attempt semantic faithfulness or human-quality scoring.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

NOT_CALCULATED = "NOT_CALCULATED"

ABSTENTION_EXPRESSIONS = [
    "현재 검색된 근거만으로는",
    "추가 문서",
    "현장 확인",
    "확인하기 어렵",
    "판단하기 어렵",
    "확인할 수 없습니다",
    "제공된 근거에서는",
]

FORBIDDEN_INPUT_LABELS = [
    "expected_answer_points",
    "relevant_chunk_ids",
    "partially_relevant_chunk_ids",
    "forbidden_claims",
    "human_scores",
    "automated_scores",
    "label_status",
]


def resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in resolve_repo_path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    target = resolve_repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_text(text: str) -> str:
    lowered = text.lower()
    return re.sub(r"\s+", " ", lowered)


def tokenize_point(point: str) -> set[str]:
    text = normalize_text(point)
    raw_tokens = re.findall(r"[a-z0-9가-힣_/-]+", text)
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "is",
        "are",
        "be",
        "can",
        "should",
        "with",
        "without",
        "do",
        "not",
        "확인",
        "필요",
        "있습니다",
        "합니다",
    }
    return {token for token in raw_tokens if len(token) >= 3 and token not in stopwords}


def expected_point_covered(point: str, answer: str) -> bool:
    answer_norm = normalize_text(answer)
    point_norm = normalize_text(point)
    if point_norm and point_norm in answer_norm:
        return True
    tokens = tokenize_point(point)
    if not tokens:
        return False
    overlap = {token for token in tokens if token in answer_norm}
    threshold = max(1, min(3, len(tokens)))
    return len(overlap) >= threshold


def calculate_coverage(expected_points: list[str], answer: str) -> tuple[float | None, list[int]]:
    if not expected_points:
        return None, []
    covered = [idx for idx, point in enumerate(expected_points) if expected_point_covered(point, answer)]
    return len(covered) / len(expected_points), covered


def forbidden_claim_detected(forbidden_claims: list[str], answer: str) -> tuple[bool, list[str]]:
    answer_norm = normalize_text(answer)
    hits: list[str] = []
    for claim in forbidden_claims:
        claim_norm = normalize_text(claim)
        if claim_norm and claim_norm in answer_norm:
            hits.append(claim)
            continue
        # The dataset stores many forbidden claims as English instructions.
        # Exact Korean semantic detection is intentionally not attempted here.
    return bool(hits), hits


def citation_valid(cited_chunk_ids: list[str], retrieved_chunk_ids: list[str]) -> bool:
    retrieved = set(retrieved_chunk_ids)
    return all(isinstance(chunk_id, str) and chunk_id in retrieved and not looks_like_document_id(chunk_id) for chunk_id in cited_chunk_ids)


def looks_like_document_id(value: str) -> bool:
    return value.startswith("doc_") or value.endswith(".pdf") or " " in value


def abstention_expression_detected(answer: str) -> bool:
    return any(expression in answer for expression in ABSTENTION_EXPRESSIONS)


def retrieval_miss_policy_passed(generated: dict[str, Any], dataset_row: dict[str, Any]) -> bool | None:
    if dataset_row.get("answerable") is False:
        return None
    if dataset_row.get("retrieval_hit_at_5") is True:
        return None
    cited = generated.get("cited_chunk_ids") or []
    return len(cited) == 0 and abstention_expression_detected(generated.get("generated_answer") or "")


def answerable_policy_passed(generated: dict[str, Any], dataset_row: dict[str, Any]) -> bool | None:
    if dataset_row.get("answerable") is True:
        return None
    cited = generated.get("cited_chunk_ids") or []
    return len(cited) == 0 and abstention_expression_detected(generated.get("generated_answer") or "")


def detect_internal_label_leak(answer: str) -> list[str]:
    return [label for label in FORBIDDEN_INPUT_LABELS if label in answer]


def evaluate_case(generated: dict[str, Any], dataset_row: dict[str, Any]) -> dict[str, Any]:
    answer = generated.get("generated_answer") or ""
    expected_points = dataset_row.get("expected_answer_points") or []
    forbidden_claims = dataset_row.get("forbidden_claims") or []
    cited_chunk_ids = generated.get("cited_chunk_ids") or []
    retrieved_chunk_ids = dataset_row.get("retrieved_chunk_ids") or []
    coverage_rate, covered_indexes = calculate_coverage(expected_points, answer)
    forbidden_detected, forbidden_hits = forbidden_claim_detected(forbidden_claims, answer)
    warnings = generated.get("warnings") or []
    error = generated.get("error")
    json_valid = isinstance(generated, dict) and generated.get("case_id") == dataset_row.get("case_id")

    return {
        "case_id": generated.get("case_id"),
        "query": generated.get("query"),
        "rule_evaluation": {
            "coverage_rate": coverage_rate,
            "covered_expected_answer_point_indexes": covered_indexes,
            "expected_answer_point_count": len(expected_points),
            "forbidden_claim_detected": forbidden_detected,
            "forbidden_claim_hits": forbidden_hits,
            "citation_exists": bool(cited_chunk_ids),
            "citation_valid": citation_valid(cited_chunk_ids, retrieved_chunk_ids),
            "retrieval_miss_policy_passed": retrieval_miss_policy_passed(generated, dataset_row),
            "answerable_policy_passed": answerable_policy_passed(generated, dataset_row),
            "abstention_expression_detected": abstention_expression_detected(answer),
            "json_valid": json_valid,
            "warning_count": len(warnings),
            "error_count": 1 if error else 0,
            "internal_label_leak_detected": bool(detect_internal_label_leak(answer)),
            "internal_label_leak_hits": detect_internal_label_leak(answer),
        },
        "not_calculated": {
            "faithfulness": NOT_CALCULATED,
            "hallucination_severity": NOT_CALCULATED,
            "operational_usefulness": NOT_CALCULATED,
            "citation_accuracy_semantic": NOT_CALCULATED,
            "human_score": NOT_CALCULATED,
            "llm_judge_score": NOT_CALCULATED,
        },
        "quality_status": {
            "rule_based_completed": True,
            "llm_judge_completed": False,
            "human_review_completed": False,
        },
    }


def summarize_results(records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage_values = [
        record["rule_evaluation"]["coverage_rate"]
        for record in records
        if record["rule_evaluation"]["coverage_rate"] is not None
    ]
    citation_values = [record["rule_evaluation"]["citation_valid"] for record in records]
    miss_values = [
        record["rule_evaluation"]["retrieval_miss_policy_passed"]
        for record in records
        if record["rule_evaluation"]["retrieval_miss_policy_passed"] is not None
    ]
    answerable_false_values = [
        record["rule_evaluation"]["answerable_policy_passed"]
        for record in records
        if record["rule_evaluation"]["answerable_policy_passed"] is not None
    ]
    return {
        "total_case_count": len(records),
        "coverage_average": sum(coverage_values) / len(coverage_values) if coverage_values else None,
        "coverage_evaluated_count": len(coverage_values),
        "citation_valid_ratio": sum(1 for value in citation_values if value) / len(citation_values) if citation_values else None,
        "forbidden_claim_detected_count": sum(1 for record in records if record["rule_evaluation"]["forbidden_claim_detected"]),
        "retrieval_miss_policy_pass_ratio": sum(1 for value in miss_values if value) / len(miss_values) if miss_values else None,
        "retrieval_miss_policy_evaluated_count": len(miss_values),
        "answerable_false_pass_ratio": sum(1 for value in answerable_false_values if value) / len(answerable_false_values) if answerable_false_values else None,
        "answerable_false_evaluated_count": len(answerable_false_values),
        "warning_total": sum(record["rule_evaluation"]["warning_count"] for record in records),
        "error_total": sum(record["rule_evaluation"]["error_count"] for record in records),
        "json_valid_count": sum(1 for record in records if record["rule_evaluation"]["json_valid"]),
        "internal_label_leak_count": sum(1 for record in records if record["rule_evaluation"]["internal_label_leak_detected"]),
        "not_calculated": {
            "faithfulness": NOT_CALCULATED,
            "hallucination_severity": NOT_CALCULATED,
            "operational_usefulness": NOT_CALCULATED,
            "citation_accuracy_semantic": NOT_CALCULATED,
            "human_score": NOT_CALCULATED,
            "llm_judge_score": NOT_CALCULATED,
        },
    }
