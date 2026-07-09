from __future__ import annotations

from daily_report_postprocess import enforce_daily_input_counts, sanitize_daily_report
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
    ReportJson,
    run_report_graph,
)


SCHEMA_PATH = SCHEMAS_DIR / "daily_report.schema.json"
PROMPT_PATH = PROMPTS_DIR / "daily_report_prompt.md"
EXAMPLE_PATH = EXAMPLES_DIR / "daily_report.example.json"


def normalize_daily_input(input_data: ReportJson) -> ReportJson:
    return dict(input_data)


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
    inputs["_output_schema"] = schema
    caller = llm_caller or call_llm_json
    report = caller(prompt, inputs)
    report = sanitize_daily_report(report)
    report = enforce_daily_input_counts(report, inputs)

    ensure_no_work_order_body(report)
    validate_report(report, schema)
    return report


def generate_daily_report_from_input(
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
        from report_rag import enrich_daily_input_with_rag

        return enrich_daily_input_with_rag(
            data,
            rag_url=options.rag_url,
            top_k=options.rag_top_k,
            force=options.force_rag,
        )

    def generate(data: ReportJson, options: ReportGraphOptions) -> ReportJson:
        return generate_daily_report(
            report_context=data.get("report_context"),
            priority_cards=data.get("priority_cards"),
            agent_outputs=data.get("agent_outputs"),
            ops_evidence_list=data.get("ops_evidence_list"),
            external_context_list=data.get("external_context_list"),
            rag_evidence=data.get("rag_evidence"),
            work_order_summaries=data.get("work_order_summaries"),
            previous_operator_memo=data.get("previous_operator_memo"),
            mock=options.mock,
            llm_caller=llm_caller,
        )

    return run_report_graph(
        ReportGraphSpec(
            normalize=normalize_daily_input,
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
    parser = make_cli_parser("Generate one HeatGrid daily operations report JSON.")
    parser.add_argument(
        "--from-priority-csv",
        action="store_true",
        help="output/agent_priority_card.csv를 하루 단위로 집계해 일간 보고서 입력을 생성합니다.",
    )
    parser.add_argument(
        "--priority-csv",
        default="output/agent_priority_card.csv",
        help="일간 보고서 입력으로 사용할 priority card CSV 경로입니다.",
    )
    parser.add_argument(
        "--site-context-csv",
        default="data/external/substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv",
        help="substation_id와 세종 아파트 매핑 정보를 담은 CSV 경로입니다.",
    )
    parser.add_argument(
        "--report-date",
        help="집계할 날짜입니다. YYYY-MM-DD 형식이며 생략하면 CSV에서 가장 최신 날짜를 사용합니다.",
    )
    parser.add_argument(
        "--max-cards",
        type=int,
        default=50,
        help="LLM 입력에 포함할 최대 카드 수입니다.",
    )
    parser.add_argument(
        "--exclude-low",
        action="store_true",
        help="낮음 위험도 카드는 일간 보고서 입력에서 제외합니다.",
    )
    args = parser.parse_args(argv)

    if args.from_priority_csv:
        from daily_input_builder import build_daily_input_from_priority_csv

        input_data = build_daily_input_from_priority_csv(
            priority_csv=args.priority_csv,
            report_date=args.report_date,
            site_context_csv=args.site_context_csv,
            max_cards=args.max_cards,
            include_low=not args.exclude_low,
        )
    else:
        input_data = load_input_or_empty(args.input_path)
    report = generate_daily_report_from_input(
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
