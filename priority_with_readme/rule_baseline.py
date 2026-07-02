"""rule v2 baseline 재구성 — mlmodel1 `priority_engine_v2_rule_based_tuned`.

출처: model_handoff/.../priority/priority_engine_tuned_metadata.json + 07_priority_engine.md.
priority 모델(LGBM 회귀)이 동일 holdout에서 이 baseline 이상이어야 채택.
"""

from __future__ import annotations

import pandas as pd

ENGINE_VERSION = "priority_engine_v2_rule_based_tuned"

RISK_LEVEL_POINTS = {"critical": 38.0, "high": 28.0, "medium": 15.0, "low": 4.0}
RISK_PROBABILITY_WEIGHT = 18.0
LEADTIME_BUCKET_POINTS = {"0-24h": 18.0, "1-3d": 10.0, "3-7d": 4.0}
ANOMALY_WEIGHT = 6.0
PRIORITY_LEVEL_RULES = [("urgent", 70.0), ("high", 52.0), ("medium", 34.0)]


def _confidence_multiplier(conf: float) -> float:
    if conf >= 0.8:
        return 1.0
    if conf >= 0.6:
        return 0.8
    return 0.6


def _history_adjustment(row) -> float:
    adj = 0.0
    task = row.get("days_since_last_task_event")
    anyev = row.get("days_since_last_any_event")
    fault = row.get("days_since_last_fault_event")
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
    risk_prob_comp = float(row.get("risk_probability", 0.0)) * RISK_PROBABILITY_WEIGHT
    bucket = str(row.get("predicted_lead_time_bucket", "3-7d"))
    leadtime_base = LEADTIME_BUCKET_POINTS.get(bucket, 4.0)
    mult = _confidence_multiplier(float(row.get("predicted_lead_time_confidence", 0.0)))
    leadtime_comp = leadtime_base * mult
    anomaly_comp = float(row.get("anomaly_score", 0.0)) * ANOMALY_WEIGHT
    history = _history_adjustment(row)
    return risk_base + risk_prob_comp + leadtime_comp + anomaly_comp + history


def score_frame(df: pd.DataFrame) -> pd.Series:
    return df.apply(score_row, axis=1).clip(lower=0.0)


def level_frame(scores: pd.Series) -> pd.Series:
    return scores.apply(_priority_level)
