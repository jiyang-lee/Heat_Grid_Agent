"""Run HeatGrid LLM Judge semantic answer evaluation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_judge_utils import (
    AUTOMATIC_EVAL_PATH,
    DATASET_PATH,
    GENERATION_PATH,
    JUDGE_PROMPT_VERSION,
    PROMPT_PATH,
    RESULTS_PATH,
    RETRIEVAL_PATH,
    SUMMARY_PATH,
    build_model_input,
    build_summary,
    estimate_prompt_payloads,
    file_sha256,
    get_judge_model,
    load_dotenv,
    load_eval_rows,
    normalize_judge_record,
    parse_model_json,
    resolve_repo_path,
    validate_judge_record,
    write_json,
    write_jsonl,
    write_validation_doc,
)


def call_openai_responses(input_text: str, model_name: str, temperature: float, timeout_seconds: int) -> tuple[str, dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    payload: dict[str, Any] = {
        "model": model_name,
        "input": input_text,
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    normalized_usage = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }

    if isinstance(body.get("output_text"), str):
        return body["output_text"], normalized_usage

    texts: list[str] = []
    for item in body.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                texts.append(content["text"])
    if texts:
        return "\n".join(texts), normalized_usage

    raise RuntimeError("No text output returned by OpenAI Responses API")


def run_plan_only() -> dict[str, Any]:
    payloads = estimate_prompt_payloads()
    return {
        "planned_case_count": len(payloads),
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "api_calls_per_full_run": len(payloads),
        "api_execution_enabled": False,
    }


def run_judge(
    overwrite: bool,
    max_retries: int,
    timeout_seconds: int,
    temperature: float,
) -> dict[str, Any]:
    results_path = resolve_repo_path(RESULTS_PATH)
    summary_path = resolve_repo_path(SUMMARY_PATH)
    if (results_path.exists() or summary_path.exists()) and not overwrite:
        raise SystemExit(
            "LLM Judge result files already exist. Re-run with --overwrite only after confirming replacement is intended."
        )

    load_dotenv()
    judge_model = get_judge_model()
    prompt = resolve_repo_path(PROMPT_PATH).read_text(encoding="utf-8")
    eval_rows = load_eval_rows()
    before_hashes = {
        "answer_generation_all.jsonl": file_sha256(GENERATION_PATH),
        "answer_eval.draft.jsonl": file_sha256(DATASET_PATH),
        "real_retrieval_results.jsonl": file_sha256(RETRIEVAL_PATH),
        "automatic_answer_eval_results.jsonl": file_sha256(AUTOMATIC_EVAL_PATH),
    }

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    retry_log: list[dict[str, Any]] = []
    raw_response_issues: list[dict[str, Any]] = []
    api_call_count = 0

    for index, row in enumerate(eval_rows, start=1):
        case_id = row["case_id"]
        input_text = build_model_input(prompt, row["judge_input"])
        parsed: dict[str, Any] | None = None
        usage: dict[str, Any] = {"input_tokens": None, "output_tokens": None, "total_tokens": None}
        error: str | None = None

        print(f"[{index}/{len(eval_rows)}] judging {case_id}", file=sys.stderr)
        for attempt in range(max_retries + 1):
            if attempt > 0:
                retry_log.append({"case_id": case_id, "attempt": attempt + 1, "previous_error": error})
                time.sleep(1 + attempt)
            try:
                api_call_count += 1
                raw_text, usage = call_openai_responses(input_text, judge_model, temperature, timeout_seconds)
                if not raw_text or not raw_text.strip():
                    raw_response_issues.append({"case_id": case_id, "issue": "empty_response"})
                parsed, parse_error = parse_model_json(raw_text)
                if parse_error:
                    error = parse_error
                    if "empty_response" in parse_error:
                        raw_response_issues.append({"case_id": case_id, "issue": parse_error})
                    raise RuntimeError(parse_error)
                break
            except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                error = f"{type(exc).__name__}:{exc}"
                parsed = None
                if attempt >= max_retries:
                    failures.append({"case_id": case_id, "error": error})

        if parsed is None:
            continue

        record = normalize_judge_record(
            parsed=parsed,
            case_id=case_id,
            judge_model=judge_model,
            usage=usage,
            evaluation_time=datetime.now(timezone.utc).isoformat(),
        )
        records.append(record)

    validation_errors = {record["case_id"]: validate_judge_record(record) for record in records}
    after_hashes = {
        "answer_generation_all.jsonl": file_sha256(GENERATION_PATH),
        "answer_eval.draft.jsonl": file_sha256(DATASET_PATH),
        "real_retrieval_results.jsonl": file_sha256(RETRIEVAL_PATH),
        "automatic_answer_eval_results.jsonl": file_sha256(AUTOMATIC_EVAL_PATH),
    }
    summary = build_summary(
        records=records,
        eval_rows=eval_rows,
        failures=failures,
        retry_log=retry_log,
        api_call_count=api_call_count,
        validation_errors=validation_errors,
        before_hashes=before_hashes,
        after_hashes=after_hashes,
    )
    summary["raw_response_issue_count"] = len(raw_response_issues)
    summary["raw_response_issues"] = raw_response_issues
    summary["execution_time"] = datetime.now(timezone.utc).isoformat()

    write_jsonl(RESULTS_PATH, records)
    write_json(SUMMARY_PATH, summary)
    write_validation_doc(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="HeatGrid LLM Judge evaluation runner")
    parser.add_argument("--plan-only", action="store_true", help="Show planned Judge payload count without API calls")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Judge result files")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    if args.plan_only:
        summary = run_plan_only()
    else:
        summary = run_judge(
            overwrite=args.overwrite,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
            temperature=args.temperature,
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
