"""Run a blinded, direct with-RAG versus no-RAG answer comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_judge_utils import (
    build_model_input,
    load_dotenv,
    load_jsonl,
    parse_model_json,
    resolve_repo_path,
    write_json,
    write_jsonl,
)
from run_llm_judge import call_openai_responses


PROMPT_PATH = Path("rag_evaluation/llm_judge/pairwise_rag_judge_prompt.md")
WITH_RAG_PATH = Path("rag_evaluation/results/answer_generation_all.jsonl")
NO_RAG_PATH = Path("rag_evaluation/results/answer_generation_no_rag.jsonl")
DATASET_PATH = Path("rag_evaluation/answer_evaluation/answer_eval.draft.jsonl")
RETRIEVAL_PATH = Path("rag_evaluation/results/real_retrieval_results.jsonl")
RESULTS_PATH = Path("rag_evaluation/results/pairwise_rag_judge_results.jsonl")
SUMMARY_PATH = Path("rag_evaluation/results/pairwise_rag_judge_summary.json")

DIMENSIONS = (
    "correctness",
    "completeness",
    "actionability",
    "evidence_grounding",
    "calibration",
)
RISKS = {"NONE", "LOW", "MEDIUM", "HIGH"}
FAILURE_TAGS = {
    "missed_expected_point",
    "unsupported_claim",
    "over_abstention",
    "unsafe_action",
    "citation_mismatch",
    "none",
}


def _candidate_order(case_id: str) -> tuple[str, str]:
    """Alternate answer position deterministically to reduce position bias."""

    first_byte = hashlib.sha256(case_id.encode("utf-8")).digest()[0]
    return ("with_rag", "no_rag") if first_byte % 2 == 0 else ("no_rag", "with_rag")


def _answer_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": row.get("generated_answer"),
        "cited_chunk_ids": row.get("cited_chunk_ids") or [],
    }


def build_pairwise_cases(
    with_rows: list[dict[str, Any]],
    no_rows: list[dict[str, Any]],
    dataset_rows: list[dict[str, Any]],
    retrieval_rows: list[dict[str, Any]],
    *,
    swap_positions: bool = False,
) -> list[dict[str, Any]]:
    with_by_case = {row["case_id"]: row for row in with_rows}
    no_by_case = {row["case_id"]: row for row in no_rows}
    dataset_by_case = {row["case_id"]: row for row in dataset_rows}
    retrieval_by_case = {row["case_id"]: row for row in retrieval_rows}
    shared = sorted(set(with_by_case) & set(no_by_case) & set(dataset_by_case))
    cases: list[dict[str, Any]] = []
    for case_id in shared:
        dataset = dataset_by_case[case_id]
        condition_a, condition_b = _candidate_order(case_id)
        if swap_positions:
            condition_a, condition_b = condition_b, condition_a
        answers = {"with_rag": with_by_case[case_id], "no_rag": no_by_case[case_id]}
        contexts = dataset.get("retrieved_contexts") or []
        payload = {
            "case_id": case_id,
            "question": dataset.get("query"),
            "answerable": dataset.get("answerable"),
            "expected_answer_points": dataset.get("expected_answer_points") or [],
            "forbidden_claims": dataset.get("forbidden_claims") or [],
            "reference_evidence": [
                {"chunk_id": row.get("chunk_id"), "text": row.get("text")}
                for row in contexts
            ],
            "candidate_a": _answer_payload(answers[condition_a]),
            "candidate_b": _answer_payload(answers[condition_b]),
        }
        retrieval = retrieval_by_case.get(case_id, {})
        cases.append(
            {
                "case_id": case_id,
                "candidate_mapping": {"A": condition_a, "B": condition_b},
                "payload": payload,
                "metadata": {
                    "category": dataset.get("category"),
                    "query_intent": dataset.get("query_intent"),
                    "query_type": dataset.get("query_type"),
                    "difficulty": dataset.get("difficulty"),
                    "answerable": dataset.get("answerable"),
                    "retrieval_hit_at_5": ((retrieval.get("metrics") or {}).get("hit_rate_at_5") or 0) > 0,
                    "retrieval_mrr": (retrieval.get("metrics") or {}).get("mrr"),
                    "retrieval_ndcg_at_5": (retrieval.get("metrics") or {}).get("ndcg_at_5"),
                },
            }
        )
    return cases


def validate_pairwise_result(parsed: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("candidate_a", "candidate_b"):
        candidate = parsed.get(key)
        if not isinstance(candidate, dict):
            errors.append(f"{key}:not_object")
            continue
        for dimension in DIMENSIONS:
            score = candidate.get(dimension)
            if not isinstance(score, int) or not 1 <= score <= 5:
                errors.append(f"{key}.{dimension}:invalid_score")
        coverage = candidate.get("expected_point_coverage")
        if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 1:
            errors.append(f"{key}.expected_point_coverage:invalid")
        if candidate.get("unsupported_claim_risk") not in RISKS:
            errors.append(f"{key}.unsupported_claim_risk:invalid")
        tags = candidate.get("failure_tags")
        if not isinstance(tags, list) or not tags or any(tag not in FAILURE_TAGS for tag in tags):
            errors.append(f"{key}.failure_tags:invalid")
    if parsed.get("overall_winner") not in {"A", "B", "TIE"}:
        errors.append("overall_winner:invalid")
    if parsed.get("winner_strength") not in {"CLEAR", "SLIGHT", "TIE"}:
        errors.append("winner_strength:invalid")
    if parsed.get("review_priority") not in {"HIGH", "MEDIUM", "LOW"}:
        errors.append("review_priority:invalid")
    if not isinstance(parsed.get("reason"), str) or not parsed.get("reason", "").strip():
        errors.append("reason:invalid")
    return errors


def normalize_result(
    case: dict[str, Any],
    parsed: dict[str, Any],
    model: str,
    usage: dict[str, Any],
) -> dict[str, Any]:
    mapping = case["candidate_mapping"]
    by_condition = {
        mapping["A"]: parsed["candidate_a"],
        mapping["B"]: parsed["candidate_b"],
    }
    raw_winner = parsed["overall_winner"]
    winner = "tie" if raw_winner == "TIE" else mapping[raw_winner]
    retrieval_hit = case["metadata"]["retrieval_hit_at_5"]
    if winner == "with_rag":
        retrieval_effect = "beneficial"
    elif winner == "no_rag":
        retrieval_effect = "harmful"
    else:
        retrieval_effect = "neutral"

    if winner == "no_rag" and not retrieval_hit:
        failure_signal = "retrieval_failure"
    elif winner == "no_rag" and retrieval_hit:
        failure_signal = "generation_or_interpretation_failure"
    elif winner == "with_rag" and not retrieval_hit:
        failure_signal = "retrieval_miss_but_answer_resilient"
    else:
        failure_signal = "none"

    return {
        "case_id": case["case_id"],
        "winner": winner,
        "winner_strength": parsed["winner_strength"].lower(),
        "retrieval_effect": retrieval_effect,
        "failure_signal": failure_signal,
        "with_rag": by_condition["with_rag"],
        "no_rag": by_condition["no_rag"],
        "review_priority": parsed["review_priority"],
        "reason": parsed["reason"],
        "metadata": case["metadata"],
        "judge_metadata": {
            "model": model,
            "prompt_version": "pairwise-rag-judge-v1.0-draft",
            "candidate_mapping": mapping,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "usage": usage,
        },
    }


def _group_breakdown(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record["metadata"].get(field))].append(record)
    return {
        key: {
            "case_count": len(rows),
            "winner_counts": dict(Counter(row["winner"] for row in rows)),
            "with_rag_win_rate": sum(row["winner"] == "with_rag" for row in rows) / len(rows),
        }
        for key, rows in sorted(groups.items())
    }


def build_summary(
    records: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    model: str,
    api_call_count: int,
) -> dict[str, Any]:
    dimensions: dict[str, Any] = {}
    for dimension in (*DIMENSIONS, "expected_point_coverage"):
        with_average = statistics.fmean(row["with_rag"][dimension] for row in records) if records else None
        no_average = statistics.fmean(row["no_rag"][dimension] for row in records) if records else None
        dimensions[dimension] = {
            "with_rag_average": with_average,
            "no_rag_average": no_average,
            "delta_with_minus_without": (
                with_average - no_average if with_average is not None and no_average is not None else None
            ),
        }
    total_usage = {
        key: sum((row["judge_metadata"]["usage"].get(key) or 0) for row in records)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    return {
        "status": "complete" if records and not failures else "partial",
        "model": model,
        "evaluated_case_count": len(records),
        "api_call_count": api_call_count,
        "failure_count": len(failures),
        "failures": failures,
        "winner_counts": dict(Counter(row["winner"] for row in records)),
        "winner_strength_counts": dict(Counter(row["winner_strength"] for row in records)),
        "retrieval_effect_counts": dict(Counter(row["retrieval_effect"] for row in records)),
        "failure_signal_counts": dict(Counter(row["failure_signal"] for row in records)),
        "review_priority_counts": dict(Counter(row["review_priority"] for row in records)),
        "dimension_averages": dimensions,
        "unsupported_claim_risk_counts": {
            condition: dict(Counter(row[condition]["unsupported_claim_risk"] for row in records))
            for condition in ("with_rag", "no_rag")
        },
        "failure_tag_counts": {
            condition: dict(
                Counter(tag for row in records for tag in row[condition]["failure_tags"])
            )
            for condition in ("with_rag", "no_rag")
        },
        "breakdown_by_retrieval_hit": _group_breakdown(records, "retrieval_hit_at_5"),
        "breakdown_by_category": _group_breakdown(records, "category"),
        "breakdown_by_difficulty": _group_breakdown(records, "difficulty"),
        "breakdown_by_query_intent": _group_breakdown(records, "query_intent"),
        "usage": total_usage,
        "methodology_notes": [
            "Candidate identity was hidden from the Judge and A/B position was alternated by case hash.",
            "The dataset is Draft/Reference and results are not an official benchmark.",
            "Failure signals are diagnostic heuristics and require human confirmation.",
        ],
    }


def run(
    *,
    model: str,
    overwrite: bool,
    max_retries: int,
    timeout_seconds: int,
    temperature: float,
    max_cases: int | None,
    swap_positions: bool,
    results_output: str | Path,
    summary_output: str | Path,
) -> dict[str, Any]:
    results_path = resolve_repo_path(results_output)
    summary_path = resolve_repo_path(summary_output)
    if (results_path.exists() or summary_path.exists()) and not overwrite:
        raise SystemExit("Pairwise result files exist; pass --overwrite to replace them.")
    prompt = resolve_repo_path(PROMPT_PATH).read_text(encoding="utf-8")
    cases = build_pairwise_cases(
        load_jsonl(WITH_RAG_PATH),
        load_jsonl(NO_RAG_PATH),
        load_jsonl(DATASET_PATH),
        load_jsonl(RETRIEVAL_PATH),
        swap_positions=swap_positions,
    )
    if max_cases is not None:
        cases = cases[:max_cases]

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    api_call_count = 0
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] pairwise judging {case['case_id']}", file=sys.stderr)
        input_text = build_model_input(prompt, case["payload"])
        parsed: dict[str, Any] | None = None
        usage: dict[str, Any] = {}
        last_error: str | None = None
        for attempt in range(max_retries + 1):
            if attempt:
                time.sleep(1 + attempt)
            try:
                api_call_count += 1
                raw_text, usage = call_openai_responses(input_text, model, temperature, timeout_seconds)
                parsed, parse_error = parse_model_json(raw_text)
                if parse_error:
                    raise RuntimeError(parse_error)
                errors = validate_pairwise_result(parsed or {})
                if errors:
                    raise RuntimeError("schema:" + ",".join(errors))
                break
            except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}:{exc}"
                parsed = None
        if parsed is None:
            failures.append({"case_id": case["case_id"], "error": last_error})
            continue
        records.append(normalize_result(case, parsed, model, usage))

    summary = build_summary(records, failures, model, api_call_count)
    summary["swap_positions"] = swap_positions
    write_jsonl(results_output, records)
    write_json(summary_output, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--swap-positions", action="store_true")
    parser.add_argument("--results-path", default=str(RESULTS_PATH))
    parser.add_argument("--summary-path", default=str(SUMMARY_PATH))
    args = parser.parse_args()
    load_dotenv()
    if args.plan_only:
        case_count = len(
            build_pairwise_cases(
                load_jsonl(WITH_RAG_PATH),
                load_jsonl(NO_RAG_PATH),
                load_jsonl(DATASET_PATH),
                load_jsonl(RETRIEVAL_PATH),
                swap_positions=args.swap_positions,
            )
        )
        summary = {"planned_case_count": case_count, "model": args.model, "api_execution_enabled": False}
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is not configured")
        summary = run(
            model=args.model,
            overwrite=args.overwrite,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
            temperature=args.temperature,
            max_cases=args.max_cases,
            swap_positions=args.swap_positions,
            results_output=args.results_path,
            summary_output=args.summary_path,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
