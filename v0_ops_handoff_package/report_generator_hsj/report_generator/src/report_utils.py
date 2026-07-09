from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

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
    return {
        "prompt": prompt,
        "inputs": inputs,
        "output_contract": {
            "format": "json_only",
            "language": "ko",
            "no_markdown": True,
            "no_work_order_body": True,
        },
    }


def call_llm_json(prompt: str, inputs: ReportJson) -> ReportJson:
    """Interface placeholder for a future OpenAI API integration."""
    _ = build_llm_payload(prompt, inputs)
    raise NotImplementedError(
        "실제 LLM 호출은 아직 연결하지 않았습니다. mock=True로 실행하거나 llm_caller를 주입하세요."
    )


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
        help="생성된 보고서 JSON을 저장할 경로입니다.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="LLM 호출 없이 examples/*.example.json을 반환하고 schema validation을 수행합니다.",
    )
    return parser


def print_json(report: ReportJson) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))
