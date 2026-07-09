from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeAlias, TypedDict

from langgraph.graph import END, START, StateGraph

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
ReportJson: TypeAlias = dict[str, JsonValue]
NormalizeReport: TypeAlias = Callable[[ReportJson], ReportJson]
EnrichReport: TypeAlias = Callable[["ReportJson", "ReportGraphOptions"], ReportJson]
GenerateReport: TypeAlias = Callable[["ReportJson", "ReportGraphOptions"], ReportJson]
BuildReportPayload: TypeAlias = Callable[["ReportJson", "ReportGraphOptions"], ReportJson]
ReportTransform: TypeAlias = Callable[[ReportJson, "ReportGraphOptions"], ReportJson]
RouteName: TypeAlias = Literal[
    "optional_rag_enrich",
    "build_llm_payload",
    "return_enriched",
]


class ReportState(TypedDict, total=False):
    input_data: ReportJson
    llm_payload: ReportJson
    report: ReportJson


@dataclass(frozen=True, slots=True)
class ReportGraphOptions:
    mock: bool = False
    with_rag: bool = False
    rag_url: str | None = None
    rag_top_k: int = 5
    force_rag: bool = False
    enrich_only: bool = False


@dataclass(frozen=True, slots=True)
class ReportGraphSpec:
    normalize: NormalizeReport
    enrich: EnrichReport
    generate: GenerateReport
    build_llm_payload: BuildReportPayload | None = None
    call_llm: GenerateReport | None = None
    sanitize: ReportTransform | None = None
    validate_schema: ReportTransform | None = None
    write_output: ReportTransform | None = None


def run_report_graph(
    spec: ReportGraphSpec,
    input_data: ReportJson,
    options: ReportGraphOptions,
) -> ReportJson:
    graph = StateGraph(ReportState)

    def normalize_input(state: ReportState) -> ReportState:
        return {"input_data": spec.normalize(state["input_data"])}

    def optional_rag_enrich(state: ReportState) -> ReportState:
        return {"input_data": spec.enrich(state["input_data"], options)}

    def build_llm_payload(state: ReportState) -> ReportState:
        if spec.build_llm_payload is None:
            return {"llm_payload": state["input_data"]}
        return {"llm_payload": spec.build_llm_payload(state["input_data"], options)}

    def call_llm(state: ReportState) -> ReportState:
        if spec.call_llm is None:
            return {"report": spec.generate(state["llm_payload"], options)}
        return {"report": spec.call_llm(state["llm_payload"], options)}

    def sanitize(state: ReportState) -> ReportState:
        if spec.sanitize is None:
            return {}
        return {"report": spec.sanitize(state["report"], options)}

    def validate_schema(state: ReportState) -> ReportState:
        if spec.validate_schema is None:
            return {}
        return {"report": spec.validate_schema(state["report"], options)}

    def write_output(state: ReportState) -> ReportState:
        if spec.write_output is None:
            return {}
        return {"report": spec.write_output(state["report"], options)}

    def return_enriched(_: ReportState) -> ReportState:
        return {}

    def route_after_context(_: ReportState) -> RouteName:
        if options.enrich_only:
            return "return_enriched"
        return "build_llm_payload"

    def route_after_normalize(_: ReportState) -> RouteName:
        if options.with_rag:
            return "optional_rag_enrich"
        return route_after_context({})

    graph.add_node("normalize_input", normalize_input)
    graph.add_node("optional_rag_enrich", optional_rag_enrich)
    graph.add_node("build_llm_payload", build_llm_payload)
    graph.add_node("call_llm", call_llm)
    graph.add_node("sanitize", sanitize)
    graph.add_node("validate_schema", validate_schema)
    graph.add_node("write_output", write_output)
    graph.add_node("return_enriched", return_enriched)
    graph.add_edge(START, "normalize_input")
    graph.add_conditional_edges(
        "normalize_input",
        route_after_normalize,
        {
            "optional_rag_enrich": "optional_rag_enrich",
            "build_llm_payload": "build_llm_payload",
            "return_enriched": "return_enriched",
        },
    )
    graph.add_conditional_edges(
        "optional_rag_enrich",
        route_after_context,
        {
            "build_llm_payload": "build_llm_payload",
            "return_enriched": "return_enriched",
        },
    )
    graph.add_edge("build_llm_payload", "call_llm")
    graph.add_edge("call_llm", "sanitize")
    graph.add_edge("sanitize", "validate_schema")
    graph.add_edge("validate_schema", "write_output")
    graph.add_edge("write_output", END)
    graph.add_edge("return_enriched", END)
    state = graph.compile().invoke({"input_data": input_data})
    if options.enrich_only:
        return state["input_data"]
    return state["report"]
