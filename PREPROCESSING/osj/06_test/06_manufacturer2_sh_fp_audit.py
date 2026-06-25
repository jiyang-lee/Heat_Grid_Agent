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
RISK_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores.csv"
RISK_MODEL_PATH = MODEL_DIR / "lightgbm_risk_model.joblib"
RISK_MODEL_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

OUTPUT_ROW_PATH = ML_RISK_DIR / "manufacturer2_sh_fp_feature_contributions.csv"
OUTPUT_FEATURE_PATH = ML_RISK_DIR / "manufacturer2_sh_fp_feature_summary.csv"
OUTPUT_COMPARE_PATH = ML_RISK_DIR / "manufacturer2_sh_fp_vs_tn_feature_compare.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
HIGH_THRESHOLD = 0.44


def load_modeling_frame() -> tuple[pd.DataFrame, list[str], object]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    model = joblib.load(RISK_MODEL_PATH)

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        "configuration_type",
        PRIMARY_SPLIT_COLUMN,
        "anomaly_score",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
        "risk_probability",
        "risk_level",
        "main_abnormal_features",
        "model_explanation_features",
    ]
    merge_columns = [column for column in merge_columns if column in risk_scores.columns]

    modeling_df = trainable_windows.merge(
        risk_scores[merge_columns].drop_duplicates(subset=KEY_COLUMNS),
        on=KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_risk"),
    )
    if "label" not in modeling_df.columns and "label_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={"label_risk": "label"})
    if "configuration_type" not in modeling_df.columns and "configuration_type_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={"configuration_type_risk": "configuration_type"})
    if PRIMARY_SPLIT_COLUMN not in modeling_df.columns and f"{PRIMARY_SPLIT_COLUMN}_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={f"{PRIMARY_SPLIT_COLUMN}_risk": PRIMARY_SPLIT_COLUMN})

    feature_columns = metadata["model_feature_columns"]
    for column in feature_columns:
        risk_column = f"{column}_risk"
        if column not in modeling_df.columns and risk_column in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_column: column})
    x_all = modeling_df[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    if x_all.isna().any().any():
        missing_summary = x_all.isna().sum()
        missing_summary = missing_summary[missing_summary > 0].sort_values(ascending=False)
        raise ValueError("FP audit input contains missing values:\n" + str(missing_summary.head(20)))
    return modeling_df, feature_columns, model, x_all


def top_positive_features(row: pd.Series, top_n: int = 10) -> str:
    ordered = row.sort_values(ascending=False)
    ordered = ordered[ordered > 0]
    return "|".join(ordered.head(top_n).index.tolist())


def main() -> None:
    modeling_df, feature_columns, model, x_all = load_modeling_frame()

    base_mask = (
        modeling_df["manufacturer"].eq("manufacturer 2")
        & modeling_df["configuration_type"].eq("SH")
        & modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
        & modeling_df["label"].eq("normal")
    )
    false_positive_mask = base_mask & (modeling_df["risk_probability"] >= HIGH_THRESHOLD)
    true_negative_mask = base_mask & (modeling_df["risk_probability"] < HIGH_THRESHOLD)

    fp_df = modeling_df.loc[false_positive_mask].copy()
    tn_df = modeling_df.loc[true_negative_mask].copy()

    fp_contrib = model.booster_.predict(x_all.loc[false_positive_mask, feature_columns], pred_contrib=True)
    tn_contrib = model.booster_.predict(x_all.loc[true_negative_mask, feature_columns], pred_contrib=True)

    contrib_columns = [*feature_columns, "expected_value"]
    fp_contrib_df = pd.DataFrame(fp_contrib, columns=contrib_columns, index=fp_df.index)
    tn_contrib_df = pd.DataFrame(tn_contrib, columns=contrib_columns, index=tn_df.index)

    feature_only_fp = fp_contrib_df[feature_columns]
    feature_only_tn = tn_contrib_df[feature_columns]

    fp_df["top_positive_contribution_features"] = feature_only_fp.apply(top_positive_features, axis=1)
    fp_df["top_positive_contribution_values"] = feature_only_fp.apply(
        lambda row: "|".join([f"{idx}:{val:.4f}" for idx, val in row.sort_values(ascending=False).head(10).items() if val > 0]),
        axis=1,
    )
    fp_df["expected_value"] = fp_contrib_df["expected_value"]

    row_output_columns = [
        "manufacturer",
        "substation_id",
        "window_start",
        "window_end",
        "risk_probability",
        "risk_level",
        "main_abnormal_features",
        "top_positive_contribution_features",
        "top_positive_contribution_values",
        "expected_value",
    ]
    fp_df[row_output_columns].to_csv(OUTPUT_ROW_PATH, index=False, encoding="utf-8-sig")

    fp_summary = pd.DataFrame(
        {
            "feature": feature_columns,
            "fp_mean_contribution": feature_only_fp.mean(axis=0).values,
            "fp_positive_count": (feature_only_fp > 0).sum(axis=0).values,
            "fp_mean_abs_contribution": feature_only_fp.abs().mean(axis=0).values,
        }
    )
    tn_summary = pd.DataFrame(
        {
            "feature": feature_columns,
            "tn_mean_contribution": feature_only_tn.mean(axis=0).values if len(tn_df) else np.zeros(len(feature_columns)),
            "tn_positive_count": (feature_only_tn > 0).sum(axis=0).values if len(tn_df) else np.zeros(len(feature_columns)),
            "tn_mean_abs_contribution": feature_only_tn.abs().mean(axis=0).values if len(tn_df) else np.zeros(len(feature_columns)),
        }
    )
    compare_df = fp_summary.merge(tn_summary, on="feature", how="left")
    compare_df["mean_contribution_gap_fp_minus_tn"] = (
        compare_df["fp_mean_contribution"] - compare_df["tn_mean_contribution"]
    )
    compare_df["positive_count_gap_fp_minus_tn"] = (
        compare_df["fp_positive_count"] - compare_df["tn_positive_count"]
    )
    compare_df = compare_df.sort_values(
        ["mean_contribution_gap_fp_minus_tn", "fp_mean_contribution"],
        ascending=[False, False],
    ).reset_index(drop=True)

    feature_summary_df = compare_df[
        [
            "feature",
            "fp_mean_contribution",
            "fp_positive_count",
            "tn_mean_contribution",
            "tn_positive_count",
            "mean_contribution_gap_fp_minus_tn",
        ]
    ].copy()

    feature_summary_df.to_csv(OUTPUT_FEATURE_PATH, index=False, encoding="utf-8-sig")
    compare_df.to_csv(OUTPUT_COMPARE_PATH, index=False, encoding="utf-8-sig")

    print(OUTPUT_ROW_PATH)
    print(OUTPUT_FEATURE_PATH)
    print(OUTPUT_COMPARE_PATH)
    print()
    print(f"false positives: {len(fp_df)}")
    print(f"true negatives: {len(tn_df)}")
    print()
    print("Top FP-vs-TN contribution gap features:")
    print(feature_summary_df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
