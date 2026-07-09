from __future__ import annotations

from anomaly_report_postprocess import sanitize_anomaly_report
from report_utils import (
    EXAMPLES_DIR,
    PROMPTS_DIR,
    SCHEMAS_DIR,
    LLMCaller,
    ReportJson,
    call_llm_json,
    ensure_no_work_order_body,
    load_input_or_empty,
    load_json,
    load_text,
    make_cli_parser,
    print_json,
    validate_report,
    write_output_if_requested,
)
from heatgrid_ops.reports.graph import (
    ReportGraphOptions,
    ReportGraphSpec,
    run_report_graph,
)


SCHEMA_PATH = SCHEMAS_DIR / "anomaly_report.schema.json"
PROMPT_PATH = PROMPTS_DIR / "anomaly_report_prompt.md"
EXAMPLE_PATH = EXAMPLES_DIR / "anomaly_report.example.json"


def normalize_anomaly_input(input_data: ReportJson) -> ReportJson:
    normalized = dict(input_data)
    if "ops_evidence" not in normalized and "raw_context" in normalized and "priority_context" in normalized:
        normalized["ops_evidence"] = {
            "raw_context": normalized.get("raw_context") or {},
            "priority_context": normalized.get("priority_context") or {},
            "internal_context": normalized.get("internal_context") or {},
        }

    if "priority_card" not in normalized:
        evidence = normalized.get("ops_evidence") if isinstance(normalized.get("ops_evidence"), dict) else {}
        raw_context = evidence.get("raw_context") if isinstance(evidence.get("raw_context"), dict) else {}
        priority_context = evidence.get("priority_context") if isinstance(evidence.get("priority_context"), dict) else {}
        window = raw_context.get("window") if isinstance(raw_context.get("window"), dict) else {}
        card = priority_context.get("card") if isinstance(priority_context.get("card"), dict) else {}
        priority = priority_context.get("priority") if isinstance(priority_context.get("priority"), dict) else {}
        signals = priority_context.get("model_signals") if isinstance(priority_context.get("model_signals"), dict) else {}
        explanation = (
            priority_context.get("explanation") if isinstance(priority_context.get("explanation"), dict) else {}
        )
        normalized["priority_card"] = {
            "card_id": card.get("card_id"),
            "substation_id": window.get("substation_id"),
            "manufacturer_id": window.get("manufacturer_id"),
            "configuration_type": window.get("configuration_type"),
            "window_start": window.get("window_start"),
            "window_end": window.get("window_end"),
            "priority_score": priority.get("priority_score"),
            "priority_level": priority.get("priority_level"),
            "current_best_priority_level": signals.get("current_best_priority_level"),
            "m1_specialist_priority_level": signals.get("m1_specialist_priority_level"),
            "m1_specialist_primary_state": signals.get("m1_specialist_primary_state"),
            "m1_specialist_fault_group": signals.get("m1_specialist_fault_group"),
            "review_required": explanation.get("review_required"),
            "review_reasons": explanation.get("review_reasons") or [],
            "operational_label": card.get("operational_label"),
            "recommended_action": explanation.get("recommended_action"),
            "why_reason": explanation.get("why_reason"),
        }

    return normalized


def build_anomaly_inputs(
    *,
    priority_card: ReportJson | None = None,
    agent_output: ReportJson | None = None,
    ops_evidence: ReportJson | None = None,
    external_context: ReportJson | None = None,
    rag_evidence: list[ReportJson] | ReportJson | None = None,
    work_order_summary: ReportJson | None = None,
    report_context: ReportJson | None = None,
) -> ReportJson:
    return {
        "priority_card": priority_card or {},
        "agent_output": agent_output or {},
        "ops_evidence": ops_evidence or {},
        "external_context": external_context or {},
        "rag_evidence": rag_evidence or [],
        "work_order_summary": work_order_summary or {},
        "report_context": report_context or {},
    }


def generate_anomaly_report(
    *,
    priority_card: ReportJson | None = None,
    agent_output: ReportJson | None = None,
    ops_evidence: ReportJson | None = None,
    external_context: ReportJson | None = None,
    rag_evidence: list[ReportJson] | ReportJson | None = None,
    work_order_summary: ReportJson | None = None,
    report_context: ReportJson | None = None,
    mock: bool = False,
    llm_caller: LLMCaller | None = None,
) -> ReportJson:
    schema = load_json(SCHEMA_PATH)

    if mock:
        report = load_json(EXAMPLE_PATH)
        ensure_no_work_order_body(report)
        validate_report(report, schema)
        return report

    prompt = load_text(PROMPT_PATH)
    inputs = build_anomaly_inputs(
        priority_card=priority_card,
        agent_output=agent_output,
        ops_evidence=ops_evidence,
        external_context=external_context,
        rag_evidence=rag_evidence,
        work_order_summary=work_order_summary,
        report_context=report_context,
    )
    inputs["_output_schema"] = schema
    caller = llm_caller or call_llm_json
    report = caller(prompt, inputs)
    report = sanitize_anomaly_report(report)

    ensure_no_work_order_body(report)
    validate_report(report, schema)
    return report


def generate_anomaly_report_from_input(
    input_data: ReportJson,
    *,
    mock: bool = False,
    llm_caller: LLMCaller | None = None,
    with_rag: bool = False,
    rag_url: str | None = None,
    rag_top_k: int = 5,
    force_rag: bool = False,
    enrich_only: bool = False,
) -> ReportJson:
    def enrich(data: ReportJson, options: ReportGraphOptions) -> ReportJson:
        from report_rag import enrich_anomaly_input_with_rag

        return enrich_anomaly_input_with_rag(
            data,
            rag_url=options.rag_url,
            top_k=options.rag_top_k,
            force=options.force_rag,
        )

    def generate(data: ReportJson, options: ReportGraphOptions) -> ReportJson:
        return generate_anomaly_report(
            priority_card=data.get("priority_card"),
            agent_output=data.get("agent_output"),
            ops_evidence=data.get("ops_evidence"),
            external_context=data.get("external_context"),
            rag_evidence=data.get("rag_evidence"),
            work_order_summary=data.get("work_order_summary"),
            report_context=data.get("report_context"),
            mock=options.mock,
            llm_caller=llm_caller,
        )

    return run_report_graph(
        ReportGraphSpec(
            normalize=normalize_anomaly_input,
            enrich=enrich,
            generate=generate,
        ),
        input_data,
        ReportGraphOptions(
            mock=mock,
            with_rag=with_rag,
            rag_url=rag_url,
            rag_top_k=rag_top_k,
            force_rag=force_rag,
            enrich_only=enrich_only,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = make_cli_parser("Generate one HeatGrid anomaly report JSON.")
    args = parser.parse_args(argv)

    input_data = load_input_or_empty(args.input_path)
    report = generate_anomaly_report_from_input(
        input_data,
        mock=args.mock,
        with_rag=args.with_rag,
        rag_url=args.rag_url,
        rag_top_k=args.rag_top_k,
        force_rag=args.force_rag,
        enrich_only=args.enrich_only,
    )
    write_output_if_requested(report, args.output_path)
    if not args.quiet:
        print_json(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
