"""Utilities for HeatGrid LLM Judge evaluation.

This module intentionally stays under rag_evaluation/ and does not import
production RAG or Agent code. It prepares Judge-only inputs and validates the
semantic evaluation output shape.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
JUDGE_PROMPT_VERSION = "llm-judge-v1.0-draft"
DEFAULT_JUDGE_MODEL = "gpt-5.4-mini"

GENERATION_PATH = Path("rag_evaluation/results/answer_generation_all.jsonl")
DATASET_PATH = Path("rag_evaluation/answer_evaluation/answer_eval.draft.jsonl")
RETRIEVAL_PATH = Path("rag_evaluation/results/real_retrieval_results.jsonl")
AUTOMATIC_EVAL_PATH = Path("rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl")
PROMPT_PATH = Path("rag_evaluation/llm_judge/llm_judge_prompt.md")
SCHEMA_PATH = Path("rag_evaluation/llm_judge/llm_judge.schema.json")
RESULTS_PATH = Path("rag_evaluation/llm_judge/llm_judge_results.jsonl")
SUMMARY_PATH = Path("rag_evaluation/llm_judge/llm_judge_summary.json")
VALIDATION_PATH = Path("rag_evaluation/validation/LLM_JUDGE_VALIDATION.md")

SCORE_FIELDS = [
    "faithfulness",
    "operational_usefulness",
    "citation_accuracy_semantic",
    "answer_relevance",
]

ENUMS = {
    "hallucination_severity": {"NONE", "MINOR", "MAJOR", "CRITICAL"},
    "overall_recommendation": {"PASS", "REVISE", "FAIL"},
    "recommendation_criteria_status": {"calibration_required"},
    "judge_confidence": {"HIGH", "MEDIUM", "LOW"},
}

REQUIRED_FIELDS = [
    "case_id",
    "faithfulness",
    "hallucination_severity",
    "operational_usefulness",
    "citation_accuracy_semantic",
    "answer_relevance",
    "overall_recommendation",
    "recommendation_criteria_status",
    "judge_confidence",
    "judge_comment",
    "judge_model",
    "judge_prompt_version",
    "evaluation_time",
    "usage",
]

USAGE_FIELDS = ["input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd"]


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


def get_judge_model() -> str:
    load_dotenv()
    return os.environ.get("HEATGRID_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or DEFAULT_JUDGE_MODEL


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in resolve_repo_path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    target = resolve_repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = resolve_repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def file_sha256(path: str | Path) -> str | None:
    target = resolve_repo_path(path)
    if not target.exists():
        return None
    return hashlib.sha256(target.read_bytes()).hexdigest().upper()


def build_judge_input(generated: dict[str, Any], dataset_row: dict[str, Any]) -> dict[str, Any]:
    """Build Judge input using only fields allowed for semantic evaluation."""

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


def load_eval_rows(
    generation_path: str | Path = GENERATION_PATH,
    dataset_path: str | Path = DATASET_PATH,
) -> list[dict[str, Any]]:
    generated_rows = load_jsonl(generation_path)
    dataset_by_case = {row["case_id"]: row for row in load_jsonl(dataset_path)}
    rows: list[dict[str, Any]] = []
    for generated in generated_rows:
        case_id = generated["case_id"]
        dataset_row = dataset_by_case[case_id]
        rows.append({
            "case_id": case_id,
            "judge_input": build_judge_input(generated, dataset_row),
            "dataset_metadata": {
                "category": dataset_row.get("category"),
                "query_type": dataset_row.get("query_type"),
                "query_intent": dataset_row.get("query_intent"),
                "difficulty": dataset_row.get("difficulty"),
                "answerable": dataset_row.get("answerable"),
                "retrieval_hit_at_5": dataset_row.get("retrieval_hit_at_5"),
            },
            "generation_model": (generated.get("generation_metadata") or {}).get("model_name"),
        })
    return rows


def estimate_prompt_payloads() -> list[dict[str, Any]]:
    return [row["judge_input"] for row in load_eval_rows()]


def build_model_input(prompt: str, payload: dict[str, Any]) -> str:
    return (
        "SYSTEM:\n"
        f"{prompt}\n\n"
        "USER:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def parse_model_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    cleaned = (text or "").strip()
    if not cleaned:
        return None, "empty_response"
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"json_parse_error:{exc}"
    if not isinstance(parsed, dict):
        return None, "json_not_object"
    return parsed, None


def normalize_judge_record(
    parsed: dict[str, Any],
    case_id: str,
    judge_model: str,
    usage: dict[str, Any],
    evaluation_time: str | None = None,
) -> dict[str, Any]:
    normalized = {
        "case_id": case_id,
        "faithfulness": parsed.get("faithfulness"),
        "hallucination_severity": parsed.get("hallucination_severity"),
        "operational_usefulness": parsed.get("operational_usefulness"),
        "citation_accuracy_semantic": parsed.get("citation_accuracy_semantic"),
        "answer_relevance": parsed.get("answer_relevance"),
        "overall_recommendation": parsed.get("overall_recommendation"),
        "recommendation_criteria_status": parsed.get("recommendation_criteria_status"),
        "judge_confidence": parsed.get("judge_confidence"),
        "judge_comment": parsed.get("judge_comment"),
        "judge_model": judge_model,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "evaluation_time": evaluation_time or datetime.now(timezone.utc).isoformat(),
        "usage": {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "estimated_cost_usd": None,
        },
    }
    return normalized


def validate_judge_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = set(REQUIRED_FIELDS)
    extra = sorted(set(record) - allowed)
    if extra:
        errors.append(f"unexpected_fields:{','.join(extra)}")
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing_field:{field}")

    for field in SCORE_FIELDS:
        value = record.get(field)
        if not isinstance(value, int) or value < 0 or value > 5:
            errors.append(f"score_range_violation:{field}:{value}")

    for field, allowed_values in ENUMS.items():
        if record.get(field) not in allowed_values:
            errors.append(f"enum_violation:{field}:{record.get(field)}")

    comment = record.get("judge_comment")
    if not isinstance(comment, str) or not comment.strip():
        errors.append("empty_judge_comment")

    usage = record.get("usage")
    if not isinstance(usage, dict):
        errors.append("usage_not_object")
    else:
        usage_extra = sorted(set(usage) - set(USAGE_FIELDS))
        if usage_extra:
            errors.append(f"usage_unexpected_fields:{','.join(usage_extra)}")
        for field in USAGE_FIELDS:
            if field not in usage:
                errors.append(f"usage_missing_field:{field}")
        for field in ["input_tokens", "output_tokens", "total_tokens"]:
            value = usage.get(field)
            if value is not None and (not isinstance(value, int) or value < 0):
                errors.append(f"usage_token_invalid:{field}:{value}")
        cost = usage.get("estimated_cost_usd")
        if cost is not None and not isinstance(cost, (int, float)):
            errors.append(f"usage_cost_invalid:{cost}")

    try:
        datetime.fromisoformat(str(record.get("evaluation_time")).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"evaluation_time_invalid:{record.get('evaluation_time')}")

    return errors


def distribution(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get(field))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def average(records: list[dict[str, Any]], field: str) -> float | None:
    values = [record.get(field) for record in records if isinstance(record.get(field), (int, float))]
    if not values:
        return None
    return statistics.fmean(values)


def group_records(
    records: list[dict[str, Any]],
    metadata_by_case: dict[str, dict[str, Any]],
    predicate,
) -> list[dict[str, Any]]:
    return [record for record in records if predicate(metadata_by_case.get(record["case_id"], {}))]


def group_breakdown(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(records),
        "faithfulness_average": average(records, "faithfulness"),
        "operational_usefulness_average": average(records, "operational_usefulness"),
        "citation_accuracy_semantic_average": average(records, "citation_accuracy_semantic"),
        "answer_relevance_average": average(records, "answer_relevance"),
        "overall_recommendation_distribution": distribution(records, "overall_recommendation"),
        "hallucination_distribution": distribution(records, "hallucination_severity"),
    }


def build_summary(
    records: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    retry_log: list[dict[str, Any]],
    api_call_count: int,
    validation_errors: dict[str, list[str]],
    before_hashes: dict[str, str | None],
    after_hashes: dict[str, str | None],
) -> dict[str, Any]:
    metadata_by_case = {row["case_id"]: row["dataset_metadata"] for row in eval_rows}
    expected_ids = [row["case_id"] for row in eval_rows]
    actual_ids = [record["case_id"] for record in records]
    duplicate_ids = sorted({case_id for case_id in actual_ids if actual_ids.count(case_id) > 1})
    missing_ids = sorted(set(expected_ids) - set(actual_ids))
    warning_cases = sorted({
        case_id
        for case_id, errors in validation_errors.items()
        if errors
    })

    total_input_tokens = sum((record["usage"].get("input_tokens") or 0) for record in records)
    total_output_tokens = sum((record["usage"].get("output_tokens") or 0) for record in records)
    total_tokens = sum((record["usage"].get("total_tokens") or 0) for record in records)
    estimated_costs = [record["usage"].get("estimated_cost_usd") for record in records]
    estimated_total_cost = None if any(cost is None for cost in estimated_costs) else sum(estimated_costs)

    groups = {
        "retrieval_hit": group_breakdown(group_records(records, metadata_by_case, lambda m: m.get("retrieval_hit_at_5") is True)),
        "retrieval_miss": group_breakdown(group_records(records, metadata_by_case, lambda m: m.get("retrieval_hit_at_5") is False and m.get("answerable") is True)),
        "answerable_false": group_breakdown(group_records(records, metadata_by_case, lambda m: m.get("answerable") is False)),
        "keyword_match": group_breakdown(group_records(records, metadata_by_case, lambda m: m.get("query_type") == "keyword_match")),
        "semantic_paraphrase": group_breakdown(group_records(records, metadata_by_case, lambda m: m.get("query_type") == "semantic_paraphrase")),
    }

    low_score_cases = sorted(
        [
            {
                "case_id": record["case_id"],
                "faithfulness": record["faithfulness"],
                "operational_usefulness": record["operational_usefulness"],
                "citation_accuracy_semantic": record["citation_accuracy_semantic"],
                "answer_relevance": record["answer_relevance"],
                "hallucination_severity": record["hallucination_severity"],
                "overall_recommendation": record["overall_recommendation"],
                "judge_confidence": record["judge_confidence"],
            }
            for record in records
            if record.get("overall_recommendation") != "PASS"
            or record.get("judge_confidence") == "LOW"
            or record.get("hallucination_severity") in {"MAJOR", "CRITICAL"}
            or any((record.get(field) or 0) <= 2 for field in SCORE_FIELDS)
        ],
        key=lambda item: (item["overall_recommendation"], item["case_id"]),
    )

    return {
        "total_case_count": len(expected_ids),
        "evaluated_case_count": len(records),
        "failed_case_count": len(failures),
        "failed_cases": failures,
        "warning_case_count": len(warning_cases),
        "warning_cases": warning_cases,
        "api_call_count": api_call_count,
        "retry_count": len(retry_log),
        "retry_log": retry_log,
        "jsonl_row_count": len(records),
        "duplicate_case_ids": duplicate_ids,
        "missing_case_ids": missing_ids,
        "schema_validation_error_count": sum(len(errors) for errors in validation_errors.values()),
        "schema_validation_errors": validation_errors,
        "faithfulness_average": average(records, "faithfulness"),
        "operational_usefulness_average": average(records, "operational_usefulness"),
        "citation_accuracy_semantic_average": average(records, "citation_accuracy_semantic"),
        "answer_relevance_average": average(records, "answer_relevance"),
        "hallucination_distribution": distribution(records, "hallucination_severity"),
        "overall_recommendation_distribution": distribution(records, "overall_recommendation"),
        "judge_confidence_distribution": distribution(records, "judge_confidence"),
        "retrieval_hit_breakdown": groups["retrieval_hit"],
        "retrieval_miss_breakdown": groups["retrieval_miss"],
        "answerable_false_breakdown": groups["answerable_false"],
        "query_type_breakdown": {
            "keyword_match": groups["keyword_match"],
            "semantic_paraphrase": groups["semantic_paraphrase"],
        },
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "estimated_total_cost_usd": estimated_total_cost,
        "cost_calculation_note": "estimated_total_cost_usd is null because official pricing for the configured model was not confirmed in this evaluation config.",
        "judge_model": records[0]["judge_model"] if records else get_judge_model(),
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "generation_models": sorted({row.get("generation_model") for row in eval_rows if row.get("generation_model")}),
        "judge_generation_same_model": bool(records) and len({row.get("generation_model") for row in eval_rows if row.get("generation_model")}) == 1 and records[0]["judge_model"] in {row.get("generation_model") for row in eval_rows},
        "recommendation_criteria_status": "calibration_required",
        "manual_review_priority_cases": low_score_cases,
        "input_file_hashes_before": before_hashes,
        "input_file_hashes_after": after_hashes,
        "input_hashes_unchanged": before_hashes == after_hashes,
    }


def write_validation_doc(summary: dict[str, Any], output_path: str | Path = VALIDATION_PATH) -> None:
    target = resolve_repo_path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    failed_ids = [failure.get("case_id") for failure in summary.get("failed_cases", [])]
    manual_cases = [case["case_id"] for case in summary.get("manual_review_priority_cases", [])]
    lines = [
        "# LLM Judge Validation",
        "",
        "## 실행 목적",
        "",
        "Answer Generation 28건에 대해 LLM Judge 기반 의미 평가를 수행하고, 결과 JSONL과 summary의 구조 및 집계를 검증한다.",
        "",
        "## 실행 설정",
        "",
        f"- Judge Model: `{summary.get('judge_model')}`",
        f"- Judge Prompt Version: `{summary.get('judge_prompt_version')}`",
        "- Temperature: `0`",
        f"- Generation Models: `{', '.join(summary.get('generation_models') or [])}`",
        f"- Judge와 Generation 동일 모델 여부: `{summary.get('judge_generation_same_model')}`",
        f"- Recommendation Criteria Status: `{summary.get('recommendation_criteria_status')}`",
        "",
        "## 처리 결과",
        "",
        f"- 평가 대상 case 수: `{summary.get('total_case_count')}`",
        f"- 성공 case 수: `{summary.get('evaluated_case_count')}`",
        f"- 실패 case 수: `{summary.get('failed_case_count')}`",
        f"- 실패 case_id: `{failed_ids}`",
        f"- 실제 API 호출 수: `{summary.get('api_call_count')}`",
        f"- 재시도 횟수: `{summary.get('retry_count')}`",
        "",
        "## 검증 결과",
        "",
        f"- JSONL 행 수: `{summary.get('jsonl_row_count')}`",
        f"- 중복 case_id: `{summary.get('duplicate_case_ids')}`",
        f"- 누락 case_id: `{summary.get('missing_case_ids')}`",
        f"- Schema 검증 오류 수: `{summary.get('schema_validation_error_count')}`",
        f"- 입력 파일 해시 유지: `{summary.get('input_hashes_unchanged')}`",
        "",
        "## 주요 평균",
        "",
        f"- Faithfulness 평균: `{summary.get('faithfulness_average')}`",
        f"- Operational Usefulness 평균: `{summary.get('operational_usefulness_average')}`",
        f"- Citation Accuracy Semantic 평균: `{summary.get('citation_accuracy_semantic_average')}`",
        f"- Answer Relevance 평균: `{summary.get('answer_relevance_average')}`",
        "",
        "## 분포",
        "",
        f"- Hallucination 분포: `{summary.get('hallucination_distribution')}`",
        f"- PASS/REVISE/FAIL 분포: `{summary.get('overall_recommendation_distribution')}`",
        f"- Judge Confidence 분포: `{summary.get('judge_confidence_distribution')}`",
        "",
        "## Token Usage",
        "",
        f"- Input Tokens: `{summary.get('total_input_tokens')}`",
        f"- Output Tokens: `{summary.get('total_output_tokens')}`",
        f"- Total Tokens: `{summary.get('total_tokens')}`",
        f"- Estimated Cost USD: `{summary.get('estimated_total_cost_usd')}`",
        f"- 비용 산정 비고: {summary.get('cost_calculation_note')}",
        "",
        "## Retrieval Hit/Miss 비교",
        "",
        f"- Retrieval Hit: `{summary.get('retrieval_hit_breakdown')}`",
        f"- Retrieval Miss: `{summary.get('retrieval_miss_breakdown')}`",
        f"- answerable=false: `{summary.get('answerable_false_breakdown')}`",
        f"- Query Type: `{summary.get('query_type_breakdown')}`",
        "",
        "## LLM Judge 결과의 한계",
        "",
        "- Judge와 Generation에 동일 모델 계열이 사용되어 자기평가 편향 가능성이 있다.",
        "- 현재 결과는 draft/reference dataset 기반이며 official benchmark가 아니다.",
        "- Recommendation 기준은 `calibration_required` 상태이므로 사람 검수 후 보정이 필요하다.",
        "",
        "## 사람 검수 우선 대상",
        "",
        f"- 우선 대상 case_id: `{manual_cases}`",
        "",
        "## 다음 단계 진행 가능 여부",
        "",
        "CONDITIONAL",
        "",
        "조건: 사람 검수로 낮은 점수/LOW confidence/REVISE/FAIL case를 우선 확인한 뒤 품질 점수 통합 단계로 진행한다.",
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
