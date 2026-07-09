from __future__ import annotations

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


SCHEMA_PATH = SCHEMAS_DIR / "daily_report.schema.json"
PROMPT_PATH = PROMPTS_DIR / "daily_report_prompt.md"
EXAMPLE_PATH = EXAMPLES_DIR / "daily_report.example.json"


def build_daily_inputs(
    *,
    report_context: ReportJson | None = None,
    priority_cards: list[ReportJson] | None = None,
    agent_outputs: list[ReportJson] | None = None,
    ops_evidence_list: list[ReportJson] | None = None,
    external_context_list: list[ReportJson] | None = None,
    rag_evidence: list[ReportJson] | ReportJson | None = None,
    work_order_summaries: list[ReportJson] | None = None,
    previous_operator_memo: str | ReportJson | None = None,
) -> ReportJson:
    return {
        "report_context": report_context or {},
        "priority_cards": priority_cards or [],
        "agent_outputs": agent_outputs or [],
        "ops_evidence_list": ops_evidence_list or [],
        "external_context_list": external_context_list or [],
        "rag_evidence": rag_evidence or [],
        "work_order_summaries": work_order_summaries or [],
        "previous_operator_memo": previous_operator_memo,
    }


def generate_daily_report(
    *,
    report_context: ReportJson | None = None,
    priority_cards: list[ReportJson] | None = None,
    agent_outputs: list[ReportJson] | None = None,
    ops_evidence_list: list[ReportJson] | None = None,
    external_context_list: list[ReportJson] | None = None,
    rag_evidence: list[ReportJson] | ReportJson | None = None,
    work_order_summaries: list[ReportJson] | None = None,
    previous_operator_memo: str | ReportJson | None = None,
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
    inputs = build_daily_inputs(
        report_context=report_context,
        priority_cards=priority_cards,
        agent_outputs=agent_outputs,
        ops_evidence_list=ops_evidence_list,
        external_context_list=external_context_list,
        rag_evidence=rag_evidence,
        work_order_summaries=work_order_summaries,
        previous_operator_memo=previous_operator_memo,
    )
    caller = llm_caller or call_llm_json
    report = caller(prompt, inputs)

    ensure_no_work_order_body(report)
    validate_report(report, schema)
    return report


def generate_daily_report_from_input(
    input_data: ReportJson,
    *,
    mock: bool = False,
    llm_caller: LLMCaller | None = None,
) -> ReportJson:
    return generate_daily_report(
        report_context=input_data.get("report_context"),
        priority_cards=input_data.get("priority_cards"),
        agent_outputs=input_data.get("agent_outputs"),
        ops_evidence_list=input_data.get("ops_evidence_list"),
        external_context_list=input_data.get("external_context_list"),
        rag_evidence=input_data.get("rag_evidence"),
        work_order_summaries=input_data.get("work_order_summaries"),
        previous_operator_memo=input_data.get("previous_operator_memo"),
        mock=mock,
        llm_caller=llm_caller,
    )


def main(argv: list[str] | None = None) -> int:
    parser = make_cli_parser("Generate one HeatGrid daily operations report JSON.")
    args = parser.parse_args(argv)

    input_data = load_input_or_empty(args.input_path)
    report = generate_daily_report_from_input(input_data, mock=args.mock)
    write_output_if_requested(report, args.output_path)
    print_json(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
