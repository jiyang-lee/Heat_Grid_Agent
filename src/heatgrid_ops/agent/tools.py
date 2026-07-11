from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from langchain_core.tools import BaseTool, tool

from evidence_repository import filter_ops_evidence
from heatgrid_ops.agent.external_search import ExternalEvidenceSearchResult
from heatgrid_ops.agent.helpers import card_id_from_input, to_json
from heatgrid_ops.reports.anomaly import write_anomaly_report_json
from heatgrid_ops.reports.daily import write_daily_report_json
from schemas import JsonValue

REPORTS_URI_PREFIX: Final = "output/ops_agent/reports"
LLM_SELECTABLE_TOOL_NAMES: Final = (
    "get_ops_evidence",
    "get_priority_snapshot",
    "get_substation_context",
    "get_sensor_evidence",
    "get_model_evidence",
    "get_internal_references",
    "get_external_context",
    "get_agent_loop_context",
)
GRAPH_CONTROLLED_TOOL_NAMES: Final = (
    "search_external_evidence",
    "stage_evidence_candidate",
    "write_anomaly_report",
    "write_daily_report",
)
ALL_AGENT_TOOL_NAMES: Final = LLM_SELECTABLE_TOOL_NAMES + GRAPH_CONTROLLED_TOOL_NAMES

type ExternalSearchRunner = Callable[[str], Awaitable[ExternalEvidenceSearchResult]]
type EvidenceCandidateWriter = Callable[
    [dict[str, JsonValue]], Awaitable[dict[str, JsonValue]]
]


LLM_SELECTABLE_TOOL_NAMES: Final = (
    "get_ops_evidence",
    "get_priority_snapshot",
    "get_substation_context",
    "get_sensor_evidence",
    "get_model_evidence",
    "get_internal_references",
    "get_external_context",
    "get_agent_loop_context",
)
GRAPH_CONTROLLED_TOOL_NAMES: Final = ("write_anomaly_report", "write_daily_report")
ALL_AGENT_TOOL_NAMES: Final = LLM_SELECTABLE_TOOL_NAMES + GRAPH_CONTROLLED_TOOL_NAMES


def make_operational_tools(
    source_input: JsonObject,
    evidence_context: JsonObject,
) -> list[BaseTool]:
    return [
        make_ops_evidence_tool(source_input),
        make_priority_snapshot_tool(source_input),
        make_substation_context_tool(source_input, external_context),
        make_sensor_evidence_tool(source_input),
        make_model_evidence_tool(source_input),
        make_internal_references_tool(source_input, external_context),
        make_external_context_tool(source_input, external_context),
        make_agent_loop_context_tool(source_input, external_context),
    ]


def make_ops_evidence_tool(source_input: JsonObject) -> BaseTool:
    @tool(description="Return card, raw sensor, and ML model evidence.")
    def get_ops_evidence(card_id: str, sections: list[str] | None = None) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        if sections is None:
            return to_json(source_input)
        source_sections = _mapping(source_input.get("sections"))
        unsupported: list[JsonValue] = [
            name for name in sections if name not in source_sections
        ]
        return to_json(
            {
                "card_id": card_id,
                "sections": {
                    name: source_sections[name]
                    for name in sections
                    if name in source_sections
                },
                "unsupported_sections": unsupported,
            }
        )

    return get_ops_evidence


def make_external_context_tool(
    source_input: JsonObject,
    evidence_context: JsonObject,
) -> BaseTool:
    @tool(description="Return mapped site and structured weather snapshot.")
    def get_external_context(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        return to_json(
            {
                "status": external_context.get("status", "unavailable"),
                "site": external_context.get("site", {}),
                "weather": external_context.get("weather", {}),
            }
        )

    return get_external_context


def make_priority_snapshot_tool(source_input: dict[str, JsonValue]) -> BaseTool:
    @tool(description="Return the priority evaluation snapshot and stored priority decision.")
    def get_priority_snapshot(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        return to_json(
            {
                "evaluation_context": source_input.get("evaluation_context", {}),
                "priority_context": source_input.get("priority_context", {}),
            }
        )

    return get_priority_snapshot


def make_substation_context_tool(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> BaseTool:
    @tool(description="Return substation, source window, configuration, and mapped site context.")
    def get_substation_context(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        raw_context = _mapping(source_input.get("raw_context"))
        return to_json(
            {
                "substation": raw_context.get("substation", {}),
                "window": raw_context.get("window", {}),
                "site": external_context.get("site", {}),
            }
        )

    return get_substation_context


def make_sensor_evidence_tool(source_input: dict[str, JsonValue]) -> BaseTool:
    @tool(description="Return sensor summaries for the selected completed source window.")
    def get_sensor_evidence(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        raw_context = _mapping(source_input.get("raw_context"))
        return to_json({"sensor_summaries": raw_context.get("sensor_summaries", [])})

    return get_sensor_evidence


def make_model_evidence_tool(source_input: dict[str, JsonValue]) -> BaseTool:
    @tool(description="Return stored risk, anomaly, lead-time, and priority model outputs.")
    def get_model_evidence(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        priority_context = _mapping(source_input.get("priority_context"))
        return to_json(
            {
                "model_outputs": priority_context.get("model_outputs", []),
                "model_signals": priority_context.get("model_signals", {}),
            }
        )

    return get_model_evidence


def make_internal_references_tool(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> BaseTool:
    @tool(description="Return already-retrieved internal operating references from RAG.")
    def get_internal_references(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        return to_json({"retrieval": external_context.get("retrieval", {})})

    return get_internal_references


def make_agent_loop_context_tool(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> BaseTool:
    @tool(description="Return model verification, evidence assessment, and pending evidence context.")
    def get_agent_loop_context(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        return to_json(
            {
                "model_verification": external_context.get("model_verification"),
                "evidence_assessment": external_context.get("evidence_assessment"),
                "pending_external_evidence": external_context.get(
                    "pending_external_evidence", []
                ),
            }
        )

    return get_agent_loop_context


def make_external_search_tool(search: ExternalSearchRunner) -> BaseTool:
    @tool(description="Search approved external domains after the graph policy gate allows cost.")
    async def search_external_evidence(query: str) -> str:
        result = await search(query)
        return to_json(result.model_dump(mode="json"))

    return search_external_evidence


def make_stage_evidence_candidate_tool(
    write_candidate: EvidenceCandidateWriter,
) -> BaseTool:
    @tool(description="Stage an external evidence candidate and its review task in PostgreSQL.")
    async def stage_evidence_candidate(payload_json: str) -> str:
        payload = _report_tool_payload(payload_json)
        return to_json(await write_candidate(payload))

    return stage_evidence_candidate


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
                "evaluation_context": source_input.get("evaluation_context", {}),
                "priority_context": source_input.get("priority_context", {}),
            }
        )

    return get_priority_snapshot


def make_substation_context_tool(
    source_input: JsonObject,
    evidence_context: JsonObject,
) -> BaseTool:
    @tool(description="Return substation, source window, and mapped site context.")
    def get_substation_context(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        raw_context = _mapping(source_input.get("raw_context"))
        return to_json(
            {
                "substation": raw_context.get("substation", {}),
                "window": raw_context.get("window", {}),
                "site": evidence_context.get("site", {}),
            }
        )

    return get_substation_context


def make_sensor_evidence_tool(source_input: JsonObject) -> BaseTool:
    @tool(description="Return sensor summaries for the completed source window.")
    def get_sensor_evidence(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        raw_context = _mapping(source_input.get("raw_context"))
        return to_json({"sensor_summaries": raw_context.get("sensor_summaries", [])})

    return get_sensor_evidence


def make_model_evidence_tool(source_input: JsonObject) -> BaseTool:
    @tool(description="Return stored risk, anomaly, lead-time, and priority outputs.")
    def get_model_evidence(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        priority_context = _mapping(source_input.get("priority_context"))
        return to_json(
            {
                "model_outputs": priority_context.get("model_outputs", []),
                "model_signals": priority_context.get("model_signals", {}),
            }
        )

    return get_model_evidence


def make_internal_references_tool(
    source_input: JsonObject,
    evidence_context: JsonObject,
) -> BaseTool:
    @tool(description="Return already-retrieved internal RAG references.")
    def get_internal_references(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        return to_json({"retrieval": evidence_context.get("retrieval", {})})

    return get_internal_references


def make_agent_loop_context_tool(
    source_input: JsonObject,
    evidence_context: JsonObject,
) -> BaseTool:
    @tool(description="Return model verification and evidence assessment context.")
    def get_agent_loop_context(card_id: str) -> str:
        error = _card_error(source_input, card_id)
        if error is not None:
            return error
        return to_json(
            {
                "model_verification": evidence_context.get("model_verification"),
                "evidence_assessment": evidence_context.get("evidence_assessment"),
            }
        )

    return get_agent_loop_context


def _card_error(source_input: JsonObject, card_id: str) -> str | None:
    if card_id == card_id_from_input(source_input):
        return None
    return to_json({"error": "card_id was not found"})


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


def _card_error(source_input: dict[str, JsonValue], card_id: str) -> str | None:
    if card_id == card_id_from_input(source_input):
        return None
    return to_json({"error": "card_id를 찾을 수 없습니다."})


def _mapping(value: JsonValue | None) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}
