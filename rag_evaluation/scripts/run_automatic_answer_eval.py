"""Run rule-based automatic answer evaluation for HeatGrid RAG outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from automatic_answer_eval_utils import evaluate_case, load_jsonl, summarize_results, write_jsonl


DEFAULT_GENERATION_PATH = "rag_evaluation/results/answer_generation_all.jsonl"
DEFAULT_DATASET_PATH = "rag_evaluation/answer_evaluation/answer_eval.draft.jsonl"
DEFAULT_RESULTS_PATH = "rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl"
DEFAULT_SUMMARY_PATH = "rag_evaluation/automatic_evaluation/automatic_answer_eval_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rule-based automatic answer evaluation")
    parser.add_argument("--generation-path", default=DEFAULT_GENERATION_PATH)
    parser.add_argument("--dataset-path", default=DEFAULT_DATASET_PATH)
    parser.add_argument("--results-path", default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--summary-path", default=DEFAULT_SUMMARY_PATH)
    args = parser.parse_args()

    generated_rows = load_jsonl(args.generation_path)
    dataset_rows = load_jsonl(args.dataset_path)
    dataset_by_case = {row["case_id"]: row for row in dataset_rows}

    records = []
    missing_cases = []
    for generated in generated_rows:
        case_id = generated.get("case_id")
        dataset_row = dataset_by_case.get(case_id)
        if not dataset_row:
            missing_cases.append(case_id)
            continue
        records.append(evaluate_case(generated, dataset_row))

    summary = summarize_results(records)
    summary.update({
        "input_generation_path": args.generation_path,
        "input_dataset_path": args.dataset_path,
        "output_results_path": args.results_path,
        "missing_case_ids": missing_cases,
        "evaluated_case_ids": [record["case_id"] for record in records],
        "llm_judge_used": False,
        "human_review_used": False,
    })

    write_jsonl(args.results_path, records)
    summary_target = Path(args.summary_path)
    if not summary_target.is_absolute():
        summary_target = Path.cwd() / summary_target
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
