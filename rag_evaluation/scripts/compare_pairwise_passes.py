"""Merge two position-swapped pairwise RAG Judge passes."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from llm_judge_utils import load_jsonl, write_json, write_jsonl
from run_pairwise_rag_judge import DIMENSIONS


PASS_1_PATH = Path("rag_evaluation/results/pairwise_rag_judge_results.jsonl")
PASS_2_PATH = Path("rag_evaluation/results/pairwise_rag_judge_results_swap.jsonl")
RESULTS_PATH = Path("rag_evaluation/results/pairwise_rag_judge_consensus.jsonl")
SUMMARY_PATH = Path("rag_evaluation/results/pairwise_rag_judge_consensus_summary.json")


def _consensus_winner(first: str, second: str) -> str:
    if first == second:
        return first
    if first == "tie":
        return second
    if second == "tie":
        return first
    return "contested"


def _group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(rows),
        "consensus_winner_counts": dict(Counter(row["consensus_winner"] for row in rows)),
        "with_rag_expected_point_coverage_average": statistics.fmean(
            row["average_scores"]["with_rag"]["expected_point_coverage"] for row in rows
        ),
        "no_rag_expected_point_coverage_average": statistics.fmean(
            row["average_scores"]["no_rag"]["expected_point_coverage"] for row in rows
        ),
        "with_rag_correctness_average": statistics.fmean(
            row["average_scores"]["with_rag"]["correctness"] for row in rows
        ),
        "with_rag_actionability_average": statistics.fmean(
            row["average_scores"]["with_rag"]["actionability"] for row in rows
        ),
    }


def merge_passes(
    first_rows: list[dict[str, Any]],
    second_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    first_by_case = {row["case_id"]: row for row in first_rows}
    second_by_case = {row["case_id"]: row for row in second_rows}
    shared = sorted(set(first_by_case) & set(second_by_case))
    records: list[dict[str, Any]] = []
    for case_id in shared:
        first = first_by_case[case_id]
        second = second_by_case[case_id]
        scores: dict[str, dict[str, float]] = {}
        position_deltas: dict[str, dict[str, float]] = {}
        for condition in ("with_rag", "no_rag"):
            scores[condition] = {}
            position_deltas[condition] = {}
            for dimension in (*DIMENSIONS, "expected_point_coverage"):
                values = [first[condition][dimension], second[condition][dimension]]
                scores[condition][dimension] = statistics.fmean(values)
                position_deltas[condition][dimension] = abs(values[0] - values[1])
        winner = _consensus_winner(first["winner"], second["winner"])
        records.append(
            {
                "case_id": case_id,
                "pass_winners": [first["winner"], second["winner"]],
                "consensus_winner": winner,
                "winner_stable": first["winner"] == second["winner"],
                "position_sensitive": first["winner"] != second["winner"],
                "average_scores": scores,
                "absolute_position_score_deltas": position_deltas,
                "retrieval_hit_at_5": first["metadata"]["retrieval_hit_at_5"],
                "category": first["metadata"].get("category"),
                "difficulty": first["metadata"].get("difficulty"),
                "review_priority": (
                    "HIGH"
                    if winner == "contested"
                    else max(
                        (first["review_priority"], second["review_priority"]),
                        key={"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get,
                    )
                ),
                "reasons": [first["reason"], second["reason"]],
            }
        )

    dimension_summary: dict[str, Any] = {}
    for dimension in (*DIMENSIONS, "expected_point_coverage"):
        with_average = statistics.fmean(
            row["average_scores"]["with_rag"][dimension] for row in records
        ) if records else None
        no_average = statistics.fmean(
            row["average_scores"]["no_rag"][dimension] for row in records
        ) if records else None
        mean_position_delta = statistics.fmean(
            statistics.fmean(
                row["absolute_position_score_deltas"][condition][dimension]
                for condition in ("with_rag", "no_rag")
            )
            for row in records
        ) if records else None
        dimension_summary[dimension] = {
            "with_rag_average": with_average,
            "no_rag_average": no_average,
            "delta_with_minus_without": (
                with_average - no_average if with_average is not None and no_average is not None else None
            ),
            "mean_absolute_position_delta": mean_position_delta,
        }

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for field in ("retrieval_hit_at_5", "category", "difficulty"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in records:
            groups[str(row[field])].append(row)
        grouped[field] = groups
    summary = {
        "status": "complete" if len(shared) == len(first_by_case) == len(second_by_case) else "partial",
        "shared_case_count": len(shared),
        "consensus_winner_counts": dict(Counter(row["consensus_winner"] for row in records)),
        "stable_winner_count": sum(row["winner_stable"] for row in records),
        "position_sensitive_count": sum(row["position_sensitive"] for row in records),
        "position_sensitive_case_ids": [row["case_id"] for row in records if row["position_sensitive"]],
        "dimension_averages": dimension_summary,
        "review_priority_counts": dict(Counter(row["review_priority"] for row in records)),
        "breakdown_by_retrieval_hit": {
            key: _group_summary(rows)
            for key, rows in sorted(grouped["retrieval_hit_at_5"].items())
        },
        "breakdown_by_category": {
            key: _group_summary(rows)
            for key, rows in sorted(grouped["category"].items())
        },
        "breakdown_by_difficulty": {
            key: _group_summary(rows)
            for key, rows in sorted(grouped["difficulty"].items())
        },
        "methodology_notes": [
            "Both passes used the same Judge and rubric with A/B positions reversed.",
            "Opposite non-tie winners are marked contested instead of being forced to a winner.",
            "Draft/Reference labels still require human approval before official use.",
        ],
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-1", default=str(PASS_1_PATH))
    parser.add_argument("--pass-2", default=str(PASS_2_PATH))
    parser.add_argument("--results", default=str(RESULTS_PATH))
    parser.add_argument("--summary", default=str(SUMMARY_PATH))
    args = parser.parse_args()
    records, summary = merge_passes(load_jsonl(args.pass_1), load_jsonl(args.pass_2))
    write_jsonl(args.results, records)
    write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
