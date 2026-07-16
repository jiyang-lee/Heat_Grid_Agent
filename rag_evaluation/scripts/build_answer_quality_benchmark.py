"""Build a 100-case original-versus-regenerated answer benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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
from retrieval_adapter import RagSearcherAdapter


CHUNKS_PATH = Path("data/rag_sources/metadata/rag_chunks.jsonl")
DATASET_PATH = Path("rag_evaluation/answer_evaluation/answer_quality_eval_100.jsonl")
INITIAL_PATH = Path("rag_evaluation/results/answer_quality_initial_100.jsonl")
REGENERATED_PATH = Path("rag_evaluation/results/answer_quality_regenerated_100.jsonl")
JUDGE_PATH = Path("rag_evaluation/results/original_regenerated_judge_100.jsonl")
JUDGE_SWAP_PATH = Path(
    "rag_evaluation/results/original_regenerated_judge_swap_100.jsonl"
)
VALIDATION_PATH = Path(
    "rag_evaluation/results/answer_quality_benchmark_100_validation.json"
)
RAG_RAW_PATH = Path("rag_evaluation/results/answer_quality_rag_raw_100.jsonl")
JUDGE_PROMPT_PATH = Path(
    "rag_evaluation/llm_judge/original_regenerated_judge_prompt.md"
)

CASE_COUNT = 100
ANSWERABLE_SINGLE_COUNT = 80
ANSWERABLE_MULTI_COUNT = 10

CATEGORIES = {
    "operating_standard",
    "inspection_action",
    "fault_cause",
    "priority_reason",
    "safety_caution",
    "similar_case",
    "unanswerable",
}
INTENTS = {
    "reason_explanation",
    "inspection_action",
    "operating_standard",
    "priority_reason",
    "fault_cause",
    "safety",
    "comparison",
    "unknown",
}
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _prepare_output(path: Path, overwrite: bool) -> dict[str, dict[str, Any]]:
    target = resolve_repo_path(path)
    if overwrite:
        write_jsonl(path, [])
        return {}
    if not target.exists():
        return {}
    return {str(row["case_id"]): row for row in load_jsonl(path)}


def _call_json(
    *,
    prompt: str,
    payload: dict[str, Any],
    model: str,
    timeout_seconds: int,
    max_retries: int,
    validate: Callable[[dict[str, Any]], bool],
) -> tuple[dict[str, Any], dict[str, Any]]:
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
            if parse_error or parsed is None or not validate(parsed):
                raise RuntimeError(parse_error or "invalid_response_schema")
            return parsed, usage
        except (
            RuntimeError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
        ) as exc:
            error = f"{type(exc).__name__}:{exc}"
    raise RuntimeError(error)


def _compact_chunk(chunk: dict[str, Any], *, text_limit: int = 3200) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "document_title": chunk.get("document_title"),
        "source_file": chunk.get("source_file"),
        "rag_role": chunk.get("rag_role"),
        "section_title": chunk.get("section_title"),
        "text": str(chunk.get("text") or "")[:text_limit],
    }


def _category_for_role(role: str, index: int) -> tuple[str, str]:
    if role in {"symptom_cause_action_table", "troubleshooting_manual"}:
        return (
            ("fault_cause", "fault_cause")
            if index % 2
            else ("inspection_action", "inspection_action")
        )
    if role == "fault_priority_research":
        return (
            ("priority_reason", "priority_reason")
            if index % 2
            else ("similar_case", "comparison")
        )
    if index % 3 == 0:
        return "safety_caution", "safety"
    if index % 3 == 1:
        return "operating_standard", "operating_standard"
    return "inspection_action", "inspection_action"


def _distractors(
    chunks: list[dict[str, Any]],
    primary_ids: set[str],
    seed: int,
    count: int,
) -> list[dict[str, Any]]:
    available = [row for row in chunks if row["chunk_id"] not in primary_ids]
    ranked = sorted(
        available,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['chunk_id']}".encode()
        ).hexdigest(),
    )
    return ranked[:count]


def _case_specs(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(chunks) < 90:
        raise RuntimeError("at least 90 RAG chunks are required")
    specs: list[dict[str, Any]] = []
    for index in range(1, ANSWERABLE_SINGLE_COUNT + 1):
        primary = chunks[index - 1]
        category, intent = _category_for_role(str(primary.get("rag_role")), index)
        relevant = [primary]
        contexts = relevant + _distractors(chunks, {primary["chunk_id"]}, index, 4)
        specs.append(
            {
                "case_id": f"answer_quality_{index:03d}",
                "mode": "answerable_single",
                "category": category,
                "query_intent": intent,
                "query_type": "keyword_match" if index % 3 == 0 else "semantic_paraphrase",
                "difficulty": ("easy", "medium", "hard")[index % 3],
                "answerable": True,
                "relevant": [_compact_chunk(row) for row in relevant],
                "contexts": [_compact_chunk(row) for row in contexts],
            }
        )
    for offset in range(ANSWERABLE_MULTI_COUNT):
        index = ANSWERABLE_SINGLE_COUNT + offset + 1
        primary = chunks[ANSWERABLE_SINGLE_COUNT + offset]
        partner_candidates = [
            row
            for row in chunks
            if row["chunk_id"] != primary["chunk_id"]
            and row.get("rag_role") == primary.get("rag_role")
        ]
        partner = partner_candidates[offset % len(partner_candidates)]
        category, intent = _category_for_role(str(primary.get("rag_role")), index)
        relevant = [primary, partner]
        relevant_ids = {row["chunk_id"] for row in relevant}
        contexts = relevant + _distractors(chunks, relevant_ids, index, 3)
        specs.append(
            {
                "case_id": f"answer_quality_{index:03d}",
                "mode": "answerable_multi",
                "category": category,
                "query_intent": "comparison" if category == "similar_case" else intent,
                "query_type": "multi_condition",
                "difficulty": "hard",
                "answerable": True,
                "relevant": [_compact_chunk(row) for row in relevant],
                "contexts": [_compact_chunk(row) for row in contexts],
            }
        )
    unanswerable_topics = (
        "현재 현장 밸브의 실제 개도율과 정상 여부",
        "오늘 발생한 경보의 확정 고장 원인",
        "작업지시서가 실제로 완료됐는지 여부",
        "향후 24시간 안에 고장이 발생할 정확한 시각",
        "현재 펌프 모터의 실측 절연저항",
        "특정 제조사의 보증 수리 승인 여부",
        "현재 열교환기 내부의 실제 오염 두께",
        "현장 작업자의 안전장비 착용 완료 여부",
        "지금 이 순간의 차압 센서 교정 오차",
        "다음 달의 확정 에너지 사용량",
    )
    for offset, topic in enumerate(unanswerable_topics):
        index = 91 + offset
        contexts = _distractors(chunks, set(), index, 5)
        specs.append(
            {
                "case_id": f"answer_quality_{index:03d}",
                "mode": "unanswerable",
                "category": "unanswerable",
                "query_intent": "unknown",
                "query_type": "negative_or_unanswerable",
                "difficulty": "hard",
                "answerable": False,
                "topic": topic,
                "relevant": [],
                "contexts": [_compact_chunk(row) for row in contexts],
            }
        )
    if len(specs) != CASE_COUNT:
        raise RuntimeError(f"expected {CASE_COUNT} specs, got {len(specs)}")
    return specs


CASE_PROMPT = """
You design a Korean district-heating operations evaluation case for each supplied
specification. Use only the relevant evidence. Write a natural, specific Korean
operator question. Expected points must be supported by the relevant evidence;
forbidden claims must identify plausible but unsupported overclaims. For an
unanswerable case, the question must ask for the supplied topic, expected points
must require an explicit evidence limitation and a concrete verification need,
and forbidden claims must prohibit inventing the requested current fact.

Return exactly one JSON object:
{"cases":[{"case_id":"...","query":"...","expected_answer_points":["..."],
"forbidden_claims":["..."]}]}
Return every requested case once. Use 2-4 non-empty expected points and 2-4
non-empty forbidden claims per case. Do not include Markdown.
""".strip()


def _validate_case_batch(parsed: dict[str, Any], expected_ids: set[str]) -> bool:
    rows = parsed.get("cases")
    if not isinstance(rows, list) or {row.get("case_id") for row in rows} != expected_ids:
        return False
    return all(
        isinstance(row.get("query"), str)
        and len(row["query"].strip()) >= 8
        and isinstance(row.get("expected_answer_points"), list)
        and 2 <= len(row["expected_answer_points"]) <= 4
        and all(isinstance(value, str) and value.strip() for value in row["expected_answer_points"])
        and isinstance(row.get("forbidden_claims"), list)
        and 2 <= len(row["forbidden_claims"]) <= 4
        and all(isinstance(value, str) and value.strip() for value in row["forbidden_claims"])
        for row in rows
    )


def generate_cases(args: argparse.Namespace) -> dict[str, Any]:
    chunks = load_jsonl(CHUNKS_PATH)
    specs = _case_specs(chunks)
    existing = _prepare_output(DATASET_PATH, args.overwrite)
    completed = set(existing)
    generated = 0
    for start in range(0, len(specs), args.batch_size):
        batch = [row for row in specs[start : start + args.batch_size] if row["case_id"] not in completed]
        if not batch:
            continue
        print(
            f"cases {batch[0]['case_id']}..{batch[-1]['case_id']}",
            file=sys.stderr,
        )
        expected_ids = {row["case_id"] for row in batch}
        parsed, usage = _call_json(
            prompt=CASE_PROMPT,
            payload={"specifications": batch},
            model=args.case_model,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            validate=lambda value: _validate_case_batch(value, expected_ids),
        )
        generated_by_id = {row["case_id"]: row for row in parsed["cases"]}
        records: list[dict[str, Any]] = []
        for spec in batch:
            generated_row = generated_by_id[spec["case_id"]]
            relevant_ids = [row["chunk_id"] for row in spec["relevant"]]
            records.append(
                {
                    "case_id": spec["case_id"],
                    "category": spec["category"],
                    "query": generated_row["query"].strip(),
                    "query_intent": spec["query_intent"],
                    "query_type": spec["query_type"],
                    "difficulty": spec["difficulty"],
                    "answerable": spec["answerable"],
                    "retrieval_hit_at_5": bool(relevant_ids),
                    "relevant_chunk_ids": relevant_ids,
                    "retrieved_chunk_ids": [row["chunk_id"] for row in spec["contexts"]],
                    "retrieved_contexts": spec["contexts"],
                    "expected_answer_points": generated_row["expected_answer_points"],
                    "forbidden_claims": generated_row["forbidden_claims"],
                    "review_required": True,
                    "label_status": "draft",
                    "benchmark_metadata": {
                        "case_model": args.case_model,
                        "case_mode": spec["mode"],
                        "generated_at": _utc_now(),
                        "usage": usage,
                    },
                }
            )
        _append_jsonl(DATASET_PATH, records)
        generated += len(records)
    return {"generated": generated, "total": len(load_jsonl(DATASET_PATH))}


def retrieve_cases(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_jsonl(DATASET_PATH)
    if len(dataset) != CASE_COUNT:
        raise RuntimeError(f"dataset must contain {CASE_COUNT} cases")
    adapter = RagSearcherAdapter(requested_backend=args.rag_backend, top_k=5)
    health = adapter.health()
    if health.get("active_backend") != args.rag_backend:
        raise RuntimeError(
            f"required RAG backend {args.rag_backend} is unavailable: {health}"
        )
    raw_rows: list[dict[str, Any]] = []
    updated_rows: list[dict[str, Any]] = []
    hit_count = 0
    for index, row in enumerate(dataset, start=1):
        print(f"retrieve [{index}/{len(dataset)}] {row['case_id']}", file=sys.stderr)
        raw = adapter.search_case(row)
        if raw.get("error"):
            raise RuntimeError(f"{row['case_id']}:RAG:{raw['error']}")
        if raw.get("actual_backend") != args.rag_backend:
            raise RuntimeError(
                f"{row['case_id']}:unexpected_backend:{raw.get('actual_backend')}"
            )
        chunks = (raw.get("raw_results") or {}).get("chunks") or []
        contexts = [_compact_chunk(chunk) for chunk in chunks]
        retrieved_ids = [context["chunk_id"] for context in contexts]
        relevant_ids = set(row.get("relevant_chunk_ids") or [])
        retrieval_hit = bool(relevant_ids & set(retrieved_ids))
        hit_count += int(retrieval_hit)
        metadata = dict(row.get("benchmark_metadata") or {})
        metadata["retrieval"] = {
            "requested_backend": args.rag_backend,
            "actual_backend": raw.get("actual_backend"),
            "top_k": len(contexts),
            "latency_ms": raw.get("retrieval_latency_ms"),
            "retrieved_at": raw.get("retrieval_finished_at"),
            "warnings": raw.get("warnings") or [],
        }
        updated_rows.append(
            {
                **row,
                "retrieval_hit_at_5": retrieval_hit,
                "retrieved_chunk_ids": retrieved_ids,
                "retrieved_contexts": contexts,
                "benchmark_metadata": metadata,
            }
        )
        raw_rows.append(raw)
    write_jsonl(DATASET_PATH, updated_rows)
    write_jsonl(RAG_RAW_PATH, raw_rows)
    return {
        "retrieved": len(updated_rows),
        "backend": args.rag_backend,
        "hit_at_5_count": hit_count,
        "miss_at_5_count": len(updated_rows) - hit_count,
        "health": health,
    }


INITIAL_PROMPT = """
You are a district-heating operations assistant. Answer each Korean question
using only its retrieved contexts. Keep possible causes distinct from confirmed
facts and provide practical checks when supported. Do not invent measurements,
completed work, or live field state. Citations must contain only supplied chunk
IDs. Return concise Korean answers.

Return exactly one JSON object:
{"answers":[{"case_id":"...","generated_answer":"...","cited_chunk_ids":["..."]}]}
Return every requested case once and no Markdown.
""".strip()

REGENERATION_PROMPT = """
Strictly revise each original district-heating operations answer using only the
same retrieved contexts. Preserve correct content, add supported operational
checks and cautions, distinguish hypotheses from confirmed facts, remove every
unsupported claim, and cite only supplied chunk IDs. If the evidence cannot
answer the question, state the limitation and the exact field data or document
that must be checked. Return concise Korean answers.

Return exactly one JSON object:
{"answers":[{"case_id":"...","generated_answer":"...","cited_chunk_ids":["..."]}]}
Return every requested case once and no Markdown.
""".strip()


def _validate_answer_batch(
    parsed: dict[str, Any],
    expected_ids: set[str],
    valid_citations: dict[str, set[str]],
) -> bool:
    rows = parsed.get("answers")
    if not isinstance(rows, list) or {row.get("case_id") for row in rows} != expected_ids:
        return False
    return all(
        isinstance(row.get("generated_answer"), str)
        and len(row["generated_answer"].strip()) >= 20
        and isinstance(row.get("cited_chunk_ids"), list)
        and all(
            isinstance(chunk_id, str) and chunk_id in valid_citations[row["case_id"]]
            for chunk_id in row["cited_chunk_ids"]
        )
        for row in rows
    )


def generate_answers(args: argparse.Namespace, *, regenerated: bool) -> dict[str, Any]:
    output_path = REGENERATED_PATH if regenerated else INITIAL_PATH
    existing = _prepare_output(output_path, args.overwrite)
    dataset = load_jsonl(DATASET_PATH)
    initial_by_id = (
        {row["case_id"]: row for row in load_jsonl(INITIAL_PATH)}
        if regenerated
        else {}
    )
    if len(dataset) != CASE_COUNT:
        raise RuntimeError(f"dataset must contain {CASE_COUNT} cases")
    pending = [row for row in dataset if row["case_id"] not in existing]
    generated = 0
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        print(
            f"{'regenerate' if regenerated else 'initial'} "
            f"{batch[0]['case_id']}..{batch[-1]['case_id']}",
            file=sys.stderr,
        )
        payload_rows = []
        valid_citations: dict[str, set[str]] = {}
        for row in batch:
            case_id = row["case_id"]
            valid_citations[case_id] = set(row["retrieved_chunk_ids"])
            payload = {
                "case_id": case_id,
                "query": row["query"],
                "answerable": row["answerable"],
                "retrieved_contexts": row["retrieved_contexts"],
            }
            if regenerated:
                payload["original_answer"] = {
                    "generated_answer": initial_by_id[case_id]["generated_answer"],
                    "cited_chunk_ids": initial_by_id[case_id]["cited_chunk_ids"],
                }
            payload_rows.append(payload)
        expected_ids = {row["case_id"] for row in batch}
        parsed, usage = _call_json(
            prompt=REGENERATION_PROMPT if regenerated else INITIAL_PROMPT,
            payload={"cases": payload_rows},
            model=args.answer_model,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            validate=lambda value: _validate_answer_batch(
                value, expected_ids, valid_citations
            ),
        )
        records = []
        dataset_by_id = {row["case_id"]: row for row in batch}
        for answer in parsed["answers"]:
            source = dataset_by_id[answer["case_id"]]
            records.append(
                {
                    "case_id": answer["case_id"],
                    "query": source["query"],
                    "generated_answer": answer["generated_answer"].strip(),
                    "cited_chunk_ids": list(dict.fromkeys(answer["cited_chunk_ids"])),
                    "generation_metadata": {
                        "model": args.answer_model,
                        "prompt_version": (
                            "strict-regeneration-v2-100"
                            if regenerated
                            else "initial-answer-v2-100"
                        ),
                        "generated_at": _utc_now(),
                        "usage": usage,
                    },
                }
            )
        records.sort(key=lambda row: row["case_id"])
        _append_jsonl(output_path, records)
        generated += len(records)
    return {"generated": generated, "total": len(load_jsonl(output_path))}


def _candidate_order(case_id: str, swap: bool) -> tuple[str, str]:
    original_first = hashlib.sha256(case_id.encode()).digest()[0] % 2 == 0
    order = (
        ("initial", "regenerated")
        if original_first
        else ("regenerated", "initial")
    )
    return (order[1], order[0]) if swap else order


def _valid_candidate(candidate: object) -> bool:
    if not isinstance(candidate, dict):
        return False
    if any(
        not isinstance(candidate.get(field), int)
        or not 1 <= candidate[field] <= 5
        for field in DIMENSIONS
    ):
        return False
    tags = candidate.get("failure_tags")
    return (
        candidate.get("unsupported_claim_risk") in RISKS
        and isinstance(tags, list)
        and bool(tags)
        and all(tag in FAILURE_TAGS for tag in tags)
        and candidate.get("quality_recommendation") in {"PASS", "REGENERATE"}
    )


def _validate_judge_batch(parsed: dict[str, Any], expected_ids: set[str]) -> bool:
    rows = parsed.get("judgments")
    if not isinstance(rows, list) or {row.get("case_id") for row in rows} != expected_ids:
        return False
    return all(
        _valid_candidate(row.get("candidate_a"))
        and _valid_candidate(row.get("candidate_b"))
        and row.get("overall_winner") in {"A", "B", "TIE"}
        and row.get("winner_strength") in {"CLEAR", "SLIGHT", "TIE"}
        and row.get("review_priority") in {"HIGH", "MEDIUM", "LOW"}
        and isinstance(row.get("reason"), str)
        for row in rows
    )


def judge_answers(args: argparse.Namespace, *, swap: bool) -> dict[str, Any]:
    output_path = JUDGE_SWAP_PATH if swap else JUDGE_PATH
    existing = _prepare_output(output_path, args.overwrite)
    dataset_by_id = {row["case_id"]: row for row in load_jsonl(DATASET_PATH)}
    initial_by_id = {row["case_id"]: row for row in load_jsonl(INITIAL_PATH)}
    regenerated_by_id = {
        row["case_id"]: row for row in load_jsonl(REGENERATED_PATH)
    }
    shared = sorted(set(dataset_by_id) & set(initial_by_id) & set(regenerated_by_id))
    if len(shared) != CASE_COUNT:
        raise RuntimeError(f"expected {CASE_COUNT} complete answer pairs, got {len(shared)}")
    pending = [case_id for case_id in shared if case_id not in existing]
    base_prompt = resolve_repo_path(JUDGE_PROMPT_PATH).read_text(encoding="utf-8")
    prompt = (
        base_prompt
        + "\n\nEvaluate every case in the supplied cases array. Return exactly one "
        "JSON object with key judgments, whose value is an array of the required "
        "judgment objects. Add case_id to each judgment. When retrieval_hit_at_5 "
        "is false, do not require expected points that are absent from the "
        "reference evidence. In that situation, reward an explicit evidence "
        "limitation and concrete verification request, and penalize candidates "
        "that invent the missing answer. Apply the same evidence-limitation "
        "policy when answerable is false. Return no Markdown."
    )
    judged = 0
    for start in range(0, len(pending), args.batch_size):
        case_ids = pending[start : start + args.batch_size]
        print(
            f"judge swap={swap} {case_ids[0]}..{case_ids[-1]}",
            file=sys.stderr,
        )
        payload_rows = []
        orders: dict[str, tuple[str, str]] = {}
        for case_id in case_ids:
            first, second = _candidate_order(case_id, swap)
            orders[case_id] = (first, second)
            answers = {
                "initial": initial_by_id[case_id],
                "regenerated": regenerated_by_id[case_id],
            }
            dataset = dataset_by_id[case_id]
            payload_rows.append(
                {
                    "case_id": case_id,
                    "question": dataset["query"],
                    "answerable": dataset["answerable"],
                    "retrieval_hit_at_5": dataset["retrieval_hit_at_5"],
                    "expected_answer_points": dataset["expected_answer_points"],
                    "forbidden_claims": dataset["forbidden_claims"],
                    "reference_evidence": [
                        {"chunk_id": row["chunk_id"], "text": row["text"]}
                        for row in dataset["retrieved_contexts"]
                    ],
                    "candidate_a": {
                        "answer": answers[first]["generated_answer"],
                        "cited_chunk_ids": answers[first]["cited_chunk_ids"],
                    },
                    "candidate_b": {
                        "answer": answers[second]["generated_answer"],
                        "cited_chunk_ids": answers[second]["cited_chunk_ids"],
                    },
                }
            )
        expected_ids = set(case_ids)
        parsed, usage = _call_json(
            prompt=prompt,
            payload={"cases": payload_rows},
            model=args.judge_model,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            validate=lambda value: _validate_judge_batch(value, expected_ids),
        )
        records = []
        for judgment in parsed["judgments"]:
            case_id = judgment["case_id"]
            first, second = orders[case_id]
            mapping = {"A": first, "B": second}
            winner = judgment["overall_winner"]
            dataset = dataset_by_id[case_id]
            records.append(
                {
                    "case_id": case_id,
                    "candidate_mapping": mapping,
                    "initial": (
                        judgment["candidate_a"]
                        if first == "initial"
                        else judgment["candidate_b"]
                    ),
                    "regenerated": (
                        judgment["candidate_a"]
                        if first == "regenerated"
                        else judgment["candidate_b"]
                    ),
                    "winner": "tie" if winner == "TIE" else mapping[winner],
                    "winner_strength": judgment["winner_strength"].lower(),
                    "review_priority": judgment["review_priority"],
                    "reason": judgment["reason"],
                    "metadata": {
                        "category": dataset["category"],
                        "difficulty": dataset["difficulty"],
                        "answerable": dataset["answerable"],
                        "retrieval_hit_at_5": dataset["retrieval_hit_at_5"],
                        "valid_chunk_ids": dataset["retrieved_chunk_ids"],
                        "initial_answer": {
                            "answer": initial_by_id[case_id]["generated_answer"],
                            "cited_chunk_ids": initial_by_id[case_id]["cited_chunk_ids"],
                        },
                        "regenerated_answer": {
                            "answer": regenerated_by_id[case_id]["generated_answer"],
                            "cited_chunk_ids": regenerated_by_id[case_id]["cited_chunk_ids"],
                        },
                    },
                    "judge_metadata": {
                        "model": args.judge_model,
                        "swap": swap,
                        "usage": usage,
                    },
                }
            )
        records.sort(key=lambda row: row["case_id"])
        _append_jsonl(output_path, records)
        judged += len(records)
    return {"judged": judged, "total": len(load_jsonl(output_path)), "swap": swap}


def validate_benchmark() -> dict[str, Any]:
    chunks = {row["chunk_id"]: row for row in load_jsonl(CHUNKS_PATH)}
    rag_raw = load_jsonl(RAG_RAW_PATH)
    retrieved_registry = {
        chunk.get("chunk_id")
        for raw in rag_raw
        for chunk in (raw.get("raw_results") or {}).get("chunks") or []
        if chunk.get("chunk_id")
    }
    known_chunk_ids = set(chunks) | retrieved_registry
    dataset = load_jsonl(DATASET_PATH)
    initial = load_jsonl(INITIAL_PATH)
    regenerated = load_jsonl(REGENERATED_PATH)
    first = load_jsonl(JUDGE_PATH)
    swapped = load_jsonl(JUDGE_SWAP_PATH)
    errors: list[str] = []
    dataset_ids = [row.get("case_id") for row in dataset]
    if len(dataset) != CASE_COUNT or len(set(dataset_ids)) != CASE_COUNT:
        errors.append("dataset_case_count_or_uniqueness_failed")
    queries = [str(row.get("query") or "").strip().casefold() for row in dataset]
    if len(set(queries)) != len(queries):
        errors.append("duplicate_queries")
    for row in dataset:
        context_ids = row.get("retrieved_chunk_ids") or []
        if len(context_ids) != 5 or len(set(context_ids)) != 5:
            errors.append(f"{row.get('case_id')}:context_count_or_uniqueness")
        if any(chunk_id not in known_chunk_ids for chunk_id in context_ids):
            errors.append(f"{row.get('case_id')}:unknown_context")
        expected_hit = bool(
            set(row.get("relevant_chunk_ids") or []) & set(context_ids)
        )
        if bool(row.get("retrieval_hit_at_5")) != expected_hit:
            errors.append(f"{row.get('case_id')}:retrieval_hit_flag_mismatch")
        retrieval = (row.get("benchmark_metadata") or {}).get("retrieval") or {}
        if retrieval.get("actual_backend") != "pgvector":
            errors.append(f"{row.get('case_id')}:non_pgvector_retrieval")
        if row.get("category") not in CATEGORIES or row.get("query_intent") not in INTENTS:
            errors.append(f"{row.get('case_id')}:invalid_taxonomy")
    for name, rows in (
        ("initial", initial),
        ("regenerated", regenerated),
        ("judge", first),
        ("judge_swap", swapped),
    ):
        ids = [row.get("case_id") for row in rows]
        if len(rows) != CASE_COUNT or set(ids) != set(dataset_ids):
            errors.append(f"{name}:case_coverage_failed")
    summary = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "unique_case_count": len(set(dataset_ids)),
        "unique_query_count": len(set(queries)),
        "actual_answer_count": len(initial) + len(regenerated),
        "comparison_count": len(first) + len(swapped),
        "candidate_observation_count": (len(first) + len(swapped)) * 2,
        "answerable_distribution": dict(Counter(str(row.get("answerable")) for row in dataset)),
        "retrieval_hit_distribution": dict(
            Counter(str(row.get("retrieval_hit_at_5")) for row in dataset)
        ),
        "category_distribution": dict(Counter(row.get("category") for row in dataset)),
        "difficulty_distribution": dict(Counter(row.get("difficulty") for row in dataset)),
        "source_distribution": dict(
            Counter(
                context.get("source_file")
                for row in dataset
                for context in row.get("retrieved_contexts") or []
                if context.get("chunk_id") in set(row.get("relevant_chunk_ids") or [])
            )
        ),
        "retrieved_source_distribution": dict(
            Counter(
                context.get("source_file") or "unknown"
                for row in dataset
                for context in row.get("retrieved_contexts") or []
            )
        ),
        "validated_at": _utc_now(),
    }
    write_json(VALIDATION_PATH, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "cases",
            "retrieve",
            "initial",
            "regenerate",
            "judge",
            "validate",
            "all",
        ],
    )
    parser.add_argument("--case-model", default="gpt-5.4-mini")
    parser.add_argument("--answer-model", default="gpt-5.4-mini")
    parser.add_argument("--judge-model", default="gpt-5.4")
    parser.add_argument("--rag-backend", choices=["pgvector"], default="pgvector")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 10:
        raise SystemExit("--batch-size must be between 1 and 10")
    load_dotenv()
    if args.stage != "validate" and not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not configured")
    result: dict[str, Any] = {}
    if args.stage in {"cases", "all"}:
        result["cases"] = generate_cases(args)
        args.overwrite = False
    if args.stage in {"retrieve", "all"}:
        result["retrieve"] = retrieve_cases(args)
    if args.stage in {"initial", "all"}:
        result["initial"] = generate_answers(args, regenerated=False)
    if args.stage in {"regenerate", "all"}:
        result["regenerated"] = generate_answers(args, regenerated=True)
    if args.stage in {"judge", "all"}:
        result["judge"] = judge_answers(args, swap=False)
        result["judge_swap"] = judge_answers(args, swap=True)
    if args.stage in {"validate", "all"}:
        result["validation"] = validate_benchmark()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
