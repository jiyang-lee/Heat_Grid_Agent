from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "processed"
RISK_DIR = DATA_DIR / "ml_risk"
LEADTIME_DIR = DATA_DIR / "ml_leadtime"
PRIORITY_DIR = DATA_DIR / "ml_priority"
MODEL_DIR = PRIORITY_DIR / "models"

RISK_SCORES_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"
LEADTIME_SCORES_PATH = LEADTIME_DIR / "leadtime_bucket_scores_promoted.csv"

OUTPUT_PATH = PRIORITY_DIR / "priority_engine_scores_tuned.csv"
METADATA_PATH = MODEL_DIR / "priority_engine_tuned_metadata.json"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
ENGINE_VERSION = "priority_engine_v2_threshold48"

RISK_LEVEL_POINTS = {"critical": 38.0, "high": 28.0, "medium": 15.0, "low": 4.0}
LEADTIME_BUCKET_POINTS = {"0-24h": 18.0, "1-3d": 10.0, "3-7d": 4.0}
LEVEL_THRESHOLDS = {"urgent": 70.0, "high": 48.0, "medium": 34.0}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def leadtime_confidence_multiplier(conf: float) -> float:
    if conf >= 0.8:
        return 1.0
    if conf >= 0.6:
        return 0.8
    return 0.6


def anomaly_component(score: float) -> float:
    if pd.isna(score):
        return 0.0
    return clamp(score * 6.0, 0.0, 6.0)


def risk_probability_component(prob: float) -> float:
    if pd.isna(prob):
        return 0.0
    return clamp(prob * 18.0, 0.0, 18.0)


def history_adjustment(row: pd.Series) -> tuple[float, list[str]]:
    adj = 0.0
    reasons: list[str] = []
    task_days = pd.to_numeric(row.get("days_since_last_task_event"), errors="coerce")
    any_days = pd.to_numeric(row.get("days_since_last_any_event"), errors="coerce")
    fault_days = pd.to_numeric(row.get("days_since_last_fault_event"), errors="coerce")
    risk_level = row.get("risk_level_calibrated")

    if pd.notna(task_days):
        if task_days <= 7:
            adj -= 8.0
            reasons.append("recent_task_within_7d")
        elif task_days <= 30:
            adj -= 4.0
            reasons.append("recent_task_within_30d")

    if pd.notna(any_days):
        if any_days <= 7:
            adj -= 5.0
            reasons.append("recent_any_event_within_7d")
        elif any_days <= 30:
            adj -= 2.0
            reasons.append("recent_any_event_within_30d")

    if pd.notna(fault_days) and fault_days >= 365 and risk_level in {"high", "critical"}:
        adj += 2.0
        reasons.append("long_time_since_last_fault_and_high_risk")

    return adj, reasons


def priority_level(score: float) -> str:
    if score >= LEVEL_THRESHOLDS["urgent"]:
        return "urgent"
    if score >= LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def build_reason(row: pd.Series) -> str:
    parts: list[str] = []
    if row["risk_level_calibrated"] in {"high", "critical"}:
        parts.append(f"risk={row['risk_level_calibrated']}")
    if row["predicted_lead_time_bucket"] in {"0-24h", "1-3d"}:
        parts.append(f"leadtime={row['predicted_lead_time_bucket']}")
    if row["leadtime_confidence_multiplier"] < 1.0:
        parts.append("leadtime_confidence_damped")
    if row["history_adjustment_score"] != 0:
        parts.append("history_adjusted")
    if row["anomaly_component_score"] >= 4:
        parts.append("strong_anomaly")
    return "|".join(parts)


def main() -> None:
    PRIORITY_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    risk_df = pd.read_csv(RISK_SCORES_PATH)
    leadtime_df = pd.read_csv(LEADTIME_SCORES_PATH)

    risk_columns = KEY_COLUMNS + [
        "anomaly_score",
        "risk_score",
        "risk_probability",
        "risk_level_calibrated",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
    ]
    leadtime_columns = KEY_COLUMNS + [
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "leadtime_prob_0-24h",
        "leadtime_prob_1-3d",
        "leadtime_prob_3-7d",
        "lead_time_bucket_distance",
    ]
    risk_columns = [c for c in risk_columns if c in risk_df.columns]
    leadtime_columns = [c for c in leadtime_columns if c in leadtime_df.columns]

    merged = risk_df[risk_columns].merge(
        leadtime_df[leadtime_columns].drop_duplicates(subset=KEY_COLUMNS),
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )

    merged["risk_base_score"] = merged["risk_level_calibrated"].map(RISK_LEVEL_POINTS).fillna(0.0)
    merged["risk_probability_component_score"] = merged["risk_probability"].map(risk_probability_component)
    merged["leadtime_bucket_base_score"] = merged["predicted_lead_time_bucket"].map(LEADTIME_BUCKET_POINTS).fillna(0.0)
    merged["leadtime_confidence_multiplier"] = merged["predicted_lead_time_confidence"].fillna(0.0).map(leadtime_confidence_multiplier)
    merged["leadtime_component_score"] = merged["leadtime_bucket_base_score"] * merged["leadtime_confidence_multiplier"]
    merged["anomaly_component_score"] = merged["anomaly_score"].map(anomaly_component)

    history_scores = merged.apply(history_adjustment, axis=1)
    merged["history_adjustment_score"] = [score for score, _ in history_scores]
    merged["history_adjustment_reason"] = ["|".join(reasons) for _, reasons in history_scores]

    merged["priority_score_raw"] = (
        merged["risk_base_score"]
        + merged["risk_probability_component_score"]
        + merged["leadtime_component_score"]
        + merged["anomaly_component_score"]
        + merged["history_adjustment_score"]
    )
    merged["priority_score"] = merged["priority_score_raw"].map(lambda x: round(clamp(float(x), 0.0, 100.0), 4))
    merged["priority_level"] = merged["priority_score"].map(priority_level)
    merged["priority_reason"] = merged.apply(build_reason, axis=1)
    merged["engine_version"] = ENGINE_VERSION

    output_columns = KEY_COLUMNS + [
        "anomaly_score",
        "risk_score",
        "risk_probability",
        "risk_level_calibrated",
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "leadtime_prob_0-24h",
        "leadtime_prob_1-3d",
        "leadtime_prob_3-7d",
        "lead_time_bucket_distance",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
        "risk_base_score",
        "risk_probability_component_score",
        "leadtime_bucket_base_score",
        "leadtime_confidence_multiplier",
        "leadtime_component_score",
        "anomaly_component_score",
        "history_adjustment_score",
        "history_adjustment_reason",
        "priority_score",
        "priority_level",
        "priority_reason",
        "engine_version",
    ]
    output_columns = [c for c in output_columns if c in merged.columns]
    output_df = merged[output_columns].copy().sort_values(["priority_score", "risk_probability"], ascending=[False, False]).reset_index(drop=True)
    output_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    metadata = {
        "engine_version": ENGINE_VERSION,
        "input_risk_scores_path": str(RISK_SCORES_PATH),
        "input_leadtime_scores_path": str(LEADTIME_SCORES_PATH),
        "output_scores_path": str(OUTPUT_PATH),
        "risk_level_points": RISK_LEVEL_POINTS,
        "leadtime_bucket_points": LEADTIME_BUCKET_POINTS,
        "priority_level_rules": LEVEL_THRESHOLDS,
        "notes": [
            "compressed score scaling to reduce urgent saturation",
            "high priority threshold promoted from 52.0 to 48.0 after holdout threshold sweep",
            "long fault gap bonus applies only when risk is high or critical",
        ],
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(OUTPUT_PATH)
    print(METADATA_PATH)
    print()
    print(output_df["priority_level"].value_counts().to_string())
    print()
    print(output_df["priority_score"].describe().to_string())
    print()
    print(output_df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
