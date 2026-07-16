"""Generate and calibrate original-versus-regenerated answer quality rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sklearn.model_selection import StratifiedGroupKFold

from llm_judge_utils import (
    build_model_input,
    load_dotenv,
    load_jsonl,
    parse_model_json,
    resolve_repo_path,
    write_json,
)
from run_llm_judge import call_openai_responses


INITIAL_PATH = Path("rag_evaluation/results/answer_quality_initial_100.jsonl")
DATASET_PATH = Path("rag_evaluation/answer_evaluation/answer_quality_eval_100.jsonl")
REGENERATED_PATH = Path("rag_evaluation/results/answer_quality_regenerated_100.jsonl")
JUDGE_PROMPT_PATH = Path(
    "rag_evaluation/llm_judge/original_regenerated_judge_prompt.md"
)
JUDGE_PATH = Path("rag_evaluation/results/original_regenerated_judge_100.jsonl")
JUDGE_SWAP_PATH = Path(
    "rag_evaluation/results/original_regenerated_judge_swap_100.jsonl"
)
POLICY_PATH = Path("rag_evaluation/baselines/answer_quality_policy_v2_100.json")
ANALYSIS_PATH = Path(
    "rag_evaluation/results/answer_quality_rule_calibration_100.json"
)

WEIGHTS = {
    "correctness": 0.30,
    "completeness": 0.15,
    "actionability": 0.20,
    "evidence_grounding": 0.25,
    "calibration": 0.10,
}
DIMENSIONS = tuple(WEIGHTS)
RISKS = {"NONE", "LOW", "MEDIUM", "HIGH"}
FAILURE_TAGS = {
    "missed_expected_point",
    "unsupported_claim",
    "over_abstention",
    "unsafe_action",
    "citation_mismatch",
    "none",
}


def _answer_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": row.get("generated_answer"),
        "cited_chunk_ids": row.get("cited_chunk_ids") or [],
    }


def _initialize_jsonl(path: Path, *, overwrite: bool) -> Path:
    target = resolve_repo_path(path)
    if target.exists() and not overwrite:
        raise SystemExit(f"{path} exists; pass --overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


def _append_jsonl(target: Path, record: dict[str, Any]) -> None:
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _regeneration_input(
    initial: dict[str, Any],
    dataset: dict[str, Any],
) -> str:
    payload = {
        "case_id": dataset["case_id"],
        "question": dataset.get("query"),
        "answerable": dataset.get("answerable"),
        "retrieval_hit_at_5": dataset.get("retrieval_hit_at_5"),
        "retrieved_contexts": dataset.get("retrieved_contexts") or [],
        "original_answer": _answer_payload(initial),
    }
    prompt = (
        "Revise the original district-heating operations answer using only the "
        "supplied evidence. Preserve correct content, fill operational omissions, "
        "distinguish candidate causes from confirmed facts, remove unsupported "
        "claims, and use only supplied chunk IDs. If evidence is insufficient, say "
        "what must be checked. Return exactly one JSON object with keys "
        "generated_answer and cited_chunk_ids."
    )
    return build_model_input(prompt, payload)


def generate_regenerated(
    *,
    model: str,
    overwrite: bool,
    max_retries: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    target = resolve_repo_path(REGENERATED_PATH)
    target = _initialize_jsonl(REGENERATED_PATH, overwrite=overwrite)
    initial_rows = load_jsonl(INITIAL_PATH)
    dataset_by_case = {row["case_id"]: row for row in load_jsonl(DATASET_PATH)}
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, initial in enumerate(initial_rows, start=1):
        case_id = str(initial["case_id"])
        print(f"[{index}/{len(initial_rows)}] regenerating {case_id}", file=sys.stderr)
        parsed: dict[str, Any] | None = None
        usage: dict[str, Any] = {}
        error = "unknown"
        for attempt in range(max_retries + 1):
            if attempt:
                time.sleep(1 + attempt)
            try:
                raw, usage = call_openai_responses(
                    _regeneration_input(initial, dataset_by_case[case_id]),
                    model,
                    0.0,
                    timeout_seconds,
                )
                parsed, parse_error = parse_model_json(raw)
                if parse_error or parsed is None:
                    raise RuntimeError(parse_error or "response_not_object")
                if not isinstance(parsed.get("generated_answer"), str):
                    raise RuntimeError("generated_answer:not_string")
                if not isinstance(parsed.get("cited_chunk_ids"), list):
                    raise RuntimeError("cited_chunk_ids:not_list")
                break
            except (
                RuntimeError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
            ) as exc:
                error = f"{type(exc).__name__}:{exc}"
                parsed = None
        if parsed is None:
            failures.append({"case_id": case_id, "error": error})
            continue
        record = {
            "case_id": case_id,
            "query": initial.get("query"),
            "generated_answer": parsed["generated_answer"],
            "cited_chunk_ids": parsed["cited_chunk_ids"],
            "generation_metadata": {
                "model": model,
                "prompt_version": "strict-regeneration-v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "usage": usage,
            },
        }
        records.append(record)
        _append_jsonl(target, record)
    return {
        "generated_count": len(records),
        "failure_count": len(failures),
        "failures": failures,
    }


def _candidate_order(case_id: str, swap: bool) -> tuple[str, str]:
    original_first = hashlib.sha256(case_id.encode()).digest()[0] % 2 == 0
    order: tuple[str, str] = (
        ("initial", "regenerated")
        if original_first
        else ("regenerated", "initial")
    )
    return (order[1], order[0]) if swap else order


def _validate_candidate(candidate: object) -> bool:
    if not isinstance(candidate, dict):
        return False
    if any(
        not isinstance(candidate.get(field), int)
        or not 1 <= candidate[field] <= 5
        for field in DIMENSIONS
    ):
        return False
    if candidate.get("unsupported_claim_risk") not in RISKS:
        return False
    tags = candidate.get("failure_tags")
    if not isinstance(tags, list) or not tags or any(tag not in FAILURE_TAGS for tag in tags):
        return False
    return candidate.get("quality_recommendation") in {"PASS", "REGENERATE"}


def _validate_judgment(parsed: dict[str, Any]) -> bool:
    return (
        _validate_candidate(parsed.get("candidate_a"))
        and _validate_candidate(parsed.get("candidate_b"))
        and parsed.get("overall_winner") in {"A", "B", "TIE"}
        and parsed.get("winner_strength") in {"CLEAR", "SLIGHT", "TIE"}
        and parsed.get("review_priority") in {"HIGH", "MEDIUM", "LOW"}
        and isinstance(parsed.get("reason"), str)
    )


def judge_pairs(
    *,
    model: str,
    swap: bool,
    overwrite: bool,
    max_retries: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    output_path = JUDGE_SWAP_PATH if swap else JUDGE_PATH
    target = _initialize_jsonl(output_path, overwrite=overwrite)
    initial_by_case = {row["case_id"]: row for row in load_jsonl(INITIAL_PATH)}
    regenerated_by_case = {
        row["case_id"]: row for row in load_jsonl(REGENERATED_PATH)
    }
    dataset_by_case = {row["case_id"]: row for row in load_jsonl(DATASET_PATH)}
    case_ids = sorted(set(initial_by_case) & set(regenerated_by_case) & set(dataset_by_case))
    prompt = resolve_repo_path(JUDGE_PROMPT_PATH).read_text(encoding="utf-8")
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, case_id in enumerate(case_ids, start=1):
        print(f"[{index}/{len(case_ids)}] judging {case_id} swap={swap}", file=sys.stderr)
        first, second = _candidate_order(case_id, swap)
        answers = {
            "initial": initial_by_case[case_id],
            "regenerated": regenerated_by_case[case_id],
        }
        dataset = dataset_by_case[case_id]
        payload = {
            "case_id": case_id,
            "question": dataset.get("query"),
            "answerable": dataset.get("answerable"),
            "expected_answer_points": dataset.get("expected_answer_points") or [],
            "forbidden_claims": dataset.get("forbidden_claims") or [],
            "reference_evidence": [
                {"chunk_id": row.get("chunk_id"), "text": row.get("text")}
                for row in dataset.get("retrieved_contexts") or []
            ],
            "candidate_a": _answer_payload(answers[first]),
            "candidate_b": _answer_payload(answers[second]),
        }
        parsed: dict[str, Any] | None = None
        usage: dict[str, Any] = {}
        error = "unknown"
        for attempt in range(max_retries + 1):
            if attempt:
                time.sleep(1 + attempt)
            try:
                raw, usage = call_openai_responses(
                    build_model_input(prompt, payload),
                    model,
                    0.0,
                    timeout_seconds,
                )
                parsed, parse_error = parse_model_json(raw)
                if parse_error or not _validate_judgment(parsed or {}):
                    raise RuntimeError(parse_error or "invalid_judgment_schema")
                break
            except (
                RuntimeError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
            ) as exc:
                error = f"{type(exc).__name__}:{exc}"
                parsed = None
        if parsed is None:
            failures.append({"case_id": case_id, "error": error})
            continue
        mapping = {"A": first, "B": second}
        winner = parsed["overall_winner"]
        record = {
                "case_id": case_id,
                "candidate_mapping": mapping,
                "initial": parsed["candidate_a"]
                if first == "initial"
                else parsed["candidate_b"],
                "regenerated": parsed["candidate_a"]
                if first == "regenerated"
                else parsed["candidate_b"],
                "winner": "tie" if winner == "TIE" else mapping[winner],
                "winner_strength": parsed["winner_strength"].lower(),
                "review_priority": parsed["review_priority"],
                "reason": parsed["reason"],
                "metadata": {
                    "category": dataset.get("category"),
                    "difficulty": dataset.get("difficulty"),
                    "answerable": dataset.get("answerable"),
                    "retrieval_hit_at_5": dataset.get("retrieval_hit_at_5"),
                    "valid_chunk_ids": [
                        row.get("chunk_id") for row in dataset.get("retrieved_contexts") or []
                    ],
                    "initial_answer": _answer_payload(initial_by_case[case_id]),
                    "regenerated_answer": _answer_payload(regenerated_by_case[case_id]),
                },
                "judge_metadata": {"model": model, "swap": swap, "usage": usage},
            }
        records.append(record)
        _append_jsonl(target, record)
    return {
        "judged_count": len(records),
        "candidate_observation_count": len(records) * 2,
        "failure_count": len(failures),
        "failures": failures,
    }


def _score(candidate: dict[str, Any]) -> float:
    return round(
        sum(candidate[field] * WEIGHTS[field] for field in DIMENSIONS) / 5 * 100,
        2,
    )


def _deterministic_features(
    candidate: dict[str, Any],
    answer: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, bool]:
    citations = answer.get("cited_chunk_ids") or []
    valid_ids = set(metadata.get("valid_chunk_ids") or [])
    text = str(answer.get("answer") or "").strip()
    return {
        "empty_answer": not text,
        "very_short_answer": 0 < len(text) < 80,
        "invalid_citation": any(chunk_id not in valid_ids for chunk_id in citations),
        "missing_citation_on_retrieval_hit": bool(metadata.get("retrieval_hit_at_5"))
        and bool(metadata.get("answerable"))
        and not citations,
        "judge_low_correctness": candidate["correctness"] <= 2,
        "judge_low_grounding": candidate["evidence_grounding"] <= 2,
        "judge_unsupported_risk": candidate["unsupported_claim_risk"]
        in {"MEDIUM", "HIGH"},
        "judge_citation_mismatch": "citation_mismatch" in candidate["failure_tags"],
        "judge_unsafe_action": "unsafe_action" in candidate["failure_tags"],
        "judge_over_abstention": "over_abstention" in candidate["failure_tags"],
    }


def _observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for row in rows:
        for variant in ("initial", "regenerated"):
            candidate = row[variant]
            answer = row["metadata"][f"{variant}_answer"]
            observations.append(
                {
                    "case_id": row["case_id"],
                    "variant": variant,
                    "score": _score(candidate),
                    "target_pass": candidate["quality_recommendation"] == "PASS",
                    "category": row["metadata"].get("category"),
                    "answerable": row["metadata"].get("answerable"),
                    "retrieval_hit_at_5": row["metadata"].get("retrieval_hit_at_5"),
                    "features": _deterministic_features(
                        candidate,
                        answer,
                        row["metadata"],
                    ),
                }
            )
    return observations


def _metrics(rows: list[dict[str, Any]], threshold: float, rules: set[str]) -> dict[str, Any]:
    counts = Counter()
    for row in rows:
        rule_failed = any(row["features"].get(rule) for rule in rules)
        predicted_pass = row["score"] >= threshold and not rule_failed
        actual_pass = row["target_pass"]
        key = ("t" if predicted_pass == actual_pass else "f") + (
            "p" if predicted_pass else "n"
        )
        counts[key] += 1
    tp, fp, tn, fn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
    return {
        "threshold": threshold,
        "count": len(rows),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": (tp + tn) / len(rows) if rows else 0.0,
        "bad_answer_capture_rate": tn / (tn + fp) if tn + fp else 1.0,
        "false_pass_rate": fp / (tn + fp) if tn + fp else 0.0,
        "unnecessary_regeneration_rate": fn / (tp + fn) if tp + fn else 0.0,
    }


def _rule_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    names = sorted({name for row in rows for name in row["features"]})
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        triggered = [row for row in rows if row["features"].get(name)]
        bad = [row for row in triggered if not row["target_pass"]]
        result[name] = {
            "support": len(triggered),
            "bad_count": len(bad),
            "bad_precision": len(bad) / len(triggered) if triggered else None,
            "adopt_as_hard_rule": len(triggered) >= 3
            and len(bad) / len(triggered) >= 0.90,
        }
    return result


def _choose_threshold(rows: list[dict[str, Any]], rules: set[str]) -> dict[str, Any]:
    candidates = [_metrics(rows, float(value), rules) for value in range(50, 91)]
    safe = [row for row in candidates if row["false_pass_rate"] <= 0.05]
    pool = safe or candidates
    return max(
        pool,
        key=lambda row: (
            row["accuracy"],
            -row["unnecessary_regeneration_rate"],
            -abs(row["threshold"] - 70),
        ),
    )


def _fold_assignments(rows: list[dict[str, Any]]) -> dict[int, int]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    labels = [int(row["target_pass"]) for row in rows]
    groups = [row["case_id"] for row in rows]
    assignments: dict[int, int] = {}
    for fold, (_train, test) in enumerate(
        splitter.split([[0]] * len(rows), labels, groups)
    ):
        assignments.update({int(index): fold for index in test})
    return assignments


def _aggregate_fold_metrics(folds: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    for fold in folds:
        metrics = fold["test_metrics"]
        for key in ("tp", "fp", "tn", "fn", "count"):
            totals[key] += metrics[key]
    tp, fp, tn, fn = totals["tp"], totals["fp"], totals["tn"], totals["fn"]
    return {
        "count": totals["count"],
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": (tp + tn) / totals["count"],
        "bad_answer_capture_rate": tn / (tn + fp) if tn + fp else 1.0,
        "false_pass_rate": fp / (tn + fp) if tn + fp else 0.0,
        "unnecessary_regeneration_rate": fn / (tp + fn) if tp + fn else 0.0,
    }


def _judge_stability(
    first_pass: list[dict[str, Any]],
    swapped_pass: list[dict[str, Any]],
) -> dict[str, Any]:
    first_by_case = {row["case_id"]: row for row in first_pass}
    swapped_by_case = {row["case_id"]: row for row in swapped_pass}
    shared = sorted(set(first_by_case) & set(swapped_by_case))
    candidate_count = 0
    recommendation_agreements = 0
    score_deltas: list[float] = []
    disagreements: list[dict[str, Any]] = []
    for case_id in shared:
        for variant in ("initial", "regenerated"):
            first = first_by_case[case_id][variant]
            swapped = swapped_by_case[case_id][variant]
            first_score = _score(first)
            swapped_score = _score(swapped)
            candidate_count += 1
            score_deltas.append(abs(first_score - swapped_score))
            same = (
                first["quality_recommendation"]
                == swapped["quality_recommendation"]
            )
            recommendation_agreements += int(same)
            if not same:
                disagreements.append(
                    {
                        "case_id": case_id,
                        "variant": variant,
                        "first_recommendation": first["quality_recommendation"],
                        "swapped_recommendation": swapped["quality_recommendation"],
                        "first_score": first_score,
                        "swapped_score": swapped_score,
                    }
                )
    disagreement_scores = [
        score
        for row in disagreements
        for score in (row["first_score"], row["swapped_score"])
    ]
    winner_agreements = sum(
        first_by_case[case_id]["winner"] == swapped_by_case[case_id]["winner"]
        for case_id in shared
    )
    return {
        "case_count": len(shared),
        "candidate_count": candidate_count,
        "candidate_recommendation_agreement_count": recommendation_agreements,
        "candidate_recommendation_agreement_rate": recommendation_agreements
        / candidate_count,
        "winner_agreement_count": winner_agreements,
        "winner_agreement_rate": winner_agreements / len(shared),
        "mean_absolute_score_delta": statistics.fmean(score_deltas),
        "maximum_absolute_score_delta": max(score_deltas),
        "disagreement_count": len(disagreements),
        "disagreement_score_range": None
        if not disagreement_scores
        else [min(disagreement_scores), max(disagreement_scores)],
        "disagreements": disagreements,
    }


def analyze() -> dict[str, Any]:
    first_pass = load_jsonl(JUDGE_PATH)
    swapped_pass = load_jsonl(JUDGE_SWAP_PATH)
    rows = first_pass + swapped_pass
    observations = _observations(rows)
    rule_stats = _rule_stats(observations)
    adopted = {
        name for name, stats in rule_stats.items() if stats["adopt_as_hard_rule"]
    }
    selected = _choose_threshold(observations, adopted)
    fold_assignments = _fold_assignments(observations)
    folds: list[dict[str, Any]] = []
    for fold in range(5):
        train = [
            row
            for index, row in enumerate(observations)
            if fold_assignments[index] != fold
        ]
        test = [
            row
            for index, row in enumerate(observations)
            if fold_assignments[index] == fold
        ]
        train_rule_stats = _rule_stats(train)
        train_rules = {
            name
            for name, stats in train_rule_stats.items()
            if stats["adopt_as_hard_rule"]
        }
        train_choice = _choose_threshold(train, train_rules)
        folds.append(
            {
                "fold": fold,
                "train_threshold": train_choice["threshold"],
                "train_rules": sorted(train_rules),
                "test_metrics": _metrics(
                    test,
                    train_choice["threshold"],
                    train_rules,
                ),
            }
        )
    stable_threshold = float(
        statistics.median(row["train_threshold"] for row in folds)
    )
    threshold_stability_range = [
        min(row["train_threshold"] for row in folds),
        max(row["train_threshold"] for row in folds),
    ]
    out_of_fold_metrics = _aggregate_fold_metrics(folds)
    judge_stability = _judge_stability(first_pass, swapped_pass)
    winner_counts = dict(Counter(row["winner"] for row in rows))
    analysis = {
        "status": "draft_reference",
        "comparison_count": len(rows),
        "candidate_observation_count": len(observations),
        "unique_case_count": len({row["case_id"] for row in observations}),
        "winner_counts": winner_counts,
        "rule_stats": rule_stats,
        "adopted_hard_rules": sorted(adopted),
        "full_sample_selection": selected,
        "cross_validation": folds,
        "out_of_fold_metrics": out_of_fold_metrics,
        "judge_stability": judge_stability,
        "cross_validated_threshold": stable_threshold,
        "threshold_stability_range": threshold_stability_range,
        "methodology": (
            "All candidate observations are used through StratifiedGroupKFold with "
            "case_id as the group; no fixed 60/20/20 split is used."
        ),
    }
    policy = {
        "policy_version": "answer-quality-policy.v2-100-rag-single-judge-draft",
        "status": "draft_reference",
        "threshold": stable_threshold,
        "weights": WEIGHTS,
        "hard_rules": sorted(adopted),
        "tie_policy": "keep_initial",
        "maximum_regenerations": 1,
        "calibration_source": str(ANALYSIS_PATH),
        "candidate_observation_count": len(observations),
        "out_of_fold_metrics": out_of_fold_metrics,
        "judge_stability": {
            key: value
            for key, value in judge_stability.items()
            if key != "disagreements"
        },
        "offline_threshold_stability_range": threshold_stability_range,
        "limitations": [
            "Labels are produced by an LLM Judge and require human review.",
            f"The {len(observations)} observations come from "
            f"{len({row['case_id'] for row in observations})} unique operational "
            "cases judged twice.",
            "Runtime production logs should be used for the next policy revision.",
        ],
    }
    write_json(ANALYSIS_PATH, analysis)
    write_json(POLICY_PATH, policy)
    return {"analysis": analysis, "policy": policy}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["generate", "judge", "analyze", "all"],
    )
    parser.add_argument("--generation-model", default="gpt-5.4-mini")
    parser.add_argument("--judge-model", default="gpt-5.4")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    load_dotenv()
    if args.stage in {"generate", "judge", "all"} and not os.environ.get(
        "OPENAI_API_KEY"
    ):
        raise SystemExit("OPENAI_API_KEY is not configured")
    result: dict[str, Any] = {}
    if args.stage in {"generate", "all"}:
        result["generate"] = generate_regenerated(
            model=args.generation_model,
            overwrite=args.overwrite,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
        )
    if args.stage in {"judge", "all"}:
        result["judge"] = judge_pairs(
            model=args.judge_model,
            swap=False,
            overwrite=args.overwrite,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
        )
        result["judge_swap"] = judge_pairs(
            model=args.judge_model,
            swap=True,
            overwrite=args.overwrite,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
        )
    if args.stage in {"analyze", "all"}:
        result["analysis"] = analyze()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
