from __future__ import annotations

import csv
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ReportJson = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PRIORITY_CSV = PROJECT_ROOT / "output" / "agent_priority_card.csv"
DEFAULT_SITE_CONTEXT_CSV = (
    PROJECT_ROOT
    / "data"
    / "external"
    / "substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv"
)

KST = timezone(timedelta(hours=9))
LEVEL_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
SCHEMA_LEVEL = {"urgent": "Urgent", "high": "High", "medium": "Medium", "low": "Low"}
KOREAN_LEVEL = {"urgent": "긴급", "high": "높음", "medium": "보통", "low": "낮음"}


def build_daily_input_from_priority_csv(
    *,
    priority_csv: str | Path = DEFAULT_PRIORITY_CSV,
    report_date: str | None = None,
    site_context_csv: str | Path = DEFAULT_SITE_CONTEXT_CSV,
    max_cards: int = 50,
    include_low: bool = True,
) -> ReportJson:
    rows = load_priority_rows(Path(priority_csv))
    if not rows:
        raise ValueError(f"No priority card rows found: {priority_csv}")

    date = report_date or latest_report_date(rows)
    selected = [row for row in rows if row_date(row.get("window_start")) == date]
    if not selected:
        raise ValueError(f"No priority card rows found for report_date={date}")
    if not include_low:
        selected = [row for row in selected if normalize_level(row.get("priority_level")) != "low"]
    if not selected:
        raise ValueError(f"No reportable priority card rows after filtering for report_date={date}")

    selected = sort_priority_rows(selected)[: max(1, max_cards)]
    site_map = load_site_context(Path(site_context_csv))
    priority_cards = [build_priority_card(row, site_map) for row in selected]
    ops_evidence_list = [build_ops_evidence(row, site_map) for row in selected]
    work_orders = [build_work_order_summary(card) for card in priority_cards]

    coverage_start, coverage_end = coverage_window(selected)
    counts = Counter(normalize_level(row.get("priority_level")) for row in selected)
    report_id = f"DAILY-{date.replace('-', '')}"

    return {
        "report_context": {
            "report_id": report_id,
            "schema_version": "1.0",
            "generated_at": datetime.now(KST).replace(microsecond=0).isoformat(),
            "report_date": date,
            "coverage_start": to_iso8601(coverage_start),
            "coverage_end": to_iso8601(coverage_end),
            "generated_by": "heatgrid-report-generator",
            "source": {
                "priority_csv": str(Path(priority_csv)),
                "site_context_csv": str(Path(site_context_csv)),
                "row_count": len(selected),
                "priority_counts": {level: counts.get(level, 0) for level in ("urgent", "high", "medium", "low")},
                "input_note": "output/agent_priority_card.csv를 하루 단위로 집계한 실제 모델 산출물 기반 입력입니다.",
            },
        },
        "priority_cards": priority_cards,
        "agent_outputs": [],
        "ops_evidence_list": ops_evidence_list,
        "external_context_list": [],
        "rag_evidence": [],
        "work_order_summaries": work_orders,
        "previous_operator_memo": None,
    }


def load_priority_rows(path: Path) -> list[ReportJson]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def load_site_context(path: Path) -> dict[int, ReportJson]:
    if not path.exists():
        return {}
    result: dict[int, ReportJson] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            substation_id = to_int(row.get("substation_id"))
            if substation_id is not None:
                result[substation_id] = dict(row)
    return result


def latest_report_date(rows: list[ReportJson]) -> str:
    dates = sorted({row_date(row.get("window_start")) for row in rows if row_date(row.get("window_start"))})
    if not dates:
        raise ValueError("No valid window_start values in priority CSV.")
    return dates[-1]


def row_date(value: Any) -> str:
    parsed = parse_datetime(value)
    return parsed.date().isoformat() if parsed else ""


def coverage_window(rows: list[ReportJson]) -> tuple[datetime, datetime]:
    starts = [parse_datetime(row.get("window_start")) for row in rows]
    ends = [parse_datetime(row.get("window_end")) for row in rows]
    starts = [value for value in starts if value is not None]
    ends = [value for value in ends if value is not None]
    if not starts or not ends:
        now = datetime.now(KST).replace(microsecond=0)
        return now, now
    return min(starts), max(ends)


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed


def to_iso8601(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def sort_priority_rows(rows: list[ReportJson]) -> list[ReportJson]:
    return sorted(
        rows,
        key=lambda row: (
            LEVEL_ORDER.get(normalize_level(row.get("priority_level")), 99),
            -float_or_zero(row.get("priority_score")),
            str(row.get("window_start") or ""),
            str(row.get("substation_id") or ""),
        ),
    )


def build_priority_card(row: ReportJson, site_map: dict[int, ReportJson]) -> ReportJson:
    substation_id = to_int(row.get("substation_id"))
    site = site_map.get(substation_id or -1, {})
    card_id = stable_card_id(row)
    priority_level = normalize_level(row.get("priority_level"))
    return {
        "card_id": card_id,
        "substation_id": substation_id,
        "asset_label": asset_label(substation_id, site),
        "location_label": location_label(site),
        "manufacturer_id": row.get("manufacturer"),
        "configuration_type": row.get("configuration_type"),
        "window_start": to_iso8601(parse_datetime(row.get("window_start")) or datetime.now(KST)),
        "window_end": to_iso8601(parse_datetime(row.get("window_end")) or datetime.now(KST)),
        "priority_score": round_float(row.get("priority_score")),
        "priority_level": priority_level,
        "priority_level_ko": KOREAN_LEVEL.get(priority_level, "확인 필요"),
        "current_best_priority_level": normalize_level(row.get("current_best_priority_level")),
        "m1_specialist_priority_level": normalize_level(row.get("m1_specialist_priority_level")),
        "m1_specialist_primary_state": row.get("m1_specialist_primary_state") or None,
        "m1_specialist_fault_group": row.get("m1_specialist_fault_group") or None,
        "review_required": to_bool(row.get("review_required")),
        "review_reasons": split_reasons(row.get("review_reasons")),
        "operational_label": row.get("operational_label") or row.get("primary_state"),
        "recommended_action": row.get("recommended_action") or None,
        "why_reason": row.get("why_reason") or row.get("priority_reason") or None,
        "risk_probability": round_float(row.get("risk_probability")),
        "predicted_lead_time_bucket": row.get("predicted_lead_time_bucket") or None,
        "source_row": {
            "fault_label": row.get("fault_label") or None,
            "fault_event_id": row.get("fault_event_id") or None,
            "trust_level": row.get("trust_level") or None,
        },
    }


def build_ops_evidence(row: ReportJson, site_map: dict[int, ReportJson]) -> ReportJson:
    substation_id = to_int(row.get("substation_id"))
    site = site_map.get(substation_id or -1, {})
    card_id = stable_card_id(row)
    priority_level = normalize_level(row.get("priority_level"))
    return {
        "raw_context": {
            "window": {
                "window_id": stable_window_id(row),
                "manufacturer_id": row.get("manufacturer"),
                "substation_id": substation_id,
                "configuration_type": row.get("configuration_type"),
                "window_start": to_iso8601(parse_datetime(row.get("window_start")) or datetime.now(KST)),
                "window_end": to_iso8601(parse_datetime(row.get("window_end")) or datetime.now(KST)),
            },
            "asset_context": {
                "asset_label": asset_label(substation_id, site),
                "location_label": location_label(site),
                "apartment_name": site.get("matched_name") or None,
                "road_address": site.get("road_address") or None,
                "heating_type": site.get("heating_type") or None,
                "household_count": to_int(site.get("household_count")),
                "sensor_groups_ko": clean_sensor_groups(site.get("predist_sensor_groups_ko")),
                "mapping_caution": site.get("predist_mapping_note") or None,
            },
            "model_row_summary": {
                "anomaly_ensemble_score": round_float(row.get("anomaly_ensemble_score")),
                "risk_probability": round_float(row.get("risk_probability")),
                "risk_level_calibrated": row.get("risk_level_calibrated") or None,
                "predicted_lead_time_bucket": row.get("predicted_lead_time_bucket") or None,
                "anomaly_consensus_count": to_int(row.get("anomaly_consensus_count")),
                "anomaly_criticality": to_int(row.get("anomaly_criticality")),
            },
        },
        "priority_context": {
            "card": {
                "card_id": card_id,
                "operational_label": row.get("operational_label") or row.get("primary_state"),
                "primary_state": row.get("primary_state") or None,
                "trust_level": row.get("trust_level") or None,
            },
            "priority": {
                "priority_decision_id": stable_decision_id(row),
                "priority_score": round_float(row.get("priority_score")),
                "priority_level": priority_level,
                "priority_source": row.get("priority_source") or None,
                "m1_priority_agreement": row.get("m1_priority_agreement") or None,
            },
            "model_signals": {
                "current_best_priority_score": round_float(row.get("current_best_priority_score")),
                "current_best_priority_level": normalize_level(row.get("current_best_priority_level")),
                "m1_specialist_priority_score": round_float(row.get("m1_specialist_priority_score")),
                "m1_specialist_priority_level": normalize_level(row.get("m1_specialist_priority_level")),
                "m1_specialist_primary_state": row.get("m1_specialist_primary_state") or None,
                "m1_specialist_fault_group": row.get("m1_specialist_fault_group") or None,
                "m1_specialist_fault_probability": round_float(row.get("m1_specialist_fault_probability")),
            },
            "explanation": {
                "why_reason": row.get("why_reason") or row.get("priority_reason") or None,
                "recommended_action": row.get("recommended_action") or None,
                "review_required": to_bool(row.get("review_required")),
                "review_reasons": split_reasons(row.get("review_reasons")),
            },
        },
        "internal_context": {
            "data_quality": {
                "review_required": to_bool(row.get("review_required")),
                "trust_level": row.get("trust_level") or None,
            },
            "asset_context": {
                "manufacturer_id": row.get("manufacturer"),
                "substation_id": substation_id,
                "configuration_type": row.get("configuration_type"),
            },
            "window_context": {
                "source_file": f"substation_{substation_id}.csv" if substation_id is not None else None,
                "season_bucket": infer_season(row.get("window_start")),
            },
        },
    }


def build_work_order_summary(card: ReportJson) -> ReportJson:
    level = normalize_level(card.get("priority_level"))
    should_track = level in {"urgent", "high"} or bool(card.get("review_required"))
    return {
        "work_order_issued": False,
        "status": "not_created",
        "work_order_id": None,
        "summary": (
            f"{card.get('asset_label')} 건은 아직 작업지시서가 생성되지 않았으며 운영 검토 후 발행 여부를 결정해야 합니다."
            if should_track
            else f"{card.get('asset_label')} 건은 현재 관찰 대상으로 남깁니다."
        ),
        "related_card_ids": [str(card.get("card_id"))],
        "evidence_refs": [],
    }


def stable_card_id(row: ReportJson) -> str:
    return stable_id("card", row)


def stable_window_id(row: ReportJson) -> str:
    return stable_id("window", row)


def stable_decision_id(row: ReportJson) -> str:
    return stable_id("priority", row)


def stable_id(prefix: str, row: ReportJson) -> str:
    key = "|".join(
        [
            prefix,
            str(row.get("manufacturer") or ""),
            str(row.get("substation_id") or ""),
            str(row.get("window_start") or ""),
            str(row.get("window_end") or ""),
        ]
    )
    return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, key)}"


def asset_label(substation_id: int | None, site: ReportJson) -> str:
    name = str(site.get("matched_name") or "").strip()
    if name and substation_id is not None:
        return f"{name} 열수급 지점 {substation_id}"
    if substation_id is not None:
        return f"{substation_id}번 열수급 지점"
    return "열수급 지점 확인 필요"


def location_label(site: ReportJson) -> str | None:
    village = str(site.get("village") or "").strip()
    dong = str(site.get("dong") or "").strip()
    address = str(site.get("road_address") or "").strip()
    parts = [part for part in (dong, village) if part]
    if parts:
        return " ".join(parts)
    return address or None


def clean_sensor_groups(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("\\", "|").replace("/", "|").split("|") if part.strip()]


def normalize_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in LEVEL_ORDER else "low"


def split_reasons(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "required"}


def to_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def float_or_zero(value: Any) -> float:
    result = to_float(value)
    return result if result is not None else 0.0


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def round_float(value: Any) -> float | None:
    number = to_float(value)
    return round(number, 2) if number is not None else None


def infer_season(value: Any) -> str | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    month = parsed.month
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "autumn"
