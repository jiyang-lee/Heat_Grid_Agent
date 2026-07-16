"""Compare a retrieval evaluation summary with a versioned baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_GATED_METRICS = (
    "recall_at_5",
    "hit_rate_at_5",
    "mrr",
    "ndcg_at_5",
)


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_baseline_gate(
    current_summary: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    current_metrics = current_summary.get("macro_average_metrics") or {}
    baseline_retrieval = baseline.get("retrieval") or {}
    baseline_metrics = baseline_retrieval.get("macro_average_metrics") or {}
    comparisons: list[dict[str, Any]] = []
    failed_metrics: list[str] = []
    for metric in DEFAULT_GATED_METRICS:
        current_value = current_metrics.get(metric)
        minimum_value = baseline_metrics.get(metric)
        passed = (
            isinstance(current_value, (int, float))
            and isinstance(minimum_value, (int, float))
            and current_value >= minimum_value
        )
        comparisons.append(
            {
                "metric": metric,
                "current": current_value,
                "minimum": minimum_value,
                "passed": passed,
            }
        )
        if not passed:
            failed_metrics.append(metric)

    current_failures = int(current_summary.get("failed_case_count") or 0)
    maximum_failures = int(baseline_retrieval.get("failed_case_count") or 0)
    failure_count_passed = current_failures <= maximum_failures
    if not failure_count_passed:
        failed_metrics.append("failed_case_count")

    return {
        "status": "passed" if not failed_metrics else "regression",
        "baseline_id": baseline.get("baseline_id"),
        "comparisons": comparisons,
        "failed_case_count": {
            "current": current_failures,
            "maximum": maximum_failures,
            "passed": failure_count_passed,
        },
        "failed_metrics": failed_metrics,
    }
