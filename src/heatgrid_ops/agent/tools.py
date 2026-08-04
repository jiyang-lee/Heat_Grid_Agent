from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import orjson
from langchain_core.tools import BaseTool, tool

from evidence_repository import filter_ops_evidence
from heatgrid_ops.agent.helpers import card_id_from_input, to_json
from heatgrid_ops.reports.anomaly import write_anomaly_report_json
from heatgrid_ops.reports.daily import write_daily_report_json
from schemas import JsonValue

REPORTS_URI_PREFIX: Final = "output/ops_agent/reports"
MAX_REFERENCE_CHUNKS: Final = 3
MAX_REFERENCE_TEXT_CHARS: Final = 1_600
ALL_AGENT_TOOL_NAMES: Final = (
    "get_ops_evidence",
    "get_external_context",
    "write_anomaly_report",
    "write_daily_report",
)


@dataclass(frozen=True, slots=True)
class ReportToolPayloadError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


def make_operational_tools(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> list[BaseTool]:
    return [
        make_ops_evidence_tool(source_input),
        make_external_context_tool(source_input, external_context),
    ]


def make_ops_evidence_tool(source_input: dict[str, JsonValue]) -> BaseTool:
    @tool(description="Return card, raw sensor, and ML model evidence from PostgreSQL.")
    def get_ops_evidence(card_id: str, sections: list[str] | None = None) -> str:
        return to_json(filter_ops_evidence(source_input, card_id, sections))

    return get_ops_evidence


def make_external_context_tool(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> BaseTool:
    @tool(description="Return mapped site, weather, and operating reference context.")
    def get_external_context(card_id: str) -> str:
        if card_id != card_id_from_input(source_input):
            return to_json({"error": "card_id를 찾을 수 없습니다."})
        return to_json(
            _compact_external_context(
                external_context or {"status": "unavailable"}
            )
        )

    return get_external_context


def _compact_external_context(
    external_context: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    compact = {
        key: value
        for key, value in external_context.items()
        if key not in {"retrieval", "references"}
    }
    retrieval = external_context.get("retrieval")
    if not isinstance(retrieval, dict):
        return compact

    compact_retrieval = {
        key: retrieval[key]
        for key in ("status", "source", "backend", "top_k")
        if key in retrieval
    }
    chunks = retrieval.get("chunks")
    if isinstance(chunks, list):
        compact_retrieval["chunks"] = [
            _compact_reference_chunk(chunk)
            for chunk in chunks[:MAX_REFERENCE_CHUNKS]
            if isinstance(chunk, dict)
        ]
    compact["retrieval"] = compact_retrieval
    return compact


def _compact_reference_chunk(chunk: dict[str, JsonValue]) -> dict[str, JsonValue]:
    compact = {
        key: chunk[key]
        for key in (
            "chunk_id",
            "document_title",
            "section_title",
            "source_file",
            "page_start",
            "page_end",
            "download_url",
            "fault_type",
            "risk_level",
            "score",
        )
        if key in chunk
    }
    text = chunk.get("text")
    if isinstance(text, str):
        compact["text"] = text[:MAX_REFERENCE_TEXT_CHARS]
    provenance = chunk.get("provenance")
    if isinstance(provenance, dict):
        compact["provenance"] = provenance
    return compact


def make_anomaly_report_tool(
    output_root: Path | None = None,
    *,
    mock: bool = False,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
) -> BaseTool:
    @tool(description="Write an anomaly report JSON artifact for an agent run.")
    def write_anomaly_report(payload_json: str) -> str:
        payload = _report_tool_payload(payload_json)
        run_id = _required_string(payload, "run_id")
        report_path = _report_path(output_root, run_id, "anomaly_report.json")
        with _temporary_report_env(openai_api_key, openai_model):
            report = write_anomaly_report_json(
                _anomaly_input_from_payload(payload),
                report_path,
                mock=mock,
            )
        return to_json(
            {
                "kind": "anomaly_report",
                "name": "anomaly_report.json",
                "uri": _report_uri(run_id, "anomaly_report.json"),
                "report_type": _report_type(report),
            }
        )

    return write_anomaly_report


def make_daily_report_tool(
    output_root: Path | None = None,
    *,
    mock: bool = False,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
) -> BaseTool:
    @tool(description="Write a daily operations report JSON artifact.")
    def write_daily_report(payload_json: str) -> str:
        payload = _report_tool_payload(payload_json)
        run_id = _required_string(payload, "run_id")
        report_path = _report_path(output_root, run_id, "daily_report.json")
        with _temporary_report_env(openai_api_key, openai_model):
            report = write_daily_report_json(
                _daily_input_from_payload(payload),
                report_path,
                mock=mock,
            )
        return to_json(
            {
                "kind": "daily_report",
                "name": "daily_report.json",
                "uri": _report_uri(run_id, "daily_report.json"),
                "report_type": _report_type(report),
            }
        )

    return write_daily_report


def _anomaly_input_from_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    source_input = _required_mapping(payload, "source_input")
    return {
        "ops_evidence": source_input,
        "external_context": _required_mapping(payload, "external_context"),
        "agent_output": _required_mapping(payload, "ops_output"),
        "report_context": {
            "agent_run_id": _required_string(payload, "run_id"),
            "source_card_id": _required_string(payload, "card_id"),
        },
    }


def _daily_input_from_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    source_input = _required_mapping(payload, "source_input")
    return {
        "report_context": {
            "agent_run_id": _required_string(payload, "run_id"),
            "source_card_id": _required_string(payload, "card_id"),
        },
        "priority_cards": [_priority_card(source_input)],
        "agent_outputs": [_required_mapping(payload, "ops_output")],
        "ops_evidence_list": [source_input],
        "external_context_list": [_required_mapping(payload, "external_context")],
        "rag_evidence": [],
        "work_order_summaries": [],
        "previous_operator_memo": None,
    }


def _priority_card(source_input: dict[str, JsonValue]) -> dict[str, JsonValue]:
    priority_context = source_input.get("priority_context")
    if not isinstance(priority_context, dict):
        return {}
    card = priority_context.get("card")
    return card if isinstance(card, dict) else {}


def _report_tool_payload(payload_json: str) -> dict[str, JsonValue]:
    payload = orjson.loads(payload_json)
    if not isinstance(payload, dict):
        raise ReportToolPayloadError("report tool payload must be a JSON object")
    return payload


def _required_mapping(
    payload: dict[str, JsonValue],
    field_name: str,
) -> dict[str, JsonValue]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ReportToolPayloadError(f"{field_name} must be a JSON object")
    return value


def _required_string(payload: dict[str, JsonValue], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ReportToolPayloadError(f"{field_name} must be a non-empty string")
    return value


def _report_type(report: dict[str, JsonValue]) -> JsonValue:
    metadata = report.get("report_metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get("report_type")


def _report_path(output_root: Path | None, run_id: str, filename: str) -> Path:
    root = output_root or _default_output_root()
    return root / "ops_agent" / "reports" / run_id / filename


def _report_uri(run_id: str, filename: str) -> str:
    return f"{REPORTS_URI_PREFIX}/{run_id}/{filename}"


def _default_output_root() -> Path:
    return Path(__file__).resolve().parents[3] / "output"


@contextmanager
def _temporary_report_env(
    openai_api_key: str | None,
    openai_model: str | None,
) -> Iterator[None]:
    previous_key = os.environ.get("OPENAI_API_KEY")
    previous_model = os.environ.get("OPENAI_MODEL")
    if openai_api_key is not None:
        os.environ["OPENAI_API_KEY"] = openai_api_key
    if openai_model is not None:
        os.environ["OPENAI_MODEL"] = openai_model
    try:
        yield
    finally:
        _restore_env("OPENAI_API_KEY", previous_key)
        _restore_env("OPENAI_MODEL", previous_model)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
        return
    os.environ[name] = value
