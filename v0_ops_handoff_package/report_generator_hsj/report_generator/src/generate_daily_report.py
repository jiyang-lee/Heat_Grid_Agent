from __future__ import annotations

import re
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


SCHEMA_PATH = SCHEMAS_DIR / "daily_report.schema.json"
PROMPT_PATH = PROMPTS_DIR / "daily_report_prompt.md"
EXAMPLE_PATH = EXAMPLES_DIR / "daily_report.example.json"


REVIEW_REASON_LABELS = {
    "current_only_high": "기준 위험도 결과와 보조 의심 유형 사이에 차이가 있어 확인이 필요합니다.",
    "lead_time_1_3d": "1~3일 이내 위험 신호로 이어질 가능성이 있어 추세 확인이 필요합니다.",
    "fault_group_leakage_water_loss": "누수 또는 수손실 의심 신호가 있어 유량과 압력 계통 확인이 필요합니다.",
    "m1_specialist_gate_near_threshold": "보조 의심 유형이 기준값 근처에 있어 추가 확인이 필요합니다.",
    "risk_high_but_anomaly_not_confirmed": "위험도는 높지만 확정 이상으로 단정하기 어려워 현장 확인이 필요합니다.",
    "m1_priority_disagreement": "진단 근거 간 차이가 있어 운영자 검토가 필요합니다.",
}

INTERNAL_TERM_LABELS = {
    "current_best": "기준 위험도 결과",
    "current-best": "기준 위험도 결과",
    "m1_specialist": "보조 의심 유형",
    "M1 specialist": "보조 의심 유형",
    "M1 Specialist": "보조 의심 유형",
    "fault_group": "의심 유형",
    "leakage_water_loss": "누수 또는 수손실 의심",
    "unknown_review": "추가 확인 필요",
}


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


def sanitize_daily_report(report: ReportJson) -> ReportJson:
    report = _sanitize_text(report)
    report = _strip_number_prefixes(report)
    return _round_user_visible_numbers(report)


def enforce_daily_input_counts(report: ReportJson, inputs: ReportJson) -> ReportJson:
    cards = inputs.get("priority_cards") if isinstance(inputs.get("priority_cards"), list) else []
    work_orders = (
        inputs.get("work_order_summaries") if isinstance(inputs.get("work_order_summaries"), list) else []
    )
    if not cards:
        return report

    level_counts = {"urgent": 0, "high": 0, "medium": 0, "low": 0}
    review_required = 0
    for card in cards:
        if not isinstance(card, dict):
            continue
        level = _normalize_level(card.get("priority_level"))
        level_counts[level] = level_counts.get(level, 0) + 1
        if bool(card.get("review_required")):
            review_required += 1

    priority_counts = report.get("priority_counts")
    if not isinstance(priority_counts, dict):
        priority_counts = {}
    priority_counts.update(level_counts)
    priority_counts["by_review_required"] = {
        "required": review_required,
        "not_required": max(0, len(cards) - review_required),
    }
    report["priority_counts"] = priority_counts

    daily_summary = report.get("daily_summary")
    if isinstance(daily_summary, dict):
        daily_summary["total_priority_cards"] = len(cards)
        daily_summary["operator_review_required_count"] = review_required
        daily_summary.setdefault("overall_risk_level", _highest_schema_level(level_counts))

    work_order_overview = report.get("work_order_overview")
    if isinstance(work_order_overview, dict) and work_orders:
        status_counts = {
            "not_created": 0,
            "drafted": 0,
            "sent": 0,
            "acknowledged": 0,
            "in_progress": 0,
            "completed": 0,
            "cancelled": 0,
        }
        for item in work_orders:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "not_created").strip()
            if status not in status_counts:
                status = "not_created"
            status_counts[status] += 1
        work_order_overview["total"] = len(work_orders)
        work_order_overview["by_status"] = status_counts

    return report


def _sanitize_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_text(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize_text(child) for child in value]
    if isinstance(value, str):
        text = value
        for code, label in REVIEW_REASON_LABELS.items():
            text = text.replace(code, label)
        for code, label in INTERNAL_TERM_LABELS.items():
            text = text.replace(code, label)
        return text
    return value


def _strip_number_prefixes(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {key: _strip_number_prefixes(child) for key, child in value.items()}
        for key in ("action", "summary", "reason"):
            if isinstance(cleaned.get(key), str):
                cleaned[key] = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", cleaned[key]).strip()
        return cleaned
    if isinstance(value, list):
        return [_strip_number_prefixes(child) for child in value]
    return value


def _round_user_visible_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _round_user_visible_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_round_user_visible_numbers(child) for child in value]
    if isinstance(value, float):
        return round(value, 2)
    return value


def _normalize_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"urgent", "high", "medium", "low"}:
        return text
    if text == "긴급":
        return "urgent"
    if text == "높음":
        return "high"
    if text == "보통":
        return "medium"
    return "low"


def _highest_schema_level(level_counts: dict[str, int]) -> str:
    for level, schema_level in (
        ("urgent", "Urgent"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ):
        if level_counts.get(level, 0) > 0:
            return schema_level
    return "Low"


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
) -> ReportJson:
    if with_rag:
        from report_rag import enrich_daily_input_with_rag

        input_data = enrich_daily_input_with_rag(
            input_data,
            rag_url=rag_url,
            top_k=rag_top_k,
            force=force_rag,
        )
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
    if args.with_rag:
        from report_rag import enrich_daily_input_with_rag

        input_data = enrich_daily_input_with_rag(
            input_data,
            rag_url=args.rag_url,
            top_k=args.rag_top_k,
            force=args.force_rag,
        )
    if args.enrich_only:
        write_output_if_requested(input_data, args.output_path)
        if not args.quiet:
            print_json(input_data)
        return 0

    report = generate_daily_report_from_input(input_data, mock=args.mock)
    write_output_if_requested(report, args.output_path)
    if not args.quiet:
        print_json(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
