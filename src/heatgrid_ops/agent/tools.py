from __future__ import annotations

from typing import Final

from langchain_core.tools import BaseTool, tool

from heatgrid_ops.agent.helpers import card_id_from_input, to_json
from heatgrid_ops.agent.models import JsonObject, JsonValue


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
        make_substation_context_tool(source_input, evidence_context),
        make_sensor_evidence_tool(source_input),
        make_model_evidence_tool(source_input),
        make_internal_references_tool(source_input, evidence_context),
        make_external_context_tool(source_input, evidence_context),
        make_agent_loop_context_tool(source_input, evidence_context),
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
                "status": evidence_context.get("status", "unavailable"),
                "site": evidence_context.get("site", {}),
                "weather": evidence_context.get("weather", {}),
            }
        )

    return get_external_context


def make_priority_snapshot_tool(source_input: JsonObject) -> BaseTool:
    @tool(description="Return the stored priority decision and evaluation snapshot.")
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


def _mapping(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}
