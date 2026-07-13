from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from jsonschema import Draft7Validator
except ImportError as exc:  # pragma: no cover - depends on local environment
    Draft7Validator = None
    JSONSCHEMA_IMPORT_ERROR = exc
else:
    JSONSCHEMA_IMPORT_ERROR = None


ReportJson = dict[str, Any]
LLMCaller = Callable[[str, ReportJson], ReportJson]

SRC_DIR = Path(__file__).resolve().parent
REPORT_GENERATOR_DIR = SRC_DIR.parent
SCHEMAS_DIR = REPORT_GENERATOR_DIR / "schemas"
PROMPTS_DIR = REPORT_GENERATOR_DIR / "prompts"
EXAMPLES_DIR = REPORT_GENERATOR_DIR / "examples"
PROJECT_ROOT = REPORT_GENERATOR_DIR.parents[1]


class ReportValidationError(ValueError):
    """Raised when generated report JSON does not satisfy its schema."""


def load_json(path: Path) -> ReportJson:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def validate_report(report: ReportJson, schema: ReportJson) -> None:
    if Draft7Validator is not None:
        validator = Draft7Validator(schema)
        errors = sorted(validator.iter_errors(report), key=lambda error: list(error.path))
        if not errors:
            return

        messages = []
        for error in errors:
            path = "$"
            if error.path:
                path = "$." + ".".join(str(part) for part in error.path)
            messages.append(f"{path}: {error.message}")
        raise ReportValidationError("\n".join(messages))

    errors = _validate_report_fallback(report, schema)
    if errors:
        raise ReportValidationError("\n".join(errors))


def _is_object(value: Any) -> bool:
    return isinstance(value, dict)


def _has_type(value: Any, expected_type: str) -> bool:
    if expected_type == "null":
        return value is None
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    return True


def _validate_report_fallback(value: Any, schema: ReportJson, path: str = "$") -> list[str]:
    """Small draft-07 subset validator for local mock runs when jsonschema is unavailable."""
    errors: list[str] = []

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}")

    if "type" in schema:
        expected_types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_has_type(value, expected_type) for expected_type in expected_types):
            errors.append(f"{path}: expected type {' or '.join(expected_types)}")
            return errors

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: lower than minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: greater than maximum {schema['maximum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(_validate_report_fallback(item, schema["items"], f"{path}[{index}]"))

    if _is_object(value):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property {key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key}")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(_validate_report_fallback(value[key], child_schema, f"{path}.{key}"))

    return errors


def build_llm_payload(prompt: str, inputs: ReportJson) -> ReportJson:
    public_inputs = {key: value for key, value in inputs.items() if key != "_output_schema"}
    return {
        "prompt": prompt,
        "inputs": public_inputs,
        "output_contract": {
            "format": "json_only",
            "language": "ko",
            "no_markdown": True,
            "no_work_order_body": True,
        },
    }


def load_project_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def extract_json_object(text: str) -> ReportJson:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ReportValidationError("LLM 응답에서 JSON 객체를 찾지 못했습니다.")
    return json.loads(stripped[start : end + 1])


def call_llm_json(prompt: str, inputs: ReportJson) -> ReportJson:
    load_project_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 .env 또는 환경변수에 없습니다.")

    model = (
        os.getenv("OPENAI_MODEL", "").strip()
        or os.getenv("HEATGRID_OPENAI_MODEL", "").strip()
        or "gpt-5.4-mini"
    )
    return call_llm_json_with_config(
        prompt,
        inputs,
        api_key=api_key,
        model=model,
    )


def call_llm_json_with_config(
    prompt: str,
    inputs: ReportJson,
    *,
    api_key: str,
    model: str,
) -> ReportJson:
    system = "\n".join(
        [
            "You are a Korean district-heating report generator.",
            "Return only one valid JSON object. Do not wrap it in Markdown.",
            "The JSON must match the report schema described by the prompt.",
            "Write all user-facing report sentences in natural Korean for operations staff.",
            "Generate a substantive operational report, not a short alert. Prefer complete explanatory sentences over terse labels.",
            "Follow a practical incident/maintenance report flow: executive summary, asset and time context, impact assessment, detection evidence, operating context, suspected causes, immediate actions, follow-up monitoring, and traceable references.",
            "When the schema has situation_summary.summary, write 4 to 6 Korean sentences covering severity, affected asset, analysis window, observed signals, mapped site or missing site context, weather/load context if available, and uncertainty.",
            "When the schema has situation_summary.current_status, write 2 to 4 Korean sentences explaining what is known now, what is not confirmed, what has not yet been field-verified, and what should be checked first.",
            "When the schema has situation_summary.impact_summary, write 2 to 3 Korean sentences about possible operational impact such as heat supply stability, customer comfort, hot-water quality, energy efficiency, monitoring burden, and escalation risk.",
            "When the schema has daily_summary, write a daily operations summary for shift handover. Counts must be based on the provided priority_cards input, not invented.",
            "When the schema has next_shift_handover, make it concrete enough for the next shift operator to act on immediately.",
            "When the schema has major_patterns, include only repeated or clustered patterns supported by provided cards. Do not overstate a single signal as a recurring pattern.",
            "When the schema has key_evidence, structure evidence like detection evidence: signal, observed value or qualitative pattern, operational interpretation, and confidence.",
            "When the schema has risk_analysis.risk_summary and operational_impact, write 3 to 5 Korean sentences each. Explain risk pathways, affected operating functions, and why this needs attention while avoiding confirmed-cause wording.",
            "When the schema has risk_analysis.monitoring_points, provide 4 to 6 concrete monitoring points.",
            "When the schema has suspected_causes, provide 2 to 4 cautious candidates only when supported by evidence. Each rationale should explain why it is plausible and what would confirm or rule it out.",
            "When the schema has recommended_actions, provide 4 to 6 concrete actions in priority order. Each action should include an executable check, the reason for doing it, and should set owner_hint and urgency.",
            "When the schema has recommended_daily_actions, provide 3 to 6 daily-level actions in priority order. Each action should include a target, reason, and owner_hint.",
            "When the schema has recommended_actions.expected_outcome, state the expected confirmation, exclusion, or operational decision from the action when the schema allows it.",
            "For work_order_summary, keep it as metadata only, but make the summary explain whether a work order is not created, drafted, or should be considered based on urgency.",
            "For work_order_overview, keep it as metadata only. Never draft full work order text.",
            "For operator_note.note, write 2 to 4 Korean sentences summarizing the operator takeaway, uncertainty limits, and what should be handed over to the next shift.",
            "For operator_memo.memo, write 2 to 4 Korean sentences summarizing the daily operator takeaway and handover focus.",
            "For evidence_references, use readable Korean titles for operator-visible references and reserve technical ids for source_id only.",
            "Round user-visible score values to at most two decimal places.",
            "Do not start recommended_actions.action with numbering, bullets, or prefixes such as '1.' because the UI may number actions separately.",
            "Avoid raw separators such as '|', '\\', '/', bracketed code labels, or pipe-joined sensor lists in user-facing prose. Rewrite them as natural Korean lists.",
            "Do not expose implementation terms such as RAG, chunk, pgvector, API key, raw endpoint, tool function names, or variable names in narrative sections.",
            "Do not expose internal model or engineering terms in any user-facing title, summary, action, caution, or evidence title.",
            "Forbidden terms in user-facing strings include: Priority Card, current_best, m1_specialist, M1 Specialist, fault_group, leakage_water_loss, RAG, retrieval, chunk, pgvector, get_ops_evidence, get_external_context, KMA API, APIHub, model, 모델, 전문 모델, Urgent, High, Medium, Low.",
            "Schema enum values may remain Urgent/High/Medium/Low where required, but all Korean narrative fields must use 긴급/높음/보통/낮음.",
            "Use Korean operator terms instead: 위험도 산정 결과, 운영 근거, 의심 유형, 기술 점검 기준, 기상 부하 조건.",
            "You may include technical source ids only inside evidence_references.source_id or uri when the schema requires traceability.",
            "External weather is operating-load context only. Never treat it as confirmed fault cause.",
            "Retrieved documents are supporting references only. Never override the official priority score, priority level, counts, or diagnostic evidence.",
            "Do not invent missing values. Use null or cautious wording when evidence is incomplete.",
        ]
    )
    output_schema = inputs.get("_output_schema") if isinstance(inputs.get("_output_schema"), dict) else None
    user = build_llm_payload(prompt, inputs)
    text_format: dict[str, Any]
    if output_schema:
        text_format = {
            "type": "json_schema",
            "name": "heatgrid_report",
            "schema": output_schema,
            "strict": False,
        }
    else:
        text_format = {"type": "json_object"}
    body = json.dumps(
        {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "text": {"format": text_format},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

    text = payload.get("output_text")
    if not text:
        parts: list[str] = []
        for item in payload.get("output", []) or []:
            for content in item.get("content", []) or []:
                if isinstance(content, dict):
                    parts.append(str(content.get("text") or ""))
        text = "".join(parts)
    return extract_json_object(text or "")


def ensure_no_work_order_body(report: ReportJson) -> None:
    blocked_keys = {
        "work_order_body",
        "work_order_text",
        "email_body",
        "field_instruction_body",
    }

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in blocked_keys:
                    raise ReportValidationError(f"{path}.{key}: 작업지시서 전문 필드는 허용되지 않습니다.")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(report, "$")


def load_input_or_empty(input_path: str | None) -> ReportJson:
    if input_path is None:
        return {}
    return load_json(Path(input_path))


def write_output_if_requested(report: ReportJson, output_path: str | None) -> None:
    if output_path is None:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_cli_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--input",
        dest="input_path",
        help="생성 입력 JSON 경로입니다. mock mode에서는 생략할 수 있습니다.",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        help="생성한 보고서 JSON 또는 보강 입력 JSON을 저장할 경로입니다.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="LLM 호출 없이 examples/*.example.json을 반환하고 schema validation을 수행합니다.",
    )
    parser.add_argument(
        "--with-rag",
        action="store_true",
        help="입력 JSON에 RAG/외부 문맥을 보강한 뒤 보고서를 생성합니다.",
    )
    parser.add_argument(
        "--rag-url",
        dest="rag_url",
        help="RAG 서버 URL입니다. 생략하면 HEATGRID_RAG_URL 또는 로컬 RagSearcher를 사용합니다.",
    )
    parser.add_argument(
        "--rag-top-k",
        dest="rag_top_k",
        type=int,
        default=5,
        help="RAG 검색에서 가져올 chunk 개수입니다.",
    )
    parser.add_argument(
        "--force-rag",
        action="store_true",
        help="입력에 기존 external_context/rag_evidence가 있어도 다시 보강합니다.",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="보고서를 생성하지 않고 RAG로 보강된 입력 JSON만 출력합니다.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="stdout 출력 없이 --output 파일만 저장합니다.",
    )
    return parser


def print_json(report: ReportJson) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
