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


REVIEW_REASON_LABELS = {
    "current_only_high": "기준 위험도와 보조 판단 사이에 차이가 있어 확인이 필요합니다.",
    "lead_time_1_3d": "단기 위험 가능성이 있어 다음 1~3일 구간의 추세 확인이 필요합니다.",
    "fault_group_leakage_water_loss": "누수 또는 수손실 계열 신호가 의심되어 유량과 압력 계통 확인이 필요합니다.",
    "risk_high_but_anomaly_not_confirmed": "위험도는 높지만 확정 이상으로 단정하기 어려워 현장 확인이 필요합니다.",
    "m1_priority_disagreement": "판단 근거 간 차이가 있어 운영자 검토가 필요합니다.",
}

INTERNAL_TERM_LABELS = {
    "current_best": "기준 위험도 결과",
    "m1_specialist": "보조 의심 유형",
    "M1 Specialist": "보조 의심 유형",
    "leakage_water_loss": "누수 또는 수손실 의심",
    "substation 31": "31번 열수급 지점",
    "substation": "열수급 지점",
}


def sanitize_anomaly_report(report: ReportJson) -> ReportJson:
    operator_note = report.get("operator_note")
    if isinstance(operator_note, dict) and isinstance(operator_note.get("review_reasons"), list):
        operator_note["review_reasons"] = [
            REVIEW_REASON_LABELS.get(str(reason), str(reason).replace("_", " "))
            for reason in operator_note["review_reasons"]
        ]
    return _round_user_visible_numbers(_sanitize_review_reason_text(report))


def _sanitize_review_reason_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_review_reason_text(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize_review_reason_text(child) for child in value]
    if isinstance(value, str):
        text = value
        for code, label in REVIEW_REASON_LABELS.items():
            text = text.replace(code, label)
        for code, label in INTERNAL_TERM_LABELS.items():
            text = text.replace(code, label)
        return text
    return value


def _round_user_visible_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _round_user_visible_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_round_user_visible_numbers(child) for child in value]
    if isinstance(value, float):
        return round(value, 2)
    return value


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
) -> ReportJson:
    input_data = normalize_anomaly_input(input_data)
    if with_rag:
        from report_rag import enrich_anomaly_input_with_rag

        input_data = enrich_anomaly_input_with_rag(
            input_data,
            rag_url=rag_url,
            top_k=rag_top_k,
            force=force_rag,
        )
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
    if args.with_rag:
        from report_rag import enrich_anomaly_input_with_rag

        input_data = enrich_anomaly_input_with_rag(
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

    report = generate_anomaly_report_from_input(input_data, mock=args.mock)
    write_output_if_requested(report, args.output_path)
    if not args.quiet:
        print_json(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
