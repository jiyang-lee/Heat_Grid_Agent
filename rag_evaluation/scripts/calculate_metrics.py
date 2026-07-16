"""Aggregate HeatGrid retrieval case metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from evaluation_utils import mean, read_jsonl, write_json


METRIC_KEYS = (
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "precision_at_1",
    "precision_at_3",
    "precision_at_5",
    "mrr",
    "ndcg_at_5",
    "hit_rate_at_1",
    "hit_rate_at_3",
    "hit_rate_at_5",
)


def _macro_average(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    included = [row for row in rows if not row.get("excluded_from_macro_metrics")]
    for key in METRIC_KEYS:
        values = [
            float(row["metrics"][key])
            for row in included
            if row.get("metrics", {}).get(key) is not None
        ]
        result[key] = mean(values)
    return result


def _breakdown(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(field, "unknown"))].append(row)
    return {
        name: {
            "case_count": len(group),
            "evaluated_case_count": sum(1 for row in group if not row.get("excluded_from_macro_metrics")),
            "macro_average_metrics": _macro_average(group),
        }
        for name, group in sorted(groups.items())
    }


def build_summary(
    case_results: list[dict[str, Any]],
    dataset_path: str,
    dataset_status: str,
    result_level: str,
    official_benchmark: bool,
) -> dict[str, Any]:
    excluded_unanswerable = sum(1 for row in case_results if row.get("exclusion_reason") == "answerable_false")
    warning_count = sum(1 for row in case_results if row.get("warnings"))
    evaluated_count = sum(1 for row in case_results if not row.get("excluded_from_macro_metrics"))
    return {
        "dataset_path": dataset_path,
        "dataset_status": dataset_status,
        "result_level": result_level,
        "official_benchmark": official_benchmark,
        "case_count": len(case_results),
        "evaluated_case_count": evaluated_count,
        "excluded_unanswerable_count": excluded_unanswerable,
        "warning_case_count": warning_count,
        "macro_average_metrics": _macro_average(case_results),
        "category_breakdown": _breakdown(case_results, "category"),
        "difficulty_breakdown": _breakdown(case_results, "difficulty"),
        "query_intent_breakdown": _breakdown(case_results, "query_intent"),
    }


def summarize_results_file(
    results_path: str,
    summary_path: str,
    dataset_path: str,
    dataset_status: str,
    result_level: str,
    official_benchmark: bool,
) -> dict[str, Any]:
    rows = read_jsonl(results_path)
    summary = build_summary(rows, dataset_path, dataset_status, result_level, official_benchmark)
    write_json(summary_path, summary)
    return summary
