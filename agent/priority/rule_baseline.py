"""Priority rule engine v2.

IF + LGBM risk + LGBM leadtime 체인의 `model_chain_output.csv`를 입력으로 받아
운영 우선순위 점수와 등급을 계산한다. 기존에는 priority LGBM 회귀 모델의 비교
baseline이었지만, proto runtime에서는 이 규칙을 실제 priority engine으로 사용한다.
"""

from __future__ import annotations

import pandas as pd

ENGINE_VERSION = "priority_engine_v2_rule_based_tuned"

RISK_LEVEL_POINTS = {"critical": 38.0, "high": 28.0, "medium": 15.0, "low": 4.0}
RISK_PROBABILITY_WEIGHT = 18.0
LEADTIME_BUCKET_POINTS = {"0-24h": 18.0, "1-3d": 10.0, "3-7d": 4.0}
ANOMALY_WEIGHT = 6.0
PRIORITY_LEVEL_RULES = [("urgent", 70.0), ("high", 52.0), ("medium", 34.0)]


def _to_float(value, default: float = 0.0) -> float:
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _confidence_multiplier(conf: float) -> float:
    if conf >= 0.8:
        return 1.0
    if conf >= 0.6:
        return 0.8
    return 0.6


def _history_adjustment(row) -> float:
    adj = 0.0
    task = pd.to_numeric(row.get("days_since_last_task_event"), errors="coerce")
    anyev = pd.to_numeric(row.get("days_since_last_any_event"), errors="coerce")
    fault = pd.to_numeric(row.get("days_since_last_fault_event"), errors="coerce")
    risk = str(row.get("risk_level_calibrated", "low"))
    if pd.notna(task):
        if task <= 7:
            adj -= 8
        elif task <= 30:
            adj -= 4
    if pd.notna(anyev):
        if anyev <= 7:
            adj -= 5
        elif anyev <= 30:
            adj -= 2
    if pd.notna(fault) and fault >= 365 and risk in ("high", "critical"):
        adj += 2
    return adj


def _priority_level(score: float) -> str:
    for level, threshold in PRIORITY_LEVEL_RULES:
        if score >= threshold:
            return level
    return "low"


def score_row(row) -> float:
    risk_level = str(row.get("risk_level_calibrated", "low"))
    risk_base = RISK_LEVEL_POINTS.get(risk_level, 4.0)
    risk_prob_comp = _to_float(row.get("risk_probability", 0.0)) * RISK_PROBABILITY_WEIGHT
    bucket = str(row.get("predicted_lead_time_bucket", "3-7d"))
    leadtime_base = LEADTIME_BUCKET_POINTS.get(bucket, 4.0)
    mult = _confidence_multiplier(_to_float(row.get("predicted_lead_time_confidence", 0.0)))
    leadtime_comp = leadtime_base * mult
    anomaly_comp = _to_float(row.get("anomaly_score", 0.0)) * ANOMALY_WEIGHT
    history = _history_adjustment(row)
    return risk_base + risk_prob_comp + leadtime_comp + anomaly_comp + history


def score_frame(df: pd.DataFrame) -> pd.Series:
    return df.apply(score_row, axis=1).clip(lower=0.0, upper=100.0)


def level_frame(scores: pd.Series) -> pd.Series:
    return scores.apply(_priority_level)
