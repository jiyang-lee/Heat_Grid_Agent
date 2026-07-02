from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
MODEL_DIR = ML_RISK_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
RISK_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores.csv"
RISK_MODEL_PATH = MODEL_DIR / "lightgbm_risk_model.joblib"
RISK_MODEL_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

OUTPUT_IMPORTANCE_PATH = ML_RISK_DIR / "lgbm_feature_importance_audit.csv"
OUTPUT_SPLIT_SUMMARY_PATH = ML_RISK_DIR / "lgbm_feature_importance_split_summary.csv"
OUTPUT_FAMILY_SUMMARY_PATH = ML_RISK_DIR / "lgbm_feature_importance_family_summary.csv"
OUTPUT_DRIFT_PATH = ML_RISK_DIR / "lgbm_feature_importance_drift_candidates.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"


def classify_feature_family(feature: str, metadata: dict) -> str:
    if feature in set(metadata.get("event_context_feature_columns", [])):
        return "event_context"
    if feature in {"anomaly_score", "disturbance_count", "maintenance_related"}:
        return "context"
    if feature.endswith("_sin") or feature.endswith("_cos"):
        return "cyclic_time"
    if feature in {"hour_of_day", "day_of_week", "day_of_year", "month", "is_weekend", "is_heating_season"}:
        return "time_context"
    if "__is__" in feature:
        return "derived_one_hot"
    return "sensor_numeric"


def permutation_frame(model, x: pd.DataFrame, y: pd.Series, split_name: str) -> pd.DataFrame:
    result = permutation_importance(
        model,
        x,
        y,
        n_repeats=10,
        random_state=42,
        scoring="f1",
        n_jobs=1,
    )
    return pd.DataFrame(
        {
            "feature": x.columns,
            f"{split_name}_permutation_mean": result.importances_mean,
            f"{split_name}_permutation_std": result.importances_std,
        }
    )


def main() -> None:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    model = joblib.load(RISK_MODEL_PATH)

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        PRIMARY_SPLIT_COLUMN,
        "split_event_based",
        "split_regime_based",
        "split_time_based",
        "split_substation_based",
        "anomaly_score",
        "disturbance_count",
        "maintenance_related",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
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
    if PRIMARY_SPLIT_COLUMN not in modeling_df.columns and f"{PRIMARY_SPLIT_COLUMN}_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={f"{PRIMARY_SPLIT_COLUMN}_risk": PRIMARY_SPLIT_COLUMN})
    modeling_df["risk_target"] = (modeling_df["label"] == "pre_fault").astype(int)
    if "maintenance_related" in modeling_df.columns:
        modeling_df["maintenance_related"] = modeling_df["maintenance_related"].map(
            {True: 1, False: 0, "True": 1, "False": 0}
        ).fillna(0).astype("int8")

    feature_columns = metadata["model_feature_columns"]
    missing_columns = [column for column in feature_columns if column not in modeling_df.columns]
    if missing_columns:
        raise ValueError(f"Missing model feature columns: {missing_columns[:10]}")

    x = modeling_df[feature_columns].copy()
    for column in x.columns:
        if x[column].dtype == "bool":
            x[column] = x[column].astype("int8")
        elif x[column].dtype == "object":
            x[column] = pd.to_numeric(x[column], errors="coerce")
    if x.isna().any().any():
        missing_summary = x.isna().sum()
        missing_summary = missing_summary[missing_summary > 0].sort_values(ascending=False)
        raise ValueError("Importance audit input contains missing values:\n" + str(missing_summary.head(20)))
    y = modeling_df["risk_target"].astype(int)

    train_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")

    booster = model.booster_
    importance_df = pd.DataFrame(
        {
            "feature": feature_columns,
            "gain_importance": booster.feature_importance(importance_type="gain"),
            "split_importance": booster.feature_importance(importance_type="split"),
        }
    )
    importance_df["feature_family"] = importance_df["feature"].map(lambda feature: classify_feature_family(feature, metadata))
    importance_df["gain_rank"] = importance_df["gain_importance"].rank(method="min", ascending=False).astype(int)
    importance_df["split_rank"] = importance_df["split_importance"].rank(method="min", ascending=False).astype(int)

    train_perm = permutation_frame(model, x.loc[train_mask], y.loc[train_mask], "train")
    validation_perm = permutation_frame(model, x.loc[validation_mask], y.loc[validation_mask], "validation")
    holdout_perm = permutation_frame(model, x.loc[holdout_mask], y.loc[holdout_mask], "holdout")

    importance_df = importance_df.merge(train_perm, on="feature", how="left")
    importance_df = importance_df.merge(validation_perm, on="feature", how="left")
    importance_df = importance_df.merge(holdout_perm, on="feature", how="left")
    importance_df["train_holdout_gap"] = (
        importance_df["train_permutation_mean"] - importance_df["holdout_permutation_mean"]
    )
    importance_df["validation_holdout_gap"] = (
        importance_df["validation_permutation_mean"] - importance_df["holdout_permutation_mean"]
    )

    def drift_flag(row: pd.Series) -> str:
        train_mean = float(row["train_permutation_mean"])
        holdout_mean = float(row["holdout_permutation_mean"])
        if train_mean >= 0.01 and holdout_mean <= 0:
            return "train_only_signal"
        if train_mean >= 0.01 and holdout_mean < train_mean * 0.25:
            return "large_drop_on_holdout"
        if train_mean <= 0 and holdout_mean > 0.005:
            return "holdout_only_signal"
        return ""

    importance_df["drift_flag"] = importance_df.apply(drift_flag, axis=1)
    importance_df = importance_df.sort_values(
        ["holdout_permutation_mean", "gain_importance"],
        ascending=[False, False],
    ).reset_index(drop=True)

    split_summary_df = importance_df[
        [
            "feature",
            "feature_family",
            "gain_importance",
            "split_importance",
            "train_permutation_mean",
            "validation_permutation_mean",
            "holdout_permutation_mean",
            "train_holdout_gap",
            "validation_holdout_gap",
            "drift_flag",
        ]
    ].copy()

    family_summary_df = (
        importance_df.groupby("feature_family", dropna=False)
        .agg(
            feature_count=("feature", "size"),
            total_gain_importance=("gain_importance", "sum"),
            total_split_importance=("split_importance", "sum"),
            mean_holdout_permutation=("holdout_permutation_mean", "mean"),
            positive_holdout_feature_count=("holdout_permutation_mean", lambda s: int((s > 0).sum())),
        )
        .reset_index()
        .sort_values("mean_holdout_permutation", ascending=False)
    )

    drift_df = split_summary_df.loc[split_summary_df["drift_flag"].ne("")].copy()
    drift_df = drift_df.sort_values(
        ["train_holdout_gap", "train_permutation_mean", "gain_importance"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    importance_df.to_csv(OUTPUT_IMPORTANCE_PATH, index=False, encoding="utf-8-sig")
    split_summary_df.to_csv(OUTPUT_SPLIT_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    family_summary_df.to_csv(OUTPUT_FAMILY_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    drift_df.to_csv(OUTPUT_DRIFT_PATH, index=False, encoding="utf-8-sig")

    print(OUTPUT_IMPORTANCE_PATH)
    print(OUTPUT_SPLIT_SUMMARY_PATH)
    print(OUTPUT_FAMILY_SUMMARY_PATH)
    print(OUTPUT_DRIFT_PATH)
    print()
    print("Top holdout permutation features:")
    print(
        split_summary_df.sort_values(
            ["holdout_permutation_mean", "gain_importance"],
            ascending=[False, False],
        )
        .head(15)
        .to_string(index=False)
    )
    print()
    print("Top drift candidates:")
    print(drift_df.head(15).to_string(index=False))


if __name__ == "__main__":
    main()

