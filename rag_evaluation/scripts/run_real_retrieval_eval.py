"""Run real production RagSearcher retrieval and reference evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_metrics import build_summary
from baseline_gate import evaluate_baseline_gate, read_json
from evaluate_case import evaluate_case
from evaluation_utils import read_jsonl, write_json, write_jsonl
from retrieval_adapter import RagSearcherAdapter


REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_REVIEW = REPO_ROOT / "rag_evaluation" / "review" / "retrieval_eval.review.jsonl"
DEFAULT_APPROVED = REPO_ROOT / "rag_evaluation" / "datasets" / "retrieval_eval.approved.jsonl"
DEFAULT_RAW = REPO_ROOT / "rag_evaluation" / "results" / "raw_retrieval_outputs.jsonl"
DEFAULT_RESULTS = REPO_ROOT / "rag_evaluation" / "results" / "real_retrieval_results.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "rag_evaluation" / "results" / "real_retrieval_summary.json"


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def choose_dataset(explicit: str | None) -> tuple[Path, str, str, bool]:
    if explicit:
        path = Path(explicit)
        status = "approved" if "approved" in path.name else "draft"
    elif DEFAULT_APPROVED.exists():
        path = DEFAULT_APPROVED
        status = "approved"
    else:
        path = DEFAULT_REVIEW
        status = "draft"
    return path, status, "official" if status == "approved" else "reference", status == "approved"


def backend_counts(raw_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in raw_rows:
        backend = str(row.get("actual_backend") or "error")
        counts[backend] = counts.get(backend, 0) + 1
    return counts


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path, dataset_status, result_level, official_benchmark = choose_dataset(args.dataset)
    cases = read_jsonl(dataset_path)
    adapter = RagSearcherAdapter(requested_backend=args.backend, top_k=args.top_k)

    raw_rows: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []
    for case in cases:
        raw = adapter.search_case(case)
        raw_rows.append(raw)
        result = evaluate_case(case, raw["normalized_retrieved_chunk_ids"])
        result.update(
            {
                "requested_backend": raw["requested_backend"],
                "actual_backend": raw["actual_backend"],
                "retrieval_latency_ms": raw["retrieval_latency_ms"],
                "retrieved_result_count": len((raw.get("raw_results") or {}).get("chunks") or []),
                "valid_chunk_id_count": len(raw["normalized_retrieved_chunk_ids"]),
                "error": raw["error"],
                "warnings": [*result.get("warnings", []), *raw.get("warnings", [])],
            }
        )
        if raw["error"]:
            result["excluded_from_macro_metrics"] = True
            result["exclusion_reason"] = "retrieval_error"
            for metric_name in result["metrics"]:
                result["metrics"][metric_name] = None
        case_results.append(result)

    write_jsonl(args.raw_output, raw_rows)
    write_jsonl(args.results, case_results)

    summary = build_summary(
        case_results,
        str(dataset_path),
        dataset_status,
        result_level,
        official_benchmark,
    )
    latencies = [float(row["retrieval_latency_ms"]) for row in raw_rows if row.get("error") is None]
    summary.update(
        {
            "requested_backend": args.backend,
            "backend_usage_counts": backend_counts(raw_rows),
            "failed_case_count": sum(1 for row in raw_rows if row.get("error")),
            "average_retrieval_latency_ms": mean(latencies) if latencies else None,
            "p50_retrieval_latency_ms": median(latencies) if latencies else None,
            "p95_retrieval_latency_ms": percentile(latencies, 0.95),
        }
    )
    write_json(args.summary, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real HeatGrid RAG retrieval reference evaluation.")
    parser.add_argument("--backend", choices=["auto", "pgvector", "jsonl"], default="jsonl")
    parser.add_argument("--dataset")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--raw-output", default=str(DEFAULT_RAW))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--baseline")
    parser.add_argument("--baseline-gate-output")
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    print(f"dataset_status={summary['dataset_status']}")
    print(f"result_level={summary['result_level']}")
    print(f"official_benchmark={summary['official_benchmark']}")
    print(f"requested_backend={summary['requested_backend']}")
    print(f"backend_usage_counts={summary['backend_usage_counts']}")
    print(f"evaluated_case_count={summary['evaluated_case_count']}")
    print(f"failed_case_count={summary['failed_case_count']}")
    if args.baseline:
        gate = evaluate_baseline_gate(summary, read_json(args.baseline))
        gate_output = args.baseline_gate_output or str(
            Path(args.summary).with_name(f"{Path(args.summary).stem}_baseline_gate.json")
        )
        write_json(gate_output, gate)
        print(f"baseline_gate_status={gate['status']}")
        print(f"baseline_gate_output={gate_output}")
        if args.fail_on_regression and gate["status"] != "passed":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
