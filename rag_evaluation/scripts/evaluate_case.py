"""Evaluate one HeatGrid retrieval dataset case."""

from __future__ import annotations

from typing import Any

from evaluation_utils import (
    hit_rate_at_k,
    ndcg_at_k,
    normalize_retrieved_chunk_ids,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    safe_list,
)


DEFAULT_K_VALUES = (1, 3, 5)
DEFAULT_NDCG_K = 5


def evaluate_case(
    case: dict[str, Any],
    retrieved_items: list[Any],
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    ndcg_k: int = DEFAULT_NDCG_K,
) -> dict[str, Any]:
    relevant_ids = set(str(value) for value in safe_list(case.get("relevant_chunk_ids")))
    partial_ids = set(str(value) for value in safe_list(case.get("partially_relevant_chunk_ids")))
    overlapping_label_ids = relevant_ids & partial_ids
    retrieved_ids, duplicate_count = normalize_retrieved_chunk_ids(retrieved_items)
    answerable = bool(case.get("answerable", True))
    warnings: list[str] = []

    if overlapping_label_ids:
        warnings.append("overlapping_relevant_partial_labels:" + ",".join(sorted(overlapping_label_ids)))
    if duplicate_count:
        warnings.append(f"duplicate_retrieved_chunks_deduped:{duplicate_count}")
    if not retrieved_ids:
        warnings.append("empty_retrieval")
    if answerable and not relevant_ids:
        warnings.append("answerable_case_without_relevant_labels")

    excluded = (not answerable) or (not relevant_ids)
    exclusion_reason = None
    if not answerable:
        exclusion_reason = "answerable_false"
    elif not relevant_ids:
        exclusion_reason = "missing_relevant_labels"

    metrics: dict[str, float | None] = {}
    for k in k_values:
        if excluded:
            metrics[f"recall_at_{k}"] = None
            metrics[f"precision_at_{k}"] = None
            metrics[f"hit_rate_at_{k}"] = None
        else:
            metrics[f"recall_at_{k}"] = recall_at_k(retrieved_ids, relevant_ids, k)
            metrics[f"precision_at_{k}"] = precision_at_k(retrieved_ids, relevant_ids, k)
            metrics[f"hit_rate_at_{k}"] = hit_rate_at_k(retrieved_ids, relevant_ids, k)
    metrics["mrr"] = None if excluded else reciprocal_rank(retrieved_ids, relevant_ids)
    metrics[f"ndcg_at_{ndcg_k}"] = None if excluded else ndcg_at_k(
        retrieved_ids,
        relevant_ids,
        partial_ids,
        ndcg_k,
    )

    return {
        "case_id": case.get("case_id"),
        "query": case.get("query"),
        "category": case.get("category"),
        "difficulty": case.get("difficulty"),
        "query_intent": case.get("query_intent"),
        "answerable": answerable,
        "label_status": case.get("label_status"),
        "review_required": case.get("review_required"),
        "excluded_from_macro_metrics": excluded,
        "exclusion_reason": exclusion_reason,
        "relevant_chunk_ids": sorted(relevant_ids),
        "partially_relevant_chunk_ids": sorted(partial_ids),
        "retrieved_chunk_ids": retrieved_ids,
        "retrieved_count": len(retrieved_ids),
        "metrics": metrics,
        "warnings": warnings,
    }
