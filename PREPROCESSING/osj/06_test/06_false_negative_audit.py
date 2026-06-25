from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
MODEL_DIR = ML_RISK_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
CALIBRATED_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores_calibrated.csv"
RISK_MODEL_PATH = MODEL_DIR / "lightgbm_risk_model.joblib"
RISK_MODEL_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

OUTPUT_ROWS_PATH = ML_RISK_DIR / "holdout_false_negative_rows.csv"
OUTPUT_FEATURE_PATH = ML_RISK_DIR / "holdout_false_negative_feature_summary.csv"
OUTPUT_COMPARE_PATH = ML_RISK_DIR / "holdout_false_negative_vs_true_positive_compare.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"


def load_frame() -> tuple[pd.DataFrame, list[str], object, pd.DataFrame]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    scores_df = pd.read_csv(CALIBRATED_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    model = joblib.load(RISK_MODEL_PATH)

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        "configuration_type",
        PRIMARY_SPLIT_COLUMN,
        "risk_probability",
        "risk_level",
        "risk_level_calibrated",
        "main_abnormal_features",
        "model_explanation_features",
        "fault_label",
        "fault_event_id",
        "estimated_lead_time_hours",
        "lead_time_bucket",
        "anomaly_score",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
    ]
    merge_columns = [column for column in merge_columns if column in scores_df.columns]

    modeling_df = trainable_windows.merge(
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

    feature_columns = metadata["model_feature_columns"]
    for column in feature_columns:
        risk_name = f"{column}_risk"
        if column not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: column})

    x_all = modeling_df[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    if x_all.isna().any().any():
        missing_summary = x_all.isna().sum()
        missing_summary = missing_summary[missing_summary > 0].sort_values(ascending=False)
        raise ValueError("False negative audit input contains missing values:\n" + str(missing_summary.head(20)))
    return modeling_df, feature_columns, model, x_all


def top_positive_features(row: pd.Series, top_n: int = 10) -> str:
    ordered = row.sort_values(ascending=False)
    ordered = ordered[ordered > 0]
    return "|".join(ordered.head(top_n).index.tolist())


def top_negative_features(row: pd.Series, top_n: int = 10) -> str:
    ordered = row.sort_values(ascending=True)
    ordered = ordered[ordered < 0]
    return "|".join(ordered.head(top_n).index.tolist())


def main() -> None:
    modeling_df, feature_columns, model, x_all = load_frame()

    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    pre_fault_mask = modeling_df["label"].eq("pre_fault")
    predicted_positive_mask = modeling_df["risk_level_calibrated"].isin(["high", "critical"])

    fn_mask = holdout_mask & pre_fault_mask & (~predicted_positive_mask)
    tp_mask = holdout_mask & pre_fault_mask & predicted_positive_mask

    fn_df = modeling_df.loc[fn_mask].copy()
    tp_df = modeling_df.loc[tp_mask].copy()

    fn_contrib = model.booster_.predict(x_all.loc[fn_mask, feature_columns], pred_contrib=True)
    tp_contrib = model.booster_.predict(x_all.loc[tp_mask, feature_columns], pred_contrib=True)

    contrib_columns = [*feature_columns, "expected_value"]
    fn_contrib_df = pd.DataFrame(fn_contrib, columns=contrib_columns, index=fn_df.index)
    tp_contrib_df = pd.DataFrame(tp_contrib, columns=contrib_columns, index=tp_df.index)

    feature_only_fn = fn_contrib_df[feature_columns]
    feature_only_tp = tp_contrib_df[feature_columns]

    fn_df["top_positive_contribution_features"] = feature_only_fn.apply(top_positive_features, axis=1)
    fn_df["top_negative_contribution_features"] = feature_only_fn.apply(top_negative_features, axis=1)
    fn_df["top_positive_contribution_values"] = feature_only_fn.apply(
        lambda row: "|".join([f"{idx}:{val:.4f}" for idx, val in row.sort_values(ascending=False).head(10).items() if val > 0]),
        axis=1,
    )
    fn_df["top_negative_contribution_values"] = feature_only_fn.apply(
        lambda row: "|".join([f"{idx}:{val:.4f}" for idx, val in row.sort_values(ascending=True).head(10).items() if val < 0]),
        axis=1,
    )
    fn_df["expected_value"] = fn_contrib_df["expected_value"]

    row_columns = [
        "manufacturer",
        "substation_id",
        "window_start",
        "window_end",
        "fault_label",
        "fault_event_id",
        "estimated_lead_time_hours",
        "lead_time_bucket",
        "risk_probability",
        "risk_level",
        "risk_level_calibrated",
        "main_abnormal_features",
        "top_positive_contribution_features",
        "top_negative_contribution_features",
        "top_positive_contribution_values",
        "top_negative_contribution_values",
        "expected_value",
    ]
    fn_df[row_columns].to_csv(OUTPUT_ROWS_PATH, index=False, encoding="utf-8-sig")

    fn_summary = pd.DataFrame(
        {
            "feature": feature_columns,
            "fn_mean_contribution": feature_only_fn.mean(axis=0).values if len(fn_df) else np.zeros(len(feature_columns)),
            "fn_mean_abs_contribution": feature_only_fn.abs().mean(axis=0).values if len(fn_df) else np.zeros(len(feature_columns)),
            "fn_negative_count": (feature_only_fn < 0).sum(axis=0).values if len(fn_df) else np.zeros(len(feature_columns)),
            "fn_positive_count": (feature_only_fn > 0).sum(axis=0).values if len(fn_df) else np.zeros(len(feature_columns)),
        }
    )
    tp_summary = pd.DataFrame(
        {
            "feature": feature_columns,
            "tp_mean_contribution": feature_only_tp.mean(axis=0).values if len(tp_df) else np.zeros(len(feature_columns)),
            "tp_mean_abs_contribution": feature_only_tp.abs().mean(axis=0).values if len(tp_df) else np.zeros(len(feature_columns)),
            "tp_negative_count": (feature_only_tp < 0).sum(axis=0).values if len(tp_df) else np.zeros(len(feature_columns)),
            "tp_positive_count": (feature_only_tp > 0).sum(axis=0).values if len(tp_df) else np.zeros(len(feature_columns)),
        }
    )
    compare_df = fn_summary.merge(tp_summary, on="feature", how="left")
    compare_df["mean_contribution_gap_tp_minus_fn"] = compare_df["tp_mean_contribution"] - compare_df["fn_mean_contribution"]
    compare_df["negative_count_gap_fn_minus_tp"] = compare_df["fn_negative_count"] - compare_df["tp_negative_count"]
    compare_df = compare_df.sort_values(
        ["mean_contribution_gap_tp_minus_fn", "negative_count_gap_fn_minus_tp"],
        ascending=[False, False],
    ).reset_index(drop=True)

    feature_summary = compare_df[
        [
            "feature",
            "fn_mean_contribution",
            "fn_negative_count",
            "tp_mean_contribution",
            "tp_negative_count",
            "mean_contribution_gap_tp_minus_fn",
            "negative_count_gap_fn_minus_tp",
        ]
    ].copy()

    feature_summary.to_csv(OUTPUT_FEATURE_PATH, index=False, encoding="utf-8-sig")
    compare_df.to_csv(OUTPUT_COMPARE_PATH, index=False, encoding="utf-8-sig")

    print(OUTPUT_ROWS_PATH)
    print(OUTPUT_FEATURE_PATH)
    print(OUTPUT_COMPARE_PATH)
    print()
    print(f"holdout false negatives: {len(fn_df)}")
    print(f"holdout true positives: {len(tp_df)}")
    print()
    print("Top TP-vs-FN contribution gap features:")
    print(feature_summary.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
