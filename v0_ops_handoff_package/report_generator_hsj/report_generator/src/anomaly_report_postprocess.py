from __future__ import annotations

from typing import Any

from report_utils import ReportJson

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
