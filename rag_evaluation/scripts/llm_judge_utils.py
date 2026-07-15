"""Utilities for planned HeatGrid LLM Judge evaluation.

Stage 7.5 step 1 only designs the judge flow. API execution is intentionally
not implemented here until the user approves step 2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
JUDGE_PROMPT_VERSION = "llm-judge-v1.0-draft"


def resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in resolve_repo_path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def build_judge_input(generated: dict[str, Any], dataset_row: dict[str, Any]) -> dict[str, Any]:
    """Build the future Judge input.

    This input may include expected answer points and forbidden claims because
    the Judge is a separate evaluator, not the answer generator.
    """

    return {
        "case_id": generated.get("case_id"),
        "query": generated.get("query"),
        "generated_answer": generated.get("generated_answer"),
        "cited_chunk_ids": generated.get("cited_chunk_ids") or [],
        "retrieved_contexts": dataset_row.get("retrieved_contexts") or [],
        "expected_answer_points": dataset_row.get("expected_answer_points") or [],
        "forbidden_claims": dataset_row.get("forbidden_claims") or [],
        "answerable": dataset_row.get("answerable"),
        "retrieval_hit_at_5": dataset_row.get("retrieval_hit_at_5"),
    }


def estimate_prompt_payloads(
    generation_path: str | Path = "rag_evaluation/results/answer_generation_all.jsonl",
    dataset_path: str | Path = "rag_evaluation/answer_evaluation/answer_eval.draft.jsonl",
) -> list[dict[str, Any]]:
    generated_rows = load_jsonl(generation_path)
    dataset_by_case = {row["case_id"]: row for row in load_jsonl(dataset_path)}
    return [build_judge_input(row, dataset_by_case[row["case_id"]]) for row in generated_rows]
