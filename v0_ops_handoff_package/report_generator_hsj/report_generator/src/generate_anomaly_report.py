from __future__ import annotations

from typing import Any

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


SCHEMA_PATH = SCHEMAS_DIR / "anomaly_report.schema.json"
PROMPT_PATH = PROMPTS_DIR / "anomaly_report_prompt.md"
EXAMPLE_PATH = EXAMPLES_DIR / "anomaly_report.example.json"


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
    caller = llm_caller or call_llm_json
    report = caller(prompt, inputs)

    ensure_no_work_order_body(report)
    validate_report(report, schema)
    return report


def generate_anomaly_report_from_input(
    input_data: ReportJson,
    *,
    mock: bool = False,
    llm_caller: LLMCaller | None = None,
) -> ReportJson:
    return generate_anomaly_report(
        priority_card=input_data.get("priority_card"),
        agent_output=input_data.get("agent_output"),
        ops_evidence=input_data.get("ops_evidence"),
        external_context=input_data.get("external_context"),
        rag_evidence=input_data.get("rag_evidence"),
        work_order_summary=input_data.get("work_order_summary"),
        report_context=input_data.get("report_context"),
        mock=mock,
        llm_caller=llm_caller,
    )


def main(argv: list[str] | None = None) -> int:
    parser = make_cli_parser("Generate one HeatGrid anomaly report JSON.")
    args = parser.parse_args(argv)

    input_data = load_input_or_empty(args.input_path)
    report = generate_anomaly_report_from_input(input_data, mock=args.mock)
    write_output_if_requested(report, args.output_path)
    print_json(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
