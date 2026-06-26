from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
MODEL_DIR = ML_RISK_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
RISK_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores.csv"
RISK_MODEL_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

OUTPUT_PATH = ML_RISK_DIR / "lgbm_risk_weighting_experiment.csv"
OUTPUT_HOLDOUT_PATH = ML_RISK_DIR / "lgbm_risk_weighting_experiment_holdout.csv"
OUTPUT_FN_PATH = ML_RISK_DIR / "lgbm_risk_weighting_false_negative_summary.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
BASE_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}
RANDOM_STATE = 42

TARGET_GROUPS = {
    ("manufacturer 2", "SH with buffer tank"),
    ("manufacturer 2", "SH + DHW"),
    ("manufacturer 2", "SH"),
    ("manufacturer 1", "SH + DHW"),
}


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    negative_count = int(negatives.sum())
    if negative_count == 0:
        return 0.0
    fp = int(((y_pred == 1) & negatives).sum())
    return fp / negative_count


def score_frame(frame: pd.DataFrame, level_column: str) -> dict:
    y_true = (frame["label"] == "pre_fault").astype(int)
    y_score = frame["risk_probability"]
    y_pred = frame[level_column].isin(["high", "critical"]).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "row_count": int(len(frame)),
        "normal_count": int((y_true == 0).sum()),
        "pre_fault_count": int((y_true == 1).sum()),
        "roc_auc": float(roc_auc_score(y_true, y_score)),
        "average_precision": float(average_precision_score(y_true, y_score)),
        "precision_high_or_critical": float(precision),
        "recall_high_or_critical": float(recall),
        "f1_high_or_critical": float(f1),
        "false_positive_rate_high_or_critical": float(false_positive_rate(y_true, y_pred)),
    }


def apply_base_risk_level(score: float) -> str:
    if score >= BASE_THRESHOLDS["critical"]:
        return "critical"
    if score >= BASE_THRESHOLDS["high"]:
        return "high"
    if score >= BASE_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def apply_group_calibrated_risk_level(row: pd.Series) -> str:
    high = BASE_THRESHOLDS["high"]
    critical = BASE_THRESHOLDS["critical"]
    override = GROUP_OVERRIDES.get((row["manufacturer"], row["configuration_type"]))
    if override:
        high = override.get("high", high)
        critical = max(critical, high)
    score = row["risk_probability"]
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= BASE_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def load_base_frame() -> tuple[pd.DataFrame, list[str]]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    merge_columns = [
        *KEY_COLUMNS,
        "label",
        "configuration_type",
        PRIMARY_SPLIT_COLUMN,
        "lead_time_bucket",
        "anomaly_score",
        "days_since_last_fault_event",
    ]
    merge_columns = [column for column in merge_columns if column in risk_scores.columns]
    modeling_df = trainable_windows.merge(
        risk_scores[merge_columns].drop_duplicates(subset=KEY_COLUMNS),
        on=KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_risk"),
    )
    for base_name in ["label", "configuration_type", PRIMARY_SPLIT_COLUMN, "lead_time_bucket"]:
        risk_name = f"{base_name}_risk"
        if base_name not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: base_name})
    base_feature_columns = metadata["model_feature_columns"]
    for column in base_feature_columns:
        risk_name = f"{column}_risk"
        if column not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: column})
    if "use_for_supervised_training" in modeling_df.columns:
        modeling_df = modeling_df.loc[modeling_df["use_for_supervised_training"].fillna(True).astype(bool)].copy()
    modeling_df["risk_target"] = (modeling_df["label"] == "pre_fault").astype(int)
    return modeling_df, base_feature_columns


def build_features(modeling_df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    x_all = modeling_df[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    if x_all.isna().any().any():
        raise ValueError("missing values")
    return x_all


def build_sample_weights(modeling_df: pd.DataFrame, variant: str) -> pd.Series:
    weights = pd.Series(1.0, index=modeling_df.index, dtype="float64")
    pre_fault = modeling_df["label"].eq("pre_fault")
    lead_1_3d = modeling_df["lead_time_bucket"].eq("1-3d") if "lead_time_bucket" in modeling_df.columns else pd.Series(False, index=modeling_df.index)
    target_group = modeling_df.apply(lambda row: (row["manufacturer"], row["configuration_type"]) in TARGET_GROUPS, axis=1)

    if variant == "baseline_no_weight":
        return weights
    if variant == "leadtime_1_3d_x1_5":
        weights.loc[pre_fault & lead_1_3d] *= 1.5
    elif variant == "leadtime_1_3d_x2":
        weights.loc[pre_fault & lead_1_3d] *= 2.0
    elif variant == "group_x1_5":
        weights.loc[pre_fault & target_group] *= 1.5
    elif variant == "group_x2":
        weights.loc[pre_fault & target_group] *= 2.0
    elif variant == "leadtime_1_3d_x1_5_plus_group_x1_5":
        weights.loc[pre_fault & lead_1_3d] *= 1.5
        weights.loc[pre_fault & target_group] *= 1.5
    elif variant == "leadtime_1_3d_x2_plus_group_x1_5":
        weights.loc[pre_fault & lead_1_3d] *= 2.0
        weights.loc[pre_fault & target_group] *= 1.5
    else:
        raise ValueError(variant)
    return weights


def fn_summary(scored: pd.DataFrame, level_column: str, variant: str, metric_type: str) -> dict:
    holdout = scored.loc[
        scored[PRIMARY_SPLIT_COLUMN].eq("holdout")
        & scored["label"].eq("pre_fault")
        & (~scored[level_column].isin(["high", "critical"]))
    ]
    return {
        "variant": variant,
        "metric_type": metric_type,
        "false_negative_count": int(len(holdout)),
        "fn_1_3d_count": int(holdout["lead_time_bucket"].eq("1-3d").sum()) if "lead_time_bucket" in holdout.columns else None,
        "fn_medium_count": int(holdout[level_column].eq("medium").sum()),
        "fn_low_count": int(holdout[level_column].eq("low").sum()),
    }


def train_variant(modeling_df: pd.DataFrame, x_all: pd.DataFrame, feature_columns: list[str], variant: str) -> tuple[list[dict], list[dict]]:
    train_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    y_all = modeling_df["risk_target"].astype(int)
    sample_weight = build_sample_weights(modeling_df, variant)

    model = LGBMClassifier(
        objective="binary",
        n_estimators=150,
        learning_rate=0.04,
        num_leaves=15,
        min_child_samples=50,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_alpha=0.1,
        reg_lambda=1.0,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=-1,
    )
    model.fit(
        x_all.loc[train_mask, feature_columns],
        y_all.loc[train_mask],
        sample_weight=sample_weight.loc[train_mask],
        eval_set=[(x_all.loc[validation_mask, feature_columns], y_all.loc[validation_mask])],
        eval_metric="average_precision",
    )

    scored = modeling_df.copy()
    scored["risk_probability"] = model.predict_proba(x_all[feature_columns])[:, 1]
    scored["risk_level_base"] = scored["risk_probability"].map(apply_base_risk_level)
    scored["risk_level_calibrated"] = scored.apply(apply_group_calibrated_risk_level, axis=1)

    rows = []
    for split_name, split_mask in {"train": train_mask, "validation": validation_mask, "holdout": holdout_mask}.items():
        for scope_name, scope_mask in {
            "overall": pd.Series(True, index=scored.index),
            "manufacturer_2_sh": scored["manufacturer"].eq("manufacturer 2") & scored["configuration_type"].eq("SH"),
        }.items():
            frame = scored.loc[split_mask & scope_mask].copy()
            if frame.empty:
                continue
            for metric_type, level_column in {"base": "risk_level_base", "calibrated": "risk_level_calibrated"}.items():
                rows.append({
                    "variant": variant,
                    "split": split_name,
                    "scope": scope_name,
                    "metric_type": metric_type,
                    **score_frame(frame, level_column),
                })
    fn_rows = [
        fn_summary(scored, "risk_level_base", variant, "base"),
        fn_summary(scored, "risk_level_calibrated", variant, "calibrated"),
    ]
    return rows, fn_rows


def main() -> None:
    modeling_df, feature_columns = load_base_frame()
    x_all = build_features(modeling_df, feature_columns)
    variants = [
        "baseline_no_weight",
        "leadtime_1_3d_x1_5",
        "leadtime_1_3d_x2",
        "group_x1_5",
        "group_x2",
        "leadtime_1_3d_x1_5_plus_group_x1_5",
        "leadtime_1_3d_x2_plus_group_x1_5",
    ]
    rows = []
    fn_rows = []
    for variant in variants:
        r, f = train_variant(modeling_df, x_all, feature_columns, variant)
        rows.extend(r)
        fn_rows.extend(f)
    result_df = pd.DataFrame(rows)
    holdout_df = result_df.loc[result_df["split"].eq("holdout")].copy().sort_values(
        ["scope", "metric_type", "f1_high_or_critical", "false_positive_rate_high_or_critical"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)
    fn_df = pd.DataFrame(fn_rows).sort_values(
        ["metric_type", "false_negative_count", "fn_1_3d_count"], ascending=[True, True, True]
    ).reset_index(drop=True)
    result_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    holdout_df.to_csv(OUTPUT_HOLDOUT_PATH, index=False, encoding="utf-8-sig")
    fn_df.to_csv(OUTPUT_FN_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_PATH)
    print(OUTPUT_HOLDOUT_PATH)
    print(OUTPUT_FN_PATH)
    print()
    print(holdout_df.to_string(index=False))
    print()
    print(fn_df.to_string(index=False))


if __name__ == "__main__":
    main()

