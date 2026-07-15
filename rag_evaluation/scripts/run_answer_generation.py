"""Run HeatGrid answer generation for draft/reference evaluation cases."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from answer_generation_utils import (
    build_generation_input,
    build_model_messages,
    load_generation_config,
    load_jsonl,
    make_result_record,
    parse_model_json,
    select_pilot_cases,
    enforce_citation_policy,
    estimate_cost_usd,
    validate_generation_input,
    validate_generation_output,
    write_jsonl,
)


def call_openai_responses(
    messages: list[dict[str, str]],
    model_name: str,
    temperature: float,
    timeout_seconds: int,
) -> tuple[str, dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    input_text = "\n\n".join(f"{message['role'].upper()}:\n{message['content']}" for message in messages)
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


def choose_rows(args: argparse.Namespace, rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], str]]:
    if args.case_id:
        matches = [row for row in rows if row.get("case_id") == args.case_id]
        if not matches:
            raise SystemExit(f"case_id not found: {args.case_id}")
        return [("case_id", matches[0], f"manual case-id rerun: {args.case_id}")]
    if args.all:
        return [("all", row, "full 28-case run") for row in rows]
    return select_pilot_cases(rows)


def dry_run(rows: list[tuple[str, dict[str, Any], str]], prompt: str) -> dict[str, Any]:
    records = []
    all_warnings: list[str] = []
    for selection_name, row, reason in rows:
        payload = build_generation_input(row)
        warnings = validate_generation_input(payload)
        messages = build_model_messages(prompt, payload)
        all_warnings.extend([f"{row.get('case_id')}:{warning}" for warning in warnings])
        records.append({
            "case_id": row.get("case_id"),
            "selection_name": selection_name,
            "selection_reason": reason,
            "query_type": row.get("query_type"),
            "answerable": row.get("answerable"),
            "retrieval_hit_at_5": row.get("retrieval_hit_at_5"),
            "input_context_count": len(row.get("retrieved_contexts") or []),
            "input_validation_warnings": warnings,
            "message_count": len(messages),
        })
    return {
        "selected_count": len(records),
        "selected_cases": records,
        "warning_count": len(all_warnings),
        "warnings": all_warnings,
    }


def generate_rows(
    rows: list[tuple[str, dict[str, Any], str]],
    prompt: str,
    config_path: str | Path,
    append: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    config = load_generation_config(config_path)
    output_records: list[dict[str, Any]] = []
    failures = 0
    citation_warning_count = 0
    target_output_path = Path(output_path) if output_path else config.output_path
    if not append:
        target_output_path = target_output_path if target_output_path.is_absolute() else Path.cwd() / target_output_path
        target_output_path.parent.mkdir(parents=True, exist_ok=True)
        target_output_path.write_text("", encoding="utf-8")

    for _, row, _ in rows:
        input_payload = build_generation_input(row)
        input_warnings = validate_generation_input(input_payload)
        messages = build_model_messages(prompt, input_payload)
        generated_answer = None
        cited_chunk_ids: list[str] = []
        error = None
        usage: dict[str, Any] = {"input_tokens": None, "output_tokens": None, "total_tokens": None}

        for attempt in range(config.max_retries + 1):
            try:
                raw_text, usage = call_openai_responses(messages, config.model_name, config.temperature, config.timeout_seconds)
                parsed, parse_error = parse_model_json(raw_text)
                if parse_error:
                    raise RuntimeError(parse_error)
                generated_answer = parsed.get("generated_answer")
                cited_chunk_ids = parsed.get("cited_chunk_ids") or []
                break
            except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                error = f"{type(exc).__name__}:{exc}"
                if attempt < config.max_retries:
                    time.sleep(1 + attempt)
                else:
                    failures += 1

        output = {
            "generated_answer": generated_answer,
            "cited_chunk_ids": cited_chunk_ids,
        }
        cited_chunk_ids, policy_warnings = enforce_citation_policy(row, cited_chunk_ids)
        output["cited_chunk_ids"] = cited_chunk_ids
        output_warnings = policy_warnings + validate_generation_output(row, output)
        citation_warning_count += len([w for w in output_warnings if w.startswith("citation_")])
        record = make_result_record(
            row=row,
            generated_answer=generated_answer,
            cited_chunk_ids=cited_chunk_ids,
            config=config,
            warnings=input_warnings + output_warnings,
            error=error,
            usage=usage,
        )
        output_records.append(record)
        write_jsonl(output_path or config.output_path, [record], append=True)

    input_tokens_total = sum((record["generation_metadata"].get("input_tokens") or 0) for record in output_records)
    output_tokens_total = sum((record["generation_metadata"].get("output_tokens") or 0) for record in output_records)
    total_tokens_total = sum((record["generation_metadata"].get("total_tokens") or 0) for record in output_records)
    estimated_costs = [record["generation_metadata"].get("estimated_cost_usd") for record in output_records]
    estimated_cost_total = None if any(cost is None for cost in estimated_costs) else sum(estimated_costs)
    return {
        "generated_count": len(output_records),
        "failure_count": failures,
        "citation_warning_count": citation_warning_count,
        "output_path": str(target_output_path),
        "input_tokens": input_tokens_total,
        "output_tokens": output_tokens_total,
        "total_tokens": total_tokens_total,
        "estimated_cost_usd": estimated_cost_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HeatGrid answer generation runner")
    parser.add_argument("--config", default="rag_evaluation/answer_generation/answer_generation_config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Validate prompt/input structure without API calls")
    parser.add_argument("--pilot", action="store_true", help="Generate the selected 5 pilot cases")
    parser.add_argument("--all", action="store_true", help="Generate all 28 cases; do not use before pilot review")
    parser.add_argument("--case-id", help="Generate one specific case")
    parser.add_argument("--append", action="store_true", help="Append to output JSONL instead of overwriting")
    parser.add_argument("--output-path", help="Override output JSONL path")
    args = parser.parse_args()

    run_mode_count = sum(bool(x) for x in [args.pilot, args.all])
    if args.case_id and args.pilot:
        raise SystemExit("Use either --pilot or --case-id, not both")
    if args.case_id and args.all:
        raise SystemExit("Use either --all or --case-id, not both")
    if args.dry_run:
        if args.pilot:
            raise SystemExit("Use --dry-run alone, with --all, or with --case-id; not with --pilot")
    elif not args.case_id and run_mode_count != 1:
        raise SystemExit("Choose exactly one mode: --dry-run, --pilot, --all, or --case-id")
    elif args.case_id and run_mode_count > 0:
        raise SystemExit("Use --case-id alone or with --dry-run only")

    config = load_generation_config(args.config)
    prompt = config.prompt_path.read_text(encoding="utf-8")
    rows = load_jsonl(config.dataset_path)
    chosen = choose_rows(args, rows)

    if args.dry_run:
        summary = dry_run(chosen, prompt)
    else:
        if args.all:
            print("WARNING: --all requested. This should only be run after pilot review.", file=sys.stderr)
        summary = generate_rows(chosen, prompt, args.config, append=args.append, output_path=args.output_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
