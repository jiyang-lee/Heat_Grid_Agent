"""Utilities for HeatGrid answer generation evaluation.

This module intentionally lives under rag_evaluation/ and does not import
production Agent or RAG code. It prepares safe generation inputs from the
draft answer evaluation dataset.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

PROMPT_VERSION = "answer-generation-v1.1-miss-citation-strict"
DEFAULT_CONFIG_PATH = Path("rag_evaluation/answer_generation/answer_generation_config.yaml")

FORBIDDEN_INPUT_FIELDS = {
    "expected_answer_points",
    "relevant_chunk_ids",
    "partially_relevant_chunk_ids",
    "forbidden_claims",
    "human_scores",
    "automated_scores",
    "label_status",
    "metrics",
    "evaluation_metadata",
    "retrieval_recall_at_5",
}

ALLOWED_INPUT_FIELDS = {
    "case_id",
    "query",
    "category",
    "query_intent",
    "query_type",
    "difficulty",
    "answerable",
    "retrieval_hit_at_5",
    "retrieved_contexts",
}

CAUTION_PHRASES = [
    "현재 검색된 근거만으로는 판단하기 어렵",
    "추가 문서",
    "현장 확인",
    "확인이 필요",
    "제공된 근거에서는",
    "직접 확인할 수 없습니다",
]

OVERCONFIDENT_PATTERNS = [
    r"확정(?:됩니다|입니다|할 수 있습니다)",
    r"반드시",
    r"이미 .*완료",
    r"측정(?:값| 결과).*\\d",
    r"\\d+(?:\\.\\d+)?\\s?(?:kPa|bar|℃|도|%)",
]


@dataclass(frozen=True)
class GenerationConfig:
    dataset_path: Path
    prompt_path: Path
    output_path: Path
    prompt_version: str
    model_name: str
    temperature: float
    timeout_seconds: int
    max_retries: int
    input_cost_per_1m_tokens: float | None
    output_cost_per_1m_tokens: float | None
    pricing_source: str | None
    dataset_status: str
    result_level: str
    official_benchmark: bool
    retrieval_backend: str
    top_k: int


def resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def load_dotenv(dotenv_path: str | Path = ".env") -> None:
    path = resolve_repo_path(dotenv_path)
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("${") and value.endswith("}"):
        return resolve_env_expression(value)
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip('"').strip("'")


def load_simple_yaml(path: str | Path) -> dict[str, Any]:
    """Parse the small config shape used by this runner.

    This avoids adding a PyYAML dependency only for evaluation scaffolding.
    Nested lists of maps are supported for the config fields used here.
    """

    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[Any] | None = None
    current_item: dict[str, Any] | None = None
    parent_stack: list[str] = []

    for raw in resolve_repo_path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line.endswith(":"):
            current_key = line[:-1]
            result[current_key] = {}
            parent_stack = [current_key]
            current_list = None
            current_item = None
            continue
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = _parse_scalar(value)
            current_key = None
            current_list = None
            current_item = None
            parent_stack = []
            continue
        if indent == 2 and line.endswith(":"):
            parent = parent_stack[0] if parent_stack else current_key
            if parent is None:
                continue
            key = line[:-1]
            result.setdefault(parent, {})[key] = []
            parent_stack = [parent, key]
            current_list = result[parent][key]
            current_item = None
            continue
        if indent == 2 and line.startswith("- "):
            if current_key is None:
                continue
            if not isinstance(result.get(current_key), list):
                result[current_key] = []
            current_list = result[current_key]
            payload = line[2:]
            if ":" in payload:
                key, value = payload.split(":", 1)
                current_item = {key.strip(): _parse_scalar(value)}
                current_list.append(current_item)
            else:
                current_list.append(_parse_scalar(payload))
                current_item = None
            continue
        if indent == 4 and line.startswith("- "):
            parent = parent_stack[0] if parent_stack else current_key
            child = parent_stack[1] if len(parent_stack) > 1 else None
            if parent and child:
                result.setdefault(parent, {}).setdefault(child, []).append(_parse_scalar(line[2:]))
            continue
        if indent >= 4 and current_item is not None and ":" in line:
            key, value = line.split(":", 1)
            current_item[key.strip()] = _parse_scalar(value)
            continue

    return result


def resolve_env_expression(value: str) -> str:
    """Resolve limited ${VAR:-fallback} expressions used in the config."""

    def resolve(expr: str) -> str:
        if ":-" in expr:
            key, fallback = expr.split(":-", 1)
            env_value = os.environ.get(key)
            if env_value:
                return env_value
            if fallback.startswith("${") and fallback.endswith("}"):
                return resolve(fallback[2:-1])
            return fallback
        return os.environ.get(expr, "")

    return resolve(value[2:-1])


def load_generation_config(path: str | Path = DEFAULT_CONFIG_PATH) -> GenerationConfig:
    load_dotenv()
    raw = load_simple_yaml(path)
    return GenerationConfig(
        dataset_path=resolve_repo_path(raw["dataset_path"]),
        prompt_path=resolve_repo_path(raw["prompt_path"]),
        output_path=resolve_repo_path(raw["output_path"]),
        prompt_version=str(raw.get("prompt_version", PROMPT_VERSION)),
        model_name=str(raw.get("model_name") or os.environ.get("HEATGRID_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.4-mini"),
        temperature=float(raw.get("temperature", 0)),
        timeout_seconds=int(raw.get("timeout_seconds", 60)),
        max_retries=int(raw.get("max_retries", 2)),
        input_cost_per_1m_tokens=None if raw.get("input_cost_per_1m_tokens") is None else float(raw["input_cost_per_1m_tokens"]),
        output_cost_per_1m_tokens=None if raw.get("output_cost_per_1m_tokens") is None else float(raw["output_cost_per_1m_tokens"]),
        pricing_source=None if raw.get("pricing_source") is None else str(raw["pricing_source"]),
        dataset_status=str(raw.get("dataset_status", "draft")),
        result_level=str(raw.get("result_level", "reference")),
        official_benchmark=bool(raw.get("official_benchmark", False)),
        retrieval_backend=str(raw.get("retrieval_backend", "jsonl")),
        top_k=int(raw.get("top_k", 5)),
    )


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in resolve_repo_path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: str | Path, records: list[dict[str, Any]], append: bool = False) -> None:
    target = resolve_repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def select_pilot_cases(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], str]]:
    criteria = [
        ("hit_keyword", lambda r: r.get("answerable") is True and r.get("retrieval_hit_at_5") is True and r.get("query_type") == "keyword_match"),
        ("hit_semantic", lambda r: r.get("answerable") is True and r.get("retrieval_hit_at_5") is True and r.get("query_type") == "semantic_paraphrase"),
        ("miss_keyword", lambda r: r.get("answerable") is True and r.get("retrieval_hit_at_5") is False and r.get("query_type") == "keyword_match"),
        ("miss_semantic", lambda r: r.get("answerable") is True and r.get("retrieval_hit_at_5") is False and r.get("query_type") == "semantic_paraphrase"),
        ("unanswerable", lambda r: r.get("answerable") is False),
    ]
    selected: list[tuple[str, dict[str, Any], str]] = []
    used: set[str] = set()
    for name, predicate in criteria:
        matches = [row for row in rows if predicate(row) and row.get("case_id") not in used]
        if not matches:
            continue
        row = matches[0]
        used.add(row["case_id"])
        selected.append((name, row, pilot_reason(name, row)))
    return selected


def pilot_reason(name: str, row: dict[str, Any]) -> str:
    if name == "hit_keyword":
        return "Retrieval Hit + keyword_match 대표 case"
    if name == "hit_semantic":
        return "Retrieval Hit + semantic_paraphrase 대표 case"
    if name == "miss_keyword":
        return "Retrieval Miss + keyword_match 대표 case"
    if name == "miss_semantic":
        return "Retrieval Miss + semantic_paraphrase 대표 case"
    return "answerable=false 대표 case"


def build_generation_input(row: dict[str, Any]) -> dict[str, Any]:
    contexts = []
    for ctx in row.get("retrieved_contexts") or []:
        contexts.append({
            "rank": ctx.get("rank"),
            "chunk_id": ctx.get("chunk_id"),
            "document_title": ctx.get("document_title"),
            "section_title": ctx.get("section_title"),
            "rag_role": ctx.get("rag_role"),
            "score": ctx.get("score"),
            "text": ctx.get("text"),
        })

    return {
        "case_id": row.get("case_id"),
        "query": row.get("query"),
        "metadata": {
            "category": row.get("category"),
            "query_intent": row.get("query_intent"),
            "query_type": row.get("query_type"),
            "difficulty": row.get("difficulty"),
            "answerable": row.get("answerable"),
            "retrieval_hit_at_5": row.get("retrieval_hit_at_5"),
        },
        "retrieved_contexts": contexts,
        "safety_rules": [
            "답변은 한국어로 작성한다.",
            "검색 근거에 없는 고장 확정, 수치, 현장 확인 결과, 작업 완료를 생성하지 않는다.",
            "근거가 부족하면 판단을 유보하고 추가 문서 또는 현장 확인 필요성을 말한다.",
            "cited_chunk_ids에는 retrieved_contexts의 chunk_id만 사용한다.",
            "Retrieval Miss에서는 질문의 핵심 답변을 직접 뒷받침하지 못하는 chunk를 citation으로 쓰지 않는다.",
            "Retrieval Miss에서 직접 근거가 없으면 cited_chunk_ids를 빈 배열로 둔다.",
            "answerable=false에서는 원칙적으로 cited_chunk_ids를 빈 배열로 둔다.",
        ],
    }


def validate_generation_input(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    serialized = json.dumps(payload, ensure_ascii=False)
    for field in FORBIDDEN_INPUT_FIELDS:
        if field in serialized:
            warnings.append(f"forbidden_input_field_present:{field}")
    if not payload.get("query"):
        warnings.append("missing_query")
    if not isinstance(payload.get("retrieved_contexts"), list):
        warnings.append("retrieved_contexts_not_list")
    return warnings


def build_model_messages(prompt: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]


def parse_model_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\\s*", "", cleaned)
        cleaned = re.sub(r"\\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"json_parse_error:{exc}"
    if not isinstance(parsed, dict):
        return None, "json_not_object"
    return parsed, None


def validate_generation_output(row: dict[str, Any], output: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    answer = output.get("generated_answer")
    cited = output.get("cited_chunk_ids")
    retrieved_ids = {ctx.get("chunk_id") for ctx in row.get("retrieved_contexts") or [] if ctx.get("chunk_id")}

    if not isinstance(answer, str) or not answer.strip():
        warnings.append("generated_answer_empty")
    if not isinstance(cited, list):
        warnings.append("cited_chunk_ids_not_list")
        cited = []

    for cid in cited:
        if not isinstance(cid, str):
            warnings.append("citation_id_not_string")
            continue
        if cid not in retrieved_ids:
            warnings.append(f"citation_not_in_retrieved:{cid}")
        if cid.startswith("doc_") or cid.endswith(".pdf") or " " in cid:
            warnings.append(f"citation_looks_like_document_id:{cid}")

    if answer:
        forbidden_tokens = [
            "expected_answer_points",
            "relevant_chunk_ids",
            "partially_relevant_chunk_ids",
            "forbidden_claims",
            "human_scores",
            "automated_scores",
            "label_status",
        ]
        for token in forbidden_tokens:
            if token in answer:
                warnings.append(f"forbidden_label_leaked_in_answer:{token}")

    if row.get("retrieval_hit_at_5") is False and answer:
        if cited:
            warnings.append("retrieval_miss_non_empty_citations_require_directness_review")
        if not any(phrase in answer for phrase in CAUTION_PHRASES):
            warnings.append("retrieval_miss_without_required_abstention_phrase")
        for pattern in OVERCONFIDENT_PATTERNS:
            if re.search(pattern, answer):
                warnings.append(f"retrieval_miss_overconfident_pattern:{pattern}")

    if row.get("answerable") is False and answer:
        if cited:
            warnings.append("unanswerable_non_empty_citations_require_direct_unavailability_support")
        if not any(phrase in answer for phrase in CAUTION_PHRASES):
            warnings.append("unanswerable_without_abstention_phrase")

    return warnings


def enforce_citation_policy(row: dict[str, Any], cited_chunk_ids: list[str] | None) -> tuple[list[str], list[str]]:
    """Apply conservative citation normalization before saving results.

    Semantic directness is ultimately a human-review question. For Retrieval
    Miss and answerable=false rows, this runner therefore chooses the safer
    policy: do not preserve model-suggested citations unless a later human
    review explicitly restores them.
    """

    cited = list(cited_chunk_ids or [])
    warnings: list[str] = []
    if row.get("answerable") is False and cited:
        warnings.append("unanswerable_citations_cleared_by_policy")
        return [], warnings
    if row.get("retrieval_hit_at_5") is False and cited:
        warnings.append("retrieval_miss_citations_cleared_by_policy")
        return [], warnings
    return cited, warnings


def estimate_cost_usd(
    input_tokens: int | None,
    output_tokens: int | None,
    config: GenerationConfig,
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    if config.input_cost_per_1m_tokens is None or config.output_cost_per_1m_tokens is None:
        return None
    return (
        (input_tokens / 1_000_000) * config.input_cost_per_1m_tokens
        + (output_tokens / 1_000_000) * config.output_cost_per_1m_tokens
    )


def make_result_record(
    row: dict[str, Any],
    generated_answer: str | None,
    cited_chunk_ids: list[str] | None,
    config: GenerationConfig,
    warnings: list[str],
    error: str | None,
    usage: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    usage = usage or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    return {
        "case_id": row.get("case_id"),
        "query": row.get("query"),
        "generated_answer": generated_answer,
        "cited_chunk_ids": cited_chunk_ids or [],
        "generation_metadata": {
            "dataset_status": config.dataset_status,
            "result_level": config.result_level,
            "official_benchmark": config.official_benchmark,
            "model_name": config.model_name,
            "prompt_version": config.prompt_version,
            "temperature": config.temperature,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "retrieval_backend": config.retrieval_backend,
            "top_k": config.top_k,
            "run_id": run_id or str(uuid.uuid4()),
            "input_context_count": len(row.get("retrieved_contexts") or []),
            "retrieval_hit_at_5": row.get("retrieval_hit_at_5"),
            "answerable": row.get("answerable"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimate_cost_usd(input_tokens, output_tokens, config),
            "pricing_source": config.pricing_source,
        },
        "quality_tracking": {
            "retrieval_quality_score": None,
            "rag_answer_quality_score": None,
            "quality_status": "pending_evaluation",
            "failure_categories": [],
            "recommended_action": None,
            "attempt": 1,
            "provisional_threshold": 60,
            "threshold_status": "calibration_required",
            "failure_category_enum": [
                "rag_retrieval_issue",
                "rag_interpretation_issue",
                "insufficient_evidence",
                "citation_issue",
                "hallucination_issue",
                "unanswerable_handling_issue",
            ],
        },
        "warnings": warnings,
        "error": error,
    }
