"""Run HeatGrid draft/reference retrieval evaluation.

This entry point does not call the production RagSearcher. It accepts mock
retrieved chunks or uses a label echo mock for pipeline validation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_metrics import build_summary
from evaluate_case import evaluate_case
from evaluation_utils import read_jsonl, safe_list, write_json, write_jsonl


REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_APPROVED = REPO_ROOT / "rag_evaluation" / "datasets" / "retrieval_eval.approved.jsonl"
DEFAULT_REVIEW = REPO_ROOT / "rag_evaluation" / "review" / "retrieval_eval.review.jsonl"
DEFAULT_RESULTS = REPO_ROOT / "rag_evaluation" / "results" / "retrieval_results.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "rag_evaluation" / "results" / "retrieval_summary.json"


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Load the simple key/value config used by this evaluation module.

    The project does not require PyYAML for this draft pipeline.
    """
    if not path.exists():
        return {}
    config: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            config.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if not value:
                config[key] = []
            elif value.lower() in {"true", "false"}:
                config[key] = value.lower() == "true"
            elif value.startswith("[") and value.endswith("]"):
                items = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
                config[key] = items
            else:
                config[key] = value.strip("'\"")
    return config


def choose_dataset(explicit_path: str | None) -> tuple[Path, str, str, bool]:
    if explicit_path:
        path = Path(explicit_path)
        status = "approved" if "approved" in path.name else "draft"
    elif DEFAULT_APPROVED.exists():
        path = DEFAULT_APPROVED
        status = "approved"
    else:
        path = DEFAULT_REVIEW
        status = "draft"
    return path, status, "official" if status == "approved" else "reference", status == "approved"


def load_mock_retrievals(path: str | None) -> dict[str, list[Any]]:
    if not path:
        return {}
    rows = read_jsonl(path)
    mapping: dict[str, list[Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not case_id:
            raise ValueError(f"Mock retrieval row is missing case_id: {row!r}")
        retrieved = row.get("retrieved_chunk_ids", row.get("retrieved_chunks", []))
        mapping[str(case_id)] = safe_list(retrieved)
    return mapping


def label_echo_mock(case: dict[str, Any]) -> list[str]:
    """Deterministic mock used only to validate metric plumbing."""
    return [
        *[str(value) for value in safe_list(case.get("relevant_chunk_ids"))],
        *[str(value) for value in safe_list(case.get("partially_relevant_chunk_ids"))],
        *[str(value) for value in safe_list(case.get("irrelevant_but_confusable_chunk_ids"))],
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = load_simple_yaml(Path(args.config)) if args.config else {}
    dataset_path, dataset_status, result_level, official_benchmark = choose_dataset(
        args.dataset or config.get("dataset_path")
    )
    results_path = Path(args.results or config.get("results_path") or DEFAULT_RESULTS)
    summary_path = Path(args.summary or config.get("summary_path") or DEFAULT_SUMMARY)
    cases = read_jsonl(dataset_path)
    mock_retrievals = load_mock_retrievals(args.mock_retrieval_file or config.get("mock_retrieval_path"))

    case_results: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id"))
        retrieved = mock_retrievals.get(case_id)
        if retrieved is None:
            retrieved = label_echo_mock(case)
        result = evaluate_case(case, retrieved)
        result["retrieval_source"] = "mock_file" if case_id in mock_retrievals else "label_echo_mock"
        case_results.append(result)

    write_jsonl(results_path, case_results)
    summary = build_summary(
        case_results,
        str(dataset_path),
        dataset_status,
        result_level,
        official_benchmark,
    )
    write_json(summary_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HeatGrid retrieval reference evaluation.")
    parser.add_argument("--config", default=str(REPO_ROOT / "rag_evaluation" / "configs" / "retrieval_eval_config.yaml"))
    parser.add_argument("--dataset", help="Explicit dataset JSONL path. Defaults to approved, then review.")
    parser.add_argument("--mock-retrieval-file", help="JSONL with case_id and retrieved_chunk_ids.")
    parser.add_argument("--results", help="Output retrieval_results.jsonl path.")
    parser.add_argument("--summary", help="Output retrieval_summary.json path.")
    args = parser.parse_args()
    summary = run(args)
    print(f"dataset_status={summary['dataset_status']}")
    print(f"result_level={summary['result_level']}")
    print(f"official_benchmark={summary['official_benchmark']}")
    print(f"evaluated_case_count={summary['evaluated_case_count']}")


if __name__ == "__main__":
    main()
