"""Combine Retrieval, automatic evaluation, and LLM Judge results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evaluation_utils import read_jsonl, write_json, write_jsonl
from failure_attribution import classify_case, summarize_attributions


REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATASET = REPO_ROOT / "rag_evaluation" / "answer_evaluation" / "answer_eval.draft.jsonl"
DEFAULT_AUTOMATIC = REPO_ROOT / "rag_evaluation" / "automatic_evaluation" / "automatic_answer_eval_results.jsonl"
DEFAULT_JUDGE = REPO_ROOT / "rag_evaluation" / "llm_judge" / "llm_judge_results.jsonl"
DEFAULT_RESULTS = REPO_ROOT / "rag_evaluation" / "results" / "failure_attribution_results.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "rag_evaluation" / "results" / "failure_attribution_summary.json"


def _index(rows: list[dict], source: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "")
        if not case_id:
            raise ValueError(f"missing case_id in {source}")
        if case_id in indexed:
            raise ValueError(f"duplicate case_id in {source}: {case_id}")
        indexed[case_id] = row
    return indexed


def run(args: argparse.Namespace) -> dict:
    dataset_rows = read_jsonl(args.dataset)
    automatic_by_case = _index(read_jsonl(args.automatic), "automatic evaluation")
    judge_by_case = _index(read_jsonl(args.judge), "LLM Judge")

    records: list[dict] = []
    missing: dict[str, list[str]] = {"automatic": [], "judge": []}
    for dataset_row in dataset_rows:
        case_id = str(dataset_row.get("case_id") or "")
        automatic = automatic_by_case.get(case_id)
        judge = judge_by_case.get(case_id)
        if automatic is None:
            missing["automatic"].append(case_id)
        if judge is None:
            missing["judge"].append(case_id)
        if automatic is None or judge is None:
            continue
        records.append(classify_case(dataset_row, automatic, judge))

    write_jsonl(args.results, records)
    summary = summarize_attributions(records)
    summary.update(
        {
            "dataset_status": "draft",
            "result_level": "reference",
            "official_benchmark": False,
            "input_dataset_path": str(args.dataset),
            "input_automatic_path": str(args.automatic),
            "input_judge_path": str(args.judge),
            "output_results_path": str(args.results),
            "missing_case_ids": missing,
            "classification_policy_version": "failure-attribution-v1",
        }
    )
    write_json(args.summary, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Attribute HeatGrid RAG failures")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--automatic", default=str(DEFAULT_AUTOMATIC))
    parser.add_argument("--judge", default=str(DEFAULT_JUDGE))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
