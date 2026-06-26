from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
MODEL_DIR = ML_RISK_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
CALIBRATED_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores_calibrated.csv"
RISK_MODEL_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

OUTPUT_GROUP_SUMMARY_PATH = ML_RISK_DIR / "holdout_false_negative_group_summary.csv"
OUTPUT_LEVEL_SUMMARY_PATH = ML_RISK_DIR / "holdout_false_negative_level_summary.csv"
OUTPUT_SCORE_BAND_PATH = ML_RISK_DIR / "holdout_false_negative_score_band_summary.csv"
OUTPUT_LEADTIME_PATH = ML_RISK_DIR / "holdout_false_negative_leadtime_summary.csv"
OUTPUT_THRESHOLD_WINDOW_PATH = ML_RISK_DIR / "holdout_false_negative_threshold_window.csv"
OUTPUT_FEATURE_DIFF_PATH = ML_RISK_DIR / "holdout_false_negative_group_feature_diff.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
MEDIUM_THRESHOLD = 0.22
HIGH_THRESHOLD = 0.44
CRITICAL_THRESHOLD = 0.90

FOCUS_FEATURES = [
    "anomaly_score",
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
    "network_temperature_gap__mean",
    "p_net_return_temperature__mean",
    "p_net_return_temperature__max",
    "p_net_supply_temperature__mean",
    "p_net_supply_temperature__max",
    "s_dhw_upper_storage_temperature__last",
    "s_dhw_upper_storage_temperature__max",
    "day_of_year",
    "doy_sin",
    "doy_cos",
]


def load_frame() -> pd.DataFrame:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    scores_df = pd.read_csv(CALIBRATED_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        "configuration_type",
        PRIMARY_SPLIT_COLUMN,
        "risk_probability",
        "risk_level",
        "risk_level_calibrated",
        "fault_label",
        "fault_event_id",
        "estimated_lead_time_hours",
        "lead_time_bucket",
        "anomaly_score",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
    ]
    feature_columns = [column for column in metadata["model_feature_columns"] if column in trainable_windows.columns]
    merge_feature_columns = [column for column in FOCUS_FEATURES if column in feature_columns]
    merge_columns = [column for column in merge_columns if column in scores_df.columns]

    modeling_df = trainable_windows[KEY_COLUMNS + merge_feature_columns].merge(
        scores_df[merge_columns].drop_duplicates(subset=KEY_COLUMNS),
        on=KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_risk"),
    )
    for base_name in ["label", "configuration_type", PRIMARY_SPLIT_COLUMN]:
        risk_name = f"{base_name}_risk"
        if base_name not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: base_name})
    return modeling_df


def score_band(score: float) -> str:
    if score < MEDIUM_THRESHOLD:
        return "below_medium"
    if score < 0.30:
        return "medium_0.22_0.30"
    if score < 0.36:
        return "medium_0.30_0.36"
    if score < HIGH_THRESHOLD:
        return "medium_0.36_0.44"
    if score < 0.60:
        return "high_0.44_0.60"
    if score < CRITICAL_THRESHOLD:
        return "high_0.60_0.90"
    return "critical_0.90_plus"


def main() -> None:
    modeling_df = load_frame()

    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    pre_fault_mask = modeling_df["label"].eq("pre_fault")
    predicted_positive_mask = modeling_df["risk_level_calibrated"].isin(["high", "critical"])

    fn_df = modeling_df.loc[holdout_mask & pre_fault_mask & (~predicted_positive_mask)].copy()
    tp_df = modeling_df.loc[holdout_mask & pre_fault_mask & predicted_positive_mask].copy()

    fn_df["group_key"] = fn_df["manufacturer"].astype(str) + " | " + fn_df["configuration_type"].astype(str)
    tp_df["group_key"] = tp_df["manufacturer"].astype(str) + " | " + tp_df["configuration_type"].astype(str)
    fn_df["score_band"] = fn_df["risk_probability"].map(score_band)
    tp_df["score_band"] = tp_df["risk_probability"].map(score_band)

    group_summary = (
        fn_df.groupby(["manufacturer", "configuration_type", "group_key"], dropna=False)
        .agg(
            false_negative_count=("substation_id", "size"),
            substation_count=("substation_id", "nunique"),
            fault_event_count=("fault_event_id", "nunique"),
            mean_risk_probability=("risk_probability", "mean"),
            median_risk_probability=("risk_probability", "median"),
            mean_anomaly_score=("anomaly_score", "mean"),
            mean_estimated_lead_time_hours=("estimated_lead_time_hours", "mean"),
        )
        .reset_index()
        .sort_values(["false_negative_count", "mean_risk_probability"], ascending=[False, False])
        .reset_index(drop=True)
    )

    level_summary = (
        fn_df.groupby(["risk_level_calibrated"], dropna=False)
        .agg(
            false_negative_count=("substation_id", "size"),
            mean_risk_probability=("risk_probability", "mean"),
            min_risk_probability=("risk_probability", "min"),
            max_risk_probability=("risk_probability", "max"),
        )
        .reset_index()
        .sort_values("false_negative_count", ascending=False)
        .reset_index(drop=True)
    )

    score_band_summary = (
        fn_df.groupby(["score_band"], dropna=False)
        .agg(
            false_negative_count=("substation_id", "size"),
            mean_risk_probability=("risk_probability", "mean"),
        )
        .reset_index()
        .sort_values("false_negative_count", ascending=False)
        .reset_index(drop=True)
    )

    leadtime_summary = (
        fn_df.groupby(["lead_time_bucket"], dropna=False)
        .agg(
            false_negative_count=("substation_id", "size"),
            mean_risk_probability=("risk_probability", "mean"),
            mean_estimated_lead_time_hours=("estimated_lead_time_hours", "mean"),
        )
        .reset_index()
        .sort_values("false_negative_count", ascending=False)
        .reset_index(drop=True)
    )

    threshold_window = fn_df.loc[
        fn_df["risk_probability"].between(MEDIUM_THRESHOLD, HIGH_THRESHOLD, inclusive="left"),
        [
            "manufacturer",
            "configuration_type",
            "substation_id",
            "window_start",
            "window_end",
            "fault_event_id",
            "fault_label",
            "lead_time_bucket",
            "estimated_lead_time_hours",
            "risk_probability",
            "risk_level_calibrated",
            "anomaly_score",
            "days_since_last_fault_event",
            "days_since_last_task_event",
            "days_since_last_any_event",
        ],
    ].copy()
    threshold_window = threshold_window.sort_values(
        ["risk_probability", "estimated_lead_time_hours"],
        ascending=[False, True],
    ).reset_index(drop=True)

    feature_diff_rows: list[dict] = []
    for feature in [column for column in FOCUS_FEATURES if column in fn_df.columns and column in tp_df.columns]:
        fn_numeric = pd.to_numeric(fn_df[feature], errors="coerce")
        tp_numeric = pd.to_numeric(tp_df[feature], errors="coerce")
        feature_diff_rows.append(
            {
                "feature": feature,
                "fn_mean": float(fn_numeric.mean()),
                "tp_mean": float(tp_numeric.mean()),
                "tp_minus_fn": float(tp_numeric.mean() - fn_numeric.mean()),
                "fn_median": float(fn_numeric.median()),
                "tp_median": float(tp_numeric.median()),
                "tp_minus_fn_median": float(tp_numeric.median() - fn_numeric.median()),
            }
        )
    feature_diff = pd.DataFrame(feature_diff_rows).sort_values(
        "tp_minus_fn", ascending=False
    ).reset_index(drop=True)

    group_summary.to_csv(OUTPUT_GROUP_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    level_summary.to_csv(OUTPUT_LEVEL_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    score_band_summary.to_csv(OUTPUT_SCORE_BAND_PATH, index=False, encoding="utf-8-sig")
    leadtime_summary.to_csv(OUTPUT_LEADTIME_PATH, index=False, encoding="utf-8-sig")
    threshold_window.to_csv(OUTPUT_THRESHOLD_WINDOW_PATH, index=False, encoding="utf-8-sig")
    feature_diff.to_csv(OUTPUT_FEATURE_DIFF_PATH, index=False, encoding="utf-8-sig")

    print(OUTPUT_GROUP_SUMMARY_PATH)
    print(OUTPUT_LEVEL_SUMMARY_PATH)
    print(OUTPUT_SCORE_BAND_PATH)
    print(OUTPUT_LEADTIME_PATH)
    print(OUTPUT_THRESHOLD_WINDOW_PATH)
    print(OUTPUT_FEATURE_DIFF_PATH)
    print()
    print("[group summary]")
    print(group_summary.to_string(index=False))
    print()
    print("[level summary]")
    print(level_summary.to_string(index=False))
    print()
    print("[leadtime summary]")
    print(leadtime_summary.to_string(index=False))
    print()
    print("[feature diff]")
    print(feature_diff.head(20).to_string(index=False))


if __name__ == "__main__":
    main()

