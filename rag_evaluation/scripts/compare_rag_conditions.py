"""Compare with-RAG and no-RAG LLM Judge outputs by case."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


SCORE_FIELDS = (
    "faithfulness",
    "operational_usefulness",
    "citation_accuracy_semantic",
    "answer_relevance",
)
EFFECTIVENESS_FIELDS = ("operational_usefulness", "answer_relevance")
GROUNDING_FIELDS = ("faithfulness", "citation_accuracy_semantic")


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def compare_conditions(
    with_rag_rows: list[dict[str, Any]],
    no_rag_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with_by_case = {row["case_id"]: row for row in with_rag_rows}
    no_by_case = {row["case_id"]: row for row in no_rag_rows}
    shared = sorted(set(with_by_case) & set(no_by_case))
    records: list[dict[str, Any]] = []
    for case_id in shared:
        with_row = with_by_case[case_id]
        no_row = no_by_case[case_id]
        deltas = {
            field: with_row.get(field) - no_row.get(field)
            for field in SCORE_FIELDS
            if isinstance(with_row.get(field), (int, float))
            and isinstance(no_row.get(field), (int, float))
        }
        effectiveness_delta = sum(deltas.get(field, 0) for field in EFFECTIVENESS_FIELDS)
        grounding_delta = sum(deltas.get(field, 0) for field in GROUNDING_FIELDS)
        records.append(
            {
                "case_id": case_id,
                "with_rag_recommendation": with_row.get("overall_recommendation"),
                "no_rag_recommendation": no_row.get("overall_recommendation"),
                "score_deltas": deltas,
                "effectiveness_delta": effectiveness_delta,
                "grounding_delta": grounding_delta,
                "rag_effectiveness_improved": effectiveness_delta > 0,
                "rag_effectiveness_degraded": effectiveness_delta < 0,
                "abstention_confounded_grounding": True,
                "manual_review_required": (
                    with_row.get("overall_recommendation") != no_row.get("overall_recommendation")
                    or with_row.get("hallucination_severity") != no_row.get("hallucination_severity")
                ),
            }
        )

    average_deltas = {
        field: statistics.fmean(
            record["score_deltas"][field]
            for record in records
            if field in record["score_deltas"]
        )
        if any(field in record["score_deltas"] for record in records)
        else None
        for field in SCORE_FIELDS
    }
    summary = {
        "shared_case_count": len(shared),
        "with_rag_only_case_ids": sorted(set(with_by_case) - set(no_by_case)),
        "no_rag_only_case_ids": sorted(set(no_by_case) - set(with_by_case)),
        "average_score_deltas_with_minus_without": average_deltas,
        "rag_effectiveness_improved_case_count": sum(
            1 for record in records if record["rag_effectiveness_improved"]
        ),
        "rag_effectiveness_degraded_case_count": sum(
            1 for record in records if record["rag_effectiveness_degraded"]
        ),
        "grounding_comparison_note": (
            "no-RAG answers mostly abstain, so faithfulness and citation scores are "
            "safety indicators rather than direct RAG-effectiveness measures"
        ),
        "manual_review_required_count": sum(
            1 for record in records if record["manual_review_required"]
        ),
        "comparison_status": "complete" if len(shared) == len(with_by_case) == len(no_by_case) else "partial",
    }
    return records, summary


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare HeatGrid with-RAG and no-RAG Judge results")
    parser.add_argument("--with-rag", default="rag_evaluation/llm_judge/llm_judge_results.jsonl")
    parser.add_argument("--no-rag", default="rag_evaluation/llm_judge/llm_judge_no_rag_results.jsonl")
    parser.add_argument("--results", default="rag_evaluation/results/rag_condition_comparison.jsonl")
    parser.add_argument("--summary", default="rag_evaluation/results/rag_condition_comparison_summary.json")
    args = parser.parse_args()
    rows, summary = compare_conditions(load_jsonl(args.with_rag), load_jsonl(args.no_rag))
    write_jsonl(args.results, rows)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
