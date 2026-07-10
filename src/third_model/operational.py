from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .common import write_json


def _num(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _is_one(value: object) -> bool:
    numeric = pd.to_numeric(value, errors="coerce")
    return bool(pd.notna(numeric) and int(numeric) == 1)


def _best_anomaly_confirmed(row: pd.Series) -> bool:
    return _is_one(row.get("anomaly_event_label"))


def _evidence_confirmed(row: pd.Series) -> bool:
    return _best_anomaly_confirmed(row)


def _anomaly_evidence_event(row: pd.Series) -> int:
    return int(_evidence_confirmed(row))


def _anomaly_evidence_source(row: pd.Series) -> str:
    best = _best_anomaly_confirmed(row)
    if best:
        consensus = pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce")
        if pd.notna(consensus) and float(consensus) >= 2:
            return "iforest_0p90_and_mahalanobis_1p00_persistent"
        return "policy_criticality_confirmed"
    return "no_active_anomaly"


def _risk_level(row: pd.Series) -> str:
    value = row.get("risk_level_calibrated")
    if isinstance(value, str) and value:
        return value
    score = pd.to_numeric(row.get("risk_score", row.get("risk_probability", 0.0)), errors="coerce")
    score = 0.0 if pd.isna(score) else float(score)
    if score >= config.RISK_BASE_THRESHOLDS["critical"]:
        return "critical"
    if score >= config.RISK_BASE_THRESHOLDS["high"]:
        return "high"
    if score >= config.RISK_BASE_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _leadtime_urgency(row: pd.Series) -> float:
    for column in ["leadtime_urgency_score", "leadtime_urgency", "leadtime_near_term_probability"]:
        value = pd.to_numeric(row.get(column), errors="coerce")
        if pd.notna(value):
            return float(np.clip(value, 0.0, 1.0))
    bucket = row.get("predicted_lead_time_bucket", row.get("lead_time_bucket"))
    return {"0-24h": 1.0, "1-3d": 0.65, "3-7d": 0.35}.get(bucket, 0.2)


def _context_weight(row: pd.Series) -> float:
    """Context score used only for shadow priority sanity checking.

    Context depends only on the active anomaly evidence from the current M1
    anomaly baseline.
    """
    if _evidence_confirmed(row):
        return 0.75
    consensus = pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce")
    if pd.notna(consensus) and float(consensus) >= 2:
        return 0.60
    if pd.notna(consensus) and float(consensus) == 1:
        return 0.30
    return 0.10


def _shadow_priority(row: pd.Series) -> float:
    risk = pd.to_numeric(row.get("risk_score", row.get("risk_probability", 0.0)), errors="coerce")
    risk = 0.0 if pd.isna(risk) else float(np.clip(risk, 0.0, 1.0))
    lead = _leadtime_urgency(row)
    context = _context_weight(row)
    return 100.0 * (0.55 * risk + 0.30 * lead + 0.15 * context)


def _tier(score: float) -> str:
    if score >= 75:
        return "urgent"
    if score >= 55:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


COLUMN_GROUPS = {
    "manufacturer": ("기본정보", "제조사 또는 설비군"),
    "substation_id": ("기본정보", "기계실 또는 설비 ID"),
    "window_start": ("기본정보", "분석 window 시작 시각"),
    "window_end": ("기본정보", "분석 window 종료 시각"),
    "configuration_type": ("기본정보", "난방/급탕/서브회로 등 설비 구성"),
    "label": ("검증", "normal 또는 pre_fault 검증 라벨"),
    "fault_label": ("검증", "이벤트 설명 라벨"),
    "fault_event_id": ("검증", "검증 이벤트 묶음 ID"),
    "anomaly_ensemble_score": ("Anomaly", "IsolationForest와 Mahalanobis ratio를 가중합한 참고 이상 점수"),
    "anomaly_policy_score": ("Anomaly", "IF ratio 0.90과 Mahalanobis ratio 1.00 동시 충족 기준의 active 이상 점수"),
    "iforest_score_ratio": ("Anomaly", "train-normal q99 기준 IsolationForest ratio"),
    "mahalanobis_score_ratio": ("Anomaly", "train-normal q99 기준 Mahalanobis ratio"),
    "anomaly_consensus_count": ("Anomaly", "active threshold를 넘은 detector 개수"),
    "anomaly_criticality": ("Anomaly", "active 이상 점수 초과가 지속될 때 누적되는 counter"),
    "anomaly_event_label": ("Anomaly", "active policy criticality 기준 최종 anomaly event 여부"),
    "anomaly_evidence_event_label": ("Anomaly", "agent 설명에 쓰는 active anomaly event 여부"),
    "anomaly_evidence_source": ("Anomaly", "active anomaly 근거 출처"),
    "risk_probability": ("Risk", "기존 best risk 원 확률"),
    "risk_score": ("Risk", "priority와 운영 단계에 쓰는 위험 점수"),
    "risk_level_calibrated": ("Risk", "low/medium/high/critical 위험 단계"),
    "predicted_lead_time_bucket": ("Leadtime", "0-24h, 1-3d, 3-7d 중 leadtime 참고 구간"),
    "leadtime_urgency_score": ("Leadtime", "leadtime이 가까울수록 커지는 긴급도 점수"),
    "current_best_priority_score": ("Priority", "기존 best priority score"),
    "current_best_priority_level": ("Priority", "기존 best priority level"),
    "priority_score": ("Priority", "최종 agent용 M1 hybrid priority score"),
    "priority_level": ("Priority", "최종 agent용 priority level"),
    "priority_source": ("Priority", "최종 priority 생성 방식"),
    "priority_high_label": ("Priority", "최종 등급이 high 이상이면 1"),
    "m1_specialist_priority_score": ("M1 specialist", "M1 specialist gate 기반 priority score"),
    "m1_specialist_priority_level": ("M1 specialist", "M1 specialist priority level"),
    "m1_hybrid_priority_score": ("Priority", "current-best와 M1 specialist를 결합한 score"),
    "m1_hybrid_priority_level": ("Priority", "M1 hybrid priority level"),
    "m1_priority_agreement": ("Priority", "current-best와 M1 specialist 판단 일치 상태"),
    "m1_specialist_fault_probability": ("M1 specialist", "fault gate 확률"),
    "m1_specialist_task_probability": ("M1 specialist", "task gate 확률"),
    "m1_specialist_activity_probability": ("M1 specialist", "activity gate 확률"),
    "m1_specialist_pre_event_probability": ("M1 specialist", "pre-event logistic 확률"),
    "m1_specialist_primary_state": ("M1 specialist", "specialist가 본 대표 상태"),
    "m1_specialist_secondary_tags": ("M1 specialist", "보조 상태 tag"),
    "m1_specialist_fault_group": ("M1 specialist", "fault group 후보"),
    "m1_specialist_group_weight": ("M1 specialist", "fault group 운영 가중치"),
    "m1_specialist_gate_review_required": ("M1 specialist", "specialist gate 기준 검토 필요 여부"),
    "m1_specialist_gate_review_reasons": ("M1 specialist", "specialist gate 검토 사유"),
    "shadow_priority_score": ("설명보조", "별도 가중치로 계산한 참고 priority score"),
    "priority_policy_agreement": ("설명보조", "최종 priority와 shadow priority의 등급 일치성"),
    "operational_label": ("상태", "운영 상태 요약"),
    "primary_state": ("상태", "현재 대표 상태"),
    "review_required": ("설명제어", "사람 검토가 필요한지 여부"),
    "review_reasons": ("설명제어", "review_required가 켜진 이유 목록"),
    "trust_level": ("설명제어", "모델 근거 신뢰 수준"),
    "first_crossing_time": ("Leadtime", "이벤트 구간에서 처음 위험 신호가 켜진 시각"),
    "stable_crossing_time": ("Leadtime", "위험 신호가 안정적으로 유지되기 시작한 시각"),
    "stable_crossing_lead_hours": ("Leadtime", "stable crossing이 이벤트보다 몇 시간 앞섰는지"),
    "why_reason": ("설명제어", "주요 판단 근거를 합친 설명 문자열"),
    "recommended_action": ("설명제어", "현재 상태에 대한 추천 행동 문장"),
}


FINAL_AGENT_CARD_GROUPS = {
    "기본 key / 설비 식별": [
        "manufacturer",
        "substation_id",
        "window_start",
        "window_end",
        "configuration_type",
    ],
    "검증 라벨 / 보고용 ground truth": ["label", "fault_label", "fault_event_id"],
    "Anomaly evidence / M1 anomaly 모델": [
        "anomaly_ensemble_score",
        "anomaly_policy_score",
        "iforest_score_ratio",
        "mahalanobis_score_ratio",
        "anomaly_consensus_count",
        "anomaly_criticality",
        "anomaly_event_label",
        "anomaly_evidence_event_label",
        "anomaly_evidence_source",
    ],
    "Current-best risk 모델": ["risk_probability", "risk_score", "risk_level_calibrated"],
    "Current-best leadtime / crossing evidence": [
        "predicted_lead_time_bucket",
        "leadtime_urgency_score",
        "first_crossing_time",
        "stable_crossing_time",
        "stable_crossing_lead_hours",
    ],
    "Current-best priority baseline": ["current_best_priority_score", "current_best_priority_level"],
    "최종 M1 hybrid priority contract": [
        "priority_score",
        "priority_level",
        "priority_source",
        "priority_high_label",
        "m1_hybrid_priority_score",
        "m1_hybrid_priority_level",
        "m1_priority_agreement",
    ],
    "M1 specialist 단독 evidence / hybrid input": [
        "m1_specialist_priority_score",
        "m1_specialist_priority_level",
        "m1_specialist_fault_probability",
        "m1_specialist_task_probability",
        "m1_specialist_activity_probability",
        "m1_specialist_pre_event_probability",
        "m1_specialist_primary_state",
        "m1_specialist_secondary_tags",
        "m1_specialist_fault_group",
        "m1_specialist_group_weight",
        "m1_specialist_gate_review_required",
        "m1_specialist_gate_review_reasons",
    ],
    "Agent 상태 / 설명 제어 / action": [
        "shadow_priority_score",
        "priority_policy_agreement",
        "operational_label",
        "primary_state",
        "review_required",
        "review_reasons",
        "trust_level",
        "why_reason",
        "recommended_action",
    ],
}

FINAL_AGENT_GROUP_ORIGIN = {
    "기본 key / 설비 식별": "metadata / window key",
    "검증 라벨 / 보고용 ground truth": "검증 라벨 전용",
    "Anomaly evidence / M1 anomaly 모델": "M1 anomaly 모델",
    "Current-best risk 모델": "current-best risk 모델 / score bridge",
    "Current-best leadtime / crossing evidence": "current-best leadtime 및 crossing 근거",
    "Current-best priority baseline": "current-best priority engine 기준값",
    "최종 M1 hybrid priority contract": "최종 agent 계약: current-best 0.65 + M1 specialist 0.35",
    "M1 specialist 단독 evidence / hybrid input": "M1 specialist 단독/병렬 근거, hybrid 입력",
    "Agent 상태 / 설명 제어 / action": "agent 설명 및 운영 정책 계층",
}

FINAL_AGENT_GROUP_USAGE = {
    "기본 key / 설비 식별": "행 식별과 화면 표시 key",
    "검증 라벨 / 보고용 ground truth": "보고/평가 전용이며 운영 추론 입력으로 사용하지 않음",
    "Anomaly evidence / M1 anomaly 모델": "정상 패턴 이탈 근거이며 단독 fault classifier가 아님",
    "Current-best risk 모델": "supervised risk 중심 근거",
    "Current-best leadtime / crossing evidence": "긴급도와 시점 참고 근거이며 정확한 고장 시각 단정값이 아님",
    "Current-best priority baseline": "추적성과 hybrid 비교를 위해 보존한 기준 priority",
    "최종 M1 hybrid priority contract": "agent UI/API가 정렬과 level 판단에 우선 사용하는 필드",
    "M1 specialist 단독 evidence / hybrid input": "M1-only 근거 branch이며 risk/leadtime 대체값이 아님",
    "Agent 상태 / 설명 제어 / action": "표시, review gating, 사유 문구, 권장 조치",
}

PARALLEL_AGENT_CARD_GROUPS = {
    "M1 parallel key / validation labels": [
        "manufacturer",
        "substation_id",
        "window_start",
        "window_end",
        "label",
        "fault_label",
        "fault_event_id",
    ],
    "M1 compact window coverage": [
        "m1_specialist_model_scope",
        "m1_specialist_compact_window_start",
        "m1_specialist_compact_window_end",
        "m1_specialist_sample_count",
        "m1_specialist_expected_count",
        "m1_specialist_coverage_rate",
    ],
    "M1 gate probability / prediction": [
        "m1_specialist_fault_probability",
        "m1_specialist_task_probability",
        "m1_specialist_activity_probability",
        "m1_specialist_pre_event_probability",
        "m1_specialist_fault_prediction",
        "m1_specialist_task_prediction",
        "m1_specialist_activity_prediction",
        "m1_specialist_pre_event_prediction",
    ],
    "M1 standalone priority / review evidence": [
        "m1_specialist_primary_state",
        "m1_specialist_secondary_tags",
        "m1_specialist_fault_group",
        "m1_specialist_group_weight",
        "m1_specialist_leadtime_urgency",
        "m1_specialist_priority_score",
        "m1_specialist_gate_review_required",
        "m1_specialist_gate_review_reasons",
    ],
}


def _reverse_groups(groups: dict[str, list[str]]) -> dict[str, str]:
    return {column: group for group, columns in groups.items() for column in columns}


def _write_agent_column_group_docs() -> None:
    final_columns = config.AGENT_OUTPUT_COLUMNS
    final_lookup = _reverse_groups(FINAL_AGENT_CARD_GROUPS)
    missing = [column for column in final_columns if column not in final_lookup]
    if missing:
        raise ValueError(f"Missing final agent column group definitions: {missing}")

    rows: list[dict[str, object]] = []
    for idx, column in enumerate(final_columns, 1):
        group = final_lookup[column]
        rows.append(
            {
                "card_file": "output/agent_priority_card.csv; output/agent/m1_agent_priority_card.csv",
                "card_role": "final_hybrid_agent_card",
                "column_order": idx,
                "column_name": column,
                "category": group,
                "model_origin": FINAL_AGENT_GROUP_ORIGIN[group],
                "is_final_agent_contract": "Y"
                if group == "최종 M1 hybrid priority contract"
                or column in {"manufacturer", "substation_id", "window_start", "window_end"}
                else "N",
                "is_m1_standalone_evidence": "Y" if group == "M1 specialist 단독 evidence / hybrid input" else "N",
                "usage_note": FINAL_AGENT_GROUP_USAGE[group],
            }
        )

    parallel_columns: list[str] = []
    if config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH.exists():
        parallel_columns = list(pd.read_csv(config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH, nrows=0).columns)
    parallel_lookup = _reverse_groups(PARALLEL_AGENT_CARD_GROUPS)
    missing_parallel = [column for column in parallel_columns if column not in parallel_lookup]
    if missing_parallel:
        raise ValueError(f"Missing M1 parallel column group definitions: {missing_parallel}")
    for idx, column in enumerate(parallel_columns, 1):
        group = parallel_lookup[column]
        rows.append(
            {
                "card_file": "output/agent/m1_specialist_parallel_agent_card.csv",
                "card_role": "m1_specialist_parallel_card",
                "column_order": idx,
                "column_name": column,
                "category": group,
                "model_origin": "M1 specialist 단독/병렬 모델",
                "is_final_agent_contract": "N",
                "is_m1_standalone_evidence": "Y",
                "usage_note": "M1-only 병렬 근거 card. 1252개 M1 범위를 보지만 최종 hybrid agent 계약은 아님",
            }
        )

    pd.DataFrame(rows).to_csv(config.AGENT_CARD_COLUMN_GROUPS_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)

    final_rows = final_cols = 0
    if config.AGENT_CARD_PATH.exists():
        final_rows, final_cols = pd.read_csv(config.AGENT_CARD_PATH).shape
    parallel_rows = parallel_cols = 0
    if config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH.exists():
        parallel_rows, parallel_cols = pd.read_csv(config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH).shape

    lines = [
        "# Agent Card 컬럼 분류",
        "",
        "## 결론",
        "",
        "",
        "",
        "- 최종 agent가 우선 읽는 active contract 컬럼은 `priority_score`, `priority_level`, `priority_source`, `priority_high_label`이다. 현재 `priority_score`는 M1 hybrid priority다.",
        "- M1 단독 모델 계열 컬럼은 `m1_specialist_*`로 남아 있으며, 최종 priority에 35% 반영되는 근거 branch다. risk/leadtime 대체 모델로 설명하지 않는다.",
        "",
        "## 최종 Hybrid Agent Card 55개 컬럼",
        "",
        "| 분류 | 컬럼수 | 모델/출처 | 용도 |",
        "|---|---:|---|---|",
    ]
    lines[4] = (
        f"- Final agent cards `output/agent_priority_card.csv` and "
        f"`output/agent/m1_agent_priority_card.csv` have {final_rows} rows / {final_cols} columns."
    )
    lines[5] = (
        f"- `output/agent/m1_specialist_parallel_agent_card.csv` has {parallel_rows} rows / "
        f"{parallel_cols} columns and is M1-only evidence, not the final hybrid ordering contract."
    )
    lines[9] = f"## Final Hybrid Agent Card {final_cols} columns"
    for group, columns in FINAL_AGENT_CARD_GROUPS.items():
        lines.append(
            f"| {group} | {len(columns)} | {FINAL_AGENT_GROUP_ORIGIN[group]} | {FINAL_AGENT_GROUP_USAGE[group]} |"
        )
    lines.append("")
    for group, columns in FINAL_AGENT_CARD_GROUPS.items():
        lines.extend([f"### {group} ({len(columns)})", "", ", ".join(f"`{column}`" for column in columns), ""])
    lines.extend(["## M1 Specialist 병렬 Card 29개 컬럼", "", "| 분류 | 컬럼수 | 설명 |", "|---|---:|---|"])
    for group, columns in PARALLEL_AGENT_CARD_GROUPS.items():
        lines.append(f"| {group} | {len(columns)} | M1 단독/병렬 근거 card 전용 |")
    lines.append("")
    for group, columns in PARALLEL_AGENT_CARD_GROUPS.items():
        lines.extend([f"### {group} ({len(columns)})", "", ", ".join(f"`{column}`" for column in columns), ""])
    lines.extend(
        [
            "## 주의",
            "",
            "- `label`, `fault_label`, `fault_event_id`는 검증/보고용 라벨이다. 운영 추론 입력으로 쓰면 안 된다.",
            "- anomaly 컬럼은 정상 패턴 이탈 근거다. 단독 fault classifier로 말하지 않는다.",
            "- current-best risk/leadtime 컬럼은 기존 best score bridge에서 온 핵심 근거다.",
            "- M1 specialist 단독 컬럼은 M1-only 근거이며, 최종 agent ordering은 hybrid `priority_score`를 따른다.",
            "",
        ]
    )
    lines[-1] = (
        f"- `m1_specialist_parallel_agent_card.csv` covers {parallel_rows} M1 windows. "
        f"The final hybrid card currently has {final_rows} rows after joining with the current-best body."
    )
    config.AGENT_CARD_COLUMN_GROUPS_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_agent_contract_docs() -> None:
    rows = []
    for column in config.AGENT_OUTPUT_COLUMNS:
        group, meaning = COLUMN_GROUPS.get(column, ("기타", "agent contract field"))
        rows.append(
            {
                "column_name": column,
                "korean_name": meaning.split(" 또는 ")[0],
                "group": group,
                "meaning": meaning,
                "agent_usage": "설명과 우선순위 판단에 필요한 경우 사용",
                "caution": "검증용 라벨은 운영 추론 입력으로 사용하지 않음" if group == "검증" else "",
            }
        )
    dictionary = pd.DataFrame(rows)
    dictionary.to_csv(config.AGENT_CARD_COLUMN_DICTIONARY_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    lines = [
        "# Agent Card Value Mapping",
        "",
        "## Priority",
        "",
        "- `priority_score`: 최종 M1 hybrid 우선순위 점수다.",
        "- `priority_level`: `urgent`, `high`, `medium`, `low` 중 하나다.",
        "- `priority_source`: priority 생성 공식을 나타낸다.",
        "",
        "## Risk",
        "",
        "- `risk_level_calibrated`: `critical`, `high`, `medium`, `low` 중 하나다.",
        "- `risk_score`: 높을수록 고장/정비 이벤트 전 위험이 크다고 본다.",
        "",
        "## Leadtime",
        "",
        "- `predicted_lead_time_bucket`: `0-24h`, `1-3d`, `3-7d` 중 하나다.",
        "- 이 값은 고장 시각 단정이 아니라 우선순위 참고 신호다.",
        "",
        "## Anomaly",
        "",
        "- `anomaly_policy_score`: IF ratio 0.90과 Mahalanobis ratio 1.00을 모두 넘는지 보는 active 이상 점수다.",
        "- `anomaly_event_label`: active policy criticality 기준 event 여부다.",
        "- `anomaly_evidence_source`: 어떤 active anomaly 근거가 쓰였는지 설명한다.",
        "",
        "## Specialist",
        "",
        "- `m1_specialist_*`: M1 전용 gate 기반 보조 근거다.",
        "- specialist 값은 risk/leadtime을 대체하지 않고 최종 priority 설명에 보태는 신호다.",
        "",
        "## Review",
        "",
        "- `review_required == True`: 근거 충돌 또는 애매한 신호가 있어 사람이 확인해야 한다.",
        "- `review_reasons`: review가 필요한 이유 목록이다.",
    ]
    config.AGENT_CARD_VALUE_MAPPING_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _write_agent_column_group_docs()


def _priority_agreement(row: pd.Series) -> str:
    best = str(row.get("priority_level", "low"))
    shadow = _tier(float(row.get("shadow_priority_score", 0.0)))
    strong = {"urgent", "high"}
    if best == shadow:
        return "same_tier"
    if best in strong and shadow in strong:
        return "same_high_zone"
    if best in strong and shadow not in strong:
        return "best_high_shadow_low"
    if best not in strong and shadow in strong:
        return "shadow_high_best_low"
    return "different_noncritical"


def _review_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    risk_score = pd.to_numeric(row.get("risk_score", row.get("risk_probability", 0.0)), errors="coerce")
    anomaly = pd.to_numeric(row.get("anomaly_policy_score", row.get("anomaly_ensemble_score")), errors="coerce")
    crit = pd.to_numeric(row.get("anomaly_criticality"), errors="coerce")
    risk_high = _risk_level(row) in {"high", "critical"}
    anomaly_confirmed = _evidence_confirmed(row)

    if pd.notna(risk_score) and abs(float(risk_score) - config.RISK_BASE_THRESHOLDS["high"]) <= 0.05:
        reasons.append("near_risk_high_threshold")
    if pd.notna(anomaly) and 0.9 <= float(anomaly) <= 1.1:
        reasons.append("near_anomaly_threshold")
    if risk_high and not anomaly_confirmed:
        reasons.append("risk_high_but_anomaly_not_confirmed")
    if not risk_high and anomaly_confirmed:
        reasons.append("anomaly_confirmed_but_risk_low")
    if pd.notna(crit) and float(crit) >= 24:
        reasons.append("long_persistent_anomaly")
    if str(row.get("label")) == "normal" and (risk_high or anomaly_confirmed):
        reasons.append("hard_normal_review")
    return reasons


def _operational_label(row: pd.Series) -> str:
    if _risk_level(row) in {"high", "critical"} or _evidence_confirmed(row):
        return "predictive_fault_risk"
    if pd.to_numeric(row.get("maintenance_related"), errors="coerce") == 1:
        return "maintenance_context"
    return "normal_monitor"


def _trust_level(row: pd.Series) -> str:
    risk_high = _risk_level(row) in {"high", "critical"}
    anomaly_event = _evidence_confirmed(row)
    if risk_high and anomaly_event and not bool(row.get("review_required")):
        return "high"
    if risk_high and anomaly_event:
        return "medium_high"
    if risk_high or anomaly_event:
        return "medium"
    if bool(row.get("review_required")):
        return "low_review"
    return "low"


def _crossing_audit(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    working = frame.copy()
    working["window_end_dt"] = pd.to_datetime(working["window_end"], errors="coerce")
    alarm = (
        _num(working, "anomaly_evidence_event_label").ge(1)
        | _num(working, "risk_score", _num(working, "risk_probability").median()).ge(config.RISK_BASE_THRESHOLDS["high"])
    )
    working["_alarm"] = alarm.astype(int)
    if "fault_event_id" not in working.columns:
        return pd.DataFrame(
            columns=[
                "manufacturer",
                "substation_id",
                "fault_event_id",
                "first_crossing_time",
                "stable_crossing_time",
                "stable_crossing_lead_hours",
            ]
        )
    event_frame = working.loc[working["fault_event_id"].notna()].copy()
    if event_frame.empty:
        return pd.DataFrame(
            columns=[
                "manufacturer",
                "substation_id",
                "fault_event_id",
                "first_crossing_time",
                "stable_crossing_time",
                "stable_crossing_lead_hours",
            ]
        )
    for key, group in event_frame.groupby(["manufacturer", "substation_id", "fault_event_id"], dropna=True, sort=False):
        group = group.sort_values("window_end_dt")
        event_time = group["window_end_dt"].max()
        alarm_rows = group.loc[group["_alarm"].eq(1)]
        first_time = alarm_rows["window_end_dt"].min() if not alarm_rows.empty else pd.NaT
        stable_time = pd.NaT
        if not alarm_rows.empty:
            for _, row in alarm_rows.iterrows():
                tail = group.loc[group["window_end_dt"].ge(row["window_end_dt"])]
                if int(tail["_alarm"].min()) == 1:
                    stable_time = row["window_end_dt"]
                    break
        lead_hours = float((event_time - stable_time).total_seconds() / 3600.0) if pd.notna(stable_time) else np.nan
        rows.append(
            {
                "manufacturer": key[0],
                "substation_id": key[1],
                "fault_event_id": key[2],
                "first_crossing_time": "" if pd.isna(first_time) else str(first_time),
                "stable_crossing_time": "" if pd.isna(stable_time) else str(stable_time),
                "stable_crossing_lead_hours": lead_hours,
            }
        )
    return pd.DataFrame(rows)


def _why_reason(row: pd.Series) -> str:
    parts: list[str] = [f"risk={_risk_level(row)}"]
    evidence_source = str(row.get("anomaly_evidence_source", ""))
    if _evidence_confirmed(row):
        parts.append(f"anomaly_evidence={evidence_source}")
    elif pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce") >= 2:
        parts.append("IF ratio >= 0.90 and Mahalanobis ratio >= 1.00")
    elif pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce") == 1:
        parts.append("partial anomaly detector evidence")

    lead = row.get("predicted_lead_time_bucket")
    if isinstance(lead, str) and lead:
        parts.append(f"leadtime_ref={lead}")
    if row.get("review_required"):
        parts.append(f"review={row.get('review_reasons')}")
    return "; ".join(parts)


def _recommended_action(row: pd.Series) -> str:
    priority = str(row.get("priority_level", "low"))
    review = bool(row.get("review_required"))
    trust = str(row.get("trust_level", "low"))
    if review and priority in {"urgent", "high"}:
        return "우선 검토: 모델 근거는 강하지만 review flag가 있으므로 최근 작업 이력, 라벨, 데이터 결측을 함께 확인한다."
    if priority == "urgent" and trust in {"high", "medium_high"}:
        return "즉시 확인: anomaly와 risk가 함께 강하므로 설비 상태 확인 후 현장 점검 후보로 올린다."
    if priority == "high":
        return "우선순위 점검: 최근 추세와 anomaly 지속 여부를 확인한다."
    if priority == "medium":
        return "계획 모니터링: 다음 window에서도 지속되는지 확인한다."
    return "일반 모니터링: 자동 출동 알람 대상은 아니다."


def build_agent_card() -> pd.DataFrame:
    frame = pd.read_csv(config.MERGED_SCORES_PATH).copy()
    frame["anomaly_evidence_event_label"] = frame.apply(_anomaly_evidence_event, axis=1)
    frame["anomaly_evidence_source"] = frame.apply(_anomaly_evidence_source, axis=1)
    frame["risk_level_calibrated"] = frame.apply(_risk_level, axis=1)
    frame["leadtime_urgency_score"] = frame.apply(_leadtime_urgency, axis=1)
    frame["shadow_priority_score"] = frame.apply(_shadow_priority, axis=1)
    frame["priority_policy_agreement"] = frame.apply(_priority_agreement, axis=1)
    review_lists = frame.apply(_review_reasons, axis=1)
    frame["review_reasons"] = review_lists.map(lambda items: "|".join(items))
    frame["review_required"] = review_lists.map(lambda items: len(items) > 0)
    frame["primary_state"] = frame.apply(_operational_label, axis=1)
    frame["operational_label"] = frame["primary_state"]
    frame["trust_level"] = frame.apply(_trust_level, axis=1)
    crossing = _crossing_audit(frame)
    if not crossing.empty:
        frame = frame.merge(
            crossing,
            on=["manufacturer", "substation_id", "fault_event_id"],
            how="left",
            validate="many_to_one",
        )
    else:
        frame["first_crossing_time"] = ""
        frame["stable_crossing_time"] = ""
        frame["stable_crossing_lead_hours"] = np.nan
    frame["why_reason"] = frame.apply(_why_reason, axis=1)
    frame["recommended_action"] = frame.apply(_recommended_action, axis=1)

    for column in config.AGENT_OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    agent = frame[config.AGENT_OUTPUT_COLUMNS].copy()
    agent.to_csv(config.AGENT_CARD_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    write_json(
        config.STATE_CARD_SCHEMA_PATH,
        {
            "source_mix": {
                "current_best": "risk/leadtime/priority body and active M1 Mahalanobis+IsolationForest anomaly policy",
                "M1_specialist_parallel": "fault/task/activity/pre-event gate evidence and hybrid priority promotion",
                "operational_layer": "state card, review flags, stable crossing, shadow priority, action text",
                "outputs_ver2_hsj": "threshold sweep style only; no formal risk_level contract adopted",
            },
            "columns": config.AGENT_OUTPUT_COLUMNS,
        },
    )
    write_agent_contract_docs()
    return agent
