from __future__ import annotations

import json
from pathlib import Path

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

OUTPUT_PATH = ML_RISK_DIR / "lgbm_state_thermal_combined_experiment.csv"
OUTPUT_HOLDOUT_PATH = ML_RISK_DIR / "lgbm_state_thermal_combined_experiment_holdout.csv"
OUTPUT_FN_PATH = ML_RISK_DIR / "lgbm_state_thermal_combined_false_negative_summary.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
BASE_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}
EVENT_DAY_COLUMNS = [
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
]
THERMAL_RAW_COLUMNS = [
    "network_temperature_gap__mean",
    "p_net_return_temperature__max",
    "p_net_return_temperature__mean",
    "p_net_supply_temperature__mean",
    "p_net_supply_temperature__max",
    "s_dhw_upper_storage_temperature__last",
    "s_dhw_upper_storage_temperature__max",
]
RELATION_COLUMNS = {
    "p_net_supply_minus_return_mean": ("p_net_supply_temperature__mean", "p_net_return_temperature__mean"),
    "p_net_supply_minus_return_max": ("p_net_supply_temperature__max", "p_net_return_temperature__max"),
    "s_dhw_upper_minus_supply_last": ("s_dhw_upper_storage_temperature__last", "s_dhw_supply_temperature__last"),
    "s_dhw_upper_minus_supply_max": ("s_dhw_upper_storage_temperature__max", "s_dhw_supply_temperature__max"),
    "hc1_supply_setpoint_gap_mean": ("s_hc1_supply_temperature__mean", "s_hc1_supply_temperature_setpoint__mean"),
}
RANDOM_STATE = 42


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


def add_event_state_columns(series: pd.Series, prefix: str) -> pd.DataFrame:
    numeric = pd.to_numeric(series, errors="coerce").fillna(9999.0)
    frame = pd.DataFrame(index=series.index)
    frame[f"{prefix}__has_previous"] = (numeric < 9999.0).astype("int8")
    frame[f"{prefix}__recent_7d"] = (numeric <= 7).astype("int8")
    frame[f"{prefix}__recent_30d"] = (numeric <= 30).astype("int8")
    frame[f"{prefix}__recent_90d"] = (numeric <= 90).astype("int8")
    frame[f"{prefix}__stale_gt_90d"] = ((numeric > 90) & (numeric < 9999.0)).astype("int8")
    return frame


def add_group_zscore(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    group_cols = [column for column in ["manufacturer", "configuration_type", "season_bucket"] if column in frame.columns]
    if not group_cols:
        return result
    grouped = frame.groupby(group_cols, dropna=False)
    for column in columns:
        if column not in frame.columns:
            continue
        mean = grouped[column].transform("mean")
        std = grouped[column].transform("std").replace(0, pd.NA)
        result[f"{column}__group_zscore"] = (((frame[column] - mean) / std).fillna(0.0)).astype("float64")
    return result


def add_relation_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    for new_column, (left, right) in RELATION_COLUMNS.items():
        if left in frame.columns and right in frame.columns:
            result[new_column] = (frame[left] - frame[right]).astype("float64")
    if "network_temperature_gap__mean" in frame.columns and "outdoor_temperature__mean" in frame.columns:
        result["network_gap_over_outdoor_mean"] = (frame["network_temperature_gap__mean"] - frame["outdoor_temperature__mean"]).astype("float64")
    if "p_net_return_temperature__mean" in frame.columns and "outdoor_temperature__mean" in frame.columns:
        result["return_temp_over_outdoor_mean"] = (frame["p_net_return_temperature__mean"] - frame["outdoor_temperature__mean"]).astype("float64")
    return result


def load_base_frame() -> tuple[pd.DataFrame, list[str]]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    merge_columns = [*KEY_COLUMNS, "label", "configuration_type", PRIMARY_SPLIT_COLUMN, "lead_time_bucket", "anomaly_score", *EVENT_DAY_COLUMNS]
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


def build_feature_matrix(modeling_df: pd.DataFrame, feature_columns: list[str], event_variant: str, thermal_variant: str) -> tuple[pd.DataFrame, list[str]]:
    x_all = modeling_df[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")

    if event_variant == "state_any_task_keep_fault_raw":
        extra = []
        drop = []
        for column in ["days_since_last_task_event", "days_since_last_any_event"]:
            if column in x_all.columns:
                extra.append(add_event_state_columns(x_all[column], column))
                drop.append(column)
        x_all = x_all.drop(columns=drop)
        x_all = pd.concat([x_all, *extra], axis=1)
    elif event_variant != "baseline_raw":
        raise ValueError(event_variant)

    thermal_columns_present = [column for column in THERMAL_RAW_COLUMNS if column in modeling_df.columns]
    extra_frames = []
    drop_columns = []
    if thermal_variant == "raw":
        pass
    elif thermal_variant == "group_zscore_only":
        extra_frames.append(add_group_zscore(modeling_df, thermal_columns_present))
    elif thermal_variant == "replace_raw_with_relation":
        extra_frames.append(add_relation_features(modeling_df))
        drop_columns.extend([column for column in thermal_columns_present if column in x_all.columns])
    elif thermal_variant == "group_zscore_plus_relation":
        extra_frames.append(add_group_zscore(modeling_df, thermal_columns_present))
        extra_frames.append(add_relation_features(modeling_df))
    else:
        raise ValueError(thermal_variant)
    if drop_columns:
        x_all = x_all.drop(columns=drop_columns)
    if extra_frames:
        x_all = pd.concat([x_all, *extra_frames], axis=1)
    if x_all.isna().any().any():
        raise ValueError("missing values in combined experiment")
    return x_all, x_all.columns.tolist()


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


def train_variant(modeling_df: pd.DataFrame, base_feature_columns: list[str], variant_name: str, event_variant: str, thermal_variant: str) -> tuple[list[dict], list[dict]]:
    x_all, model_feature_columns = build_feature_matrix(modeling_df, base_feature_columns, event_variant, thermal_variant)
    train_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    y_all = modeling_df["risk_target"].astype(int)
    model = LGBMClassifier(
        objective="binary", n_estimators=150, learning_rate=0.04, num_leaves=15, min_child_samples=50,
        subsample=0.85, colsample_bytree=0.85, reg_alpha=0.1, reg_lambda=1.0,
        class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1, verbosity=-1,
    )
    model.fit(
        x_all.loc[train_mask, model_feature_columns], y_all.loc[train_mask],
        eval_set=[(x_all.loc[validation_mask, model_feature_columns], y_all.loc[validation_mask])],
        eval_metric="average_precision",
    )
    scored = modeling_df.copy()
    scored["risk_probability"] = model.predict_proba(x_all[model_feature_columns])[:, 1]
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
                    "variant": variant_name, "feature_count": len(model_feature_columns), "split": split_name,
                    "scope": scope_name, "metric_type": metric_type, **score_frame(frame, level_column)
                })
    fn_rows = [
        fn_summary(scored, "risk_level_base", variant_name, "base"),
        fn_summary(scored, "risk_level_calibrated", variant_name, "calibrated"),
    ]
    return rows, fn_rows


def main() -> None:
    modeling_df, base_feature_columns = load_base_frame()
    variants = [
        ("baseline_raw", "baseline_raw", "raw"),
        ("state_any_task_keep_fault_raw", "state_any_task_keep_fault_raw", "raw"),
        ("state_plus_group_zscore", "state_any_task_keep_fault_raw", "group_zscore_only"),
        ("state_plus_replace_raw_with_relation", "state_any_task_keep_fault_raw", "replace_raw_with_relation"),
        ("state_plus_group_zscore_plus_relation", "state_any_task_keep_fault_raw", "group_zscore_plus_relation"),
    ]
    rows = []
    fn_rows = []
    for variant_name, event_variant, thermal_variant in variants:
        r, f = train_variant(modeling_df, base_feature_columns, variant_name, event_variant, thermal_variant)
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

