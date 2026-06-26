from __future__ import annotations

import json
from pathlib import Path

import joblib
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

PROMOTED_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores_promoted.csv"
PROMOTED_METRICS_PATH = ML_RISK_DIR / "lgbm_risk_metrics_promoted.csv"
PROMOTED_THRESHOLDS_PATH = ML_RISK_DIR / "lgbm_risk_thresholds_promoted.csv"
PROMOTED_GROUP_OVERRIDES_PATH = ML_RISK_DIR / "lgbm_group_threshold_overrides_promoted.csv"
OVERALL_MODEL_PATH = MODEL_DIR / "lightgbm_risk_model_promoted_overall.joblib"
GROUP_MODEL_PATH = MODEL_DIR / "lightgbm_risk_model_promoted_manufacturer2_sh.joblib"
PROMOTED_METADATA_PATH = MODEL_DIR / "risk_model_promoted_metadata.json"

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
    y_score = frame["risk_probability_promoted"]
    y_pred = frame[level_column].isin(["high", "critical"]).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
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
    medium = BASE_THRESHOLDS["medium"]
    high = BASE_THRESHOLDS["high"]
    critical = BASE_THRESHOLDS["critical"]
    override = GROUP_OVERRIDES.get((row["manufacturer"], row["configuration_type"]))
    if override:
        high = override.get("high", high)
        critical = max(critical, high)
    score = row["risk_probability_promoted"]
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def bucketize_event_days(series: pd.Series, prefix: str) -> pd.DataFrame:
    numeric = pd.to_numeric(series, errors="coerce").fillna(9999.0)
    frame = pd.DataFrame(index=series.index)
    frame[f"{prefix}__bucket__le_7d"] = (numeric <= 7).astype("int8")
    frame[f"{prefix}__bucket__8_30d"] = ((numeric > 7) & (numeric <= 30)).astype("int8")
    frame[f"{prefix}__bucket__31_90d"] = ((numeric > 30) & (numeric <= 90)).astype("int8")
    frame[f"{prefix}__bucket__gt_90d"] = (numeric > 90).astype("int8")
    return frame


def add_group_zscore(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    group_cols = ["manufacturer", "configuration_type", "season_bucket"]
    result = pd.DataFrame(index=frame.index)
    available_group_cols = [column for column in group_cols if column in frame.columns]
    if not available_group_cols:
        return result
    grouped = frame.groupby(available_group_cols, dropna=False)
    for column in columns:
        if column not in frame.columns:
            continue
        mean = grouped[column].transform("mean")
        std = grouped[column].transform("std").replace(0, pd.NA)
        result[f"{column}__group_zscore"] = (((frame[column] - mean) / std).fillna(0.0)).astype("float64")
    return result


def load_base_frame() -> tuple[pd.DataFrame, list[str], dict]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        "configuration_type",
        PRIMARY_SPLIT_COLUMN,
        "anomaly_score",
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
    for base_name in ["label", "configuration_type", PRIMARY_SPLIT_COLUMN]:
        risk_name = f"{base_name}_risk"
        if base_name not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: base_name})

    base_feature_columns = metadata["model_feature_columns"]
    for column in base_feature_columns:
        risk_name = f"{column}_risk"
        if column not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: column})

    if "use_for_supervised_training" in modeling_df.columns:
        modeling_df = modeling_df.loc[
            modeling_df["use_for_supervised_training"].fillna(True).astype(bool)
        ].copy()

    modeling_df["risk_target"] = (modeling_df["label"] == "pre_fault").astype(int)
    return modeling_df, base_feature_columns, metadata


def make_numeric_feature_frame(modeling_df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    x_all = modeling_df[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    return x_all


def build_event_context_only(modeling_df: pd.DataFrame, feature_columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    x_all = make_numeric_feature_frame(modeling_df, feature_columns)
    extra_frames: list[pd.DataFrame] = []
    drop_columns: list[str] = []
    for column in ["days_since_last_task_event", "days_since_last_any_event"]:
        if column in x_all.columns:
            extra_frames.append(bucketize_event_days(x_all[column], column))
            drop_columns.append(column)
    if drop_columns:
        x_all = x_all.drop(columns=drop_columns)
    if extra_frames:
        x_all = pd.concat([x_all, *extra_frames], axis=1)
    if x_all.isna().any().any():
        raise ValueError("event_context_only contains missing values")
    return x_all, x_all.columns.tolist()


def build_thermal_group_zscore_only(modeling_df: pd.DataFrame, feature_columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    x_all = make_numeric_feature_frame(modeling_df, feature_columns)
    thermal_columns_present = [column for column in THERMAL_RAW_COLUMNS if column in modeling_df.columns]
    x_all = pd.concat([x_all, add_group_zscore(modeling_df, thermal_columns_present)], axis=1)
    if x_all.isna().any().any():
        raise ValueError("thermal_group_zscore_only contains missing values")
    return x_all, x_all.columns.tolist()


def fit_model(x_all: pd.DataFrame, feature_columns: list[str], train_mask: pd.Series, validation_mask: pd.Series, y_all: pd.Series) -> LGBMClassifier:
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
        eval_set=[(x_all.loc[validation_mask, feature_columns], y_all.loc[validation_mask])],
        eval_metric="average_precision",
    )
    return model


def main() -> None:
    modeling_df, base_feature_columns, base_metadata = load_base_frame()
    train_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    group_mask = modeling_df["manufacturer"].eq("manufacturer 2") & modeling_df["configuration_type"].eq("SH")
    y_all = modeling_df["risk_target"].astype(int)

    overall_x, overall_features = build_thermal_group_zscore_only(modeling_df, base_feature_columns)
    group_x, group_features = build_event_context_only(modeling_df, base_feature_columns)

    overall_model = fit_model(overall_x, overall_features, train_mask, validation_mask, y_all)
    group_model = fit_model(group_x, group_features, train_mask, validation_mask, y_all)

    promoted_df = modeling_df.copy()
    promoted_df["risk_probability_overall_model"] = overall_model.predict_proba(overall_x[overall_features])[:, 1]
    promoted_df["risk_probability_group_model"] = group_model.predict_proba(group_x[group_features])[:, 1]
    promoted_df["promoted_model_branch"] = "overall_thermal_group_zscore_only"
    promoted_df.loc[group_mask, "promoted_model_branch"] = "manufacturer2_sh_event_context_only"
    promoted_df["risk_probability_promoted"] = promoted_df["risk_probability_overall_model"]
    promoted_df.loc[group_mask, "risk_probability_promoted"] = promoted_df.loc[group_mask, "risk_probability_group_model"]

    promoted_df["risk_level_promoted_base"] = promoted_df["risk_probability_promoted"].map(apply_base_risk_level)
    promoted_df["risk_level_promoted_calibrated"] = promoted_df.apply(apply_group_calibrated_risk_level, axis=1)
    promoted_df["risk_threshold_medium_applied"] = BASE_THRESHOLDS["medium"]
    promoted_df["risk_threshold_high_applied"] = BASE_THRESHOLDS["high"]
    promoted_df["risk_threshold_critical_applied"] = BASE_THRESHOLDS["critical"]
    promoted_df.loc[group_mask, "risk_threshold_high_applied"] = GROUP_OVERRIDES[("manufacturer 2", "SH")]["high"]
    promoted_df["group_threshold_override_applied"] = 0
    promoted_df.loc[group_mask, "group_threshold_override_applied"] = 1

    metric_rows: list[dict] = []
    group_filters = {
        "overall": pd.Series(True, index=promoted_df.index),
        "manufacturer_2_sh": group_mask,
    }
    for split_name, split_mask in {
        "train": train_mask,
        "validation": validation_mask,
        "holdout": holdout_mask,
    }.items():
        for scope_name, scope_mask in group_filters.items():
            frame = promoted_df.loc[split_mask & scope_mask].copy()
            if frame.empty:
                continue
            for metric_type, level_column in {
                "base": "risk_level_promoted_base",
                "calibrated": "risk_level_promoted_calibrated",
            }.items():
                metrics = score_frame(frame, level_column)
                metric_rows.append(
                    {
                        "split": split_name,
                        "scope": scope_name,
                        "metric_type": metric_type,
                        **metrics,
                    }
                )

    metrics_df = pd.DataFrame(metric_rows)
    thresholds_df = pd.DataFrame(
        [
            {"level": "medium", "threshold": BASE_THRESHOLDS["medium"], "note": "promoted operating threshold"},
            {"level": "high", "threshold": BASE_THRESHOLDS["high"], "note": "promoted operating threshold"},
            {"level": "critical", "threshold": BASE_THRESHOLDS["critical"], "note": "promoted operating threshold"},
        ]
    )
    overrides_df = pd.DataFrame(
        [
            {
                "manufacturer": "manufacturer 2",
                "configuration_type": "SH",
                "medium_threshold": BASE_THRESHOLDS["medium"],
                "high_threshold": GROUP_OVERRIDES[("manufacturer 2", "SH")]["high"],
                "critical_threshold": BASE_THRESHOLDS["critical"],
                "basis": "promoted hybrid branch with group-specific operating override",
            }
        ]
    )

    promoted_df.to_csv(PROMOTED_SCORES_PATH, index=False, encoding="utf-8-sig")
    metrics_df.to_csv(PROMOTED_METRICS_PATH, index=False, encoding="utf-8-sig")
    thresholds_df.to_csv(PROMOTED_THRESHOLDS_PATH, index=False, encoding="utf-8-sig")
    overrides_df.to_csv(PROMOTED_GROUP_OVERRIDES_PATH, index=False, encoding="utf-8-sig")

    joblib.dump(overall_model, OVERALL_MODEL_PATH)
    joblib.dump(group_model, GROUP_MODEL_PATH)

    metadata = {
        "model_version": "lgbm_risk_06_promoted_hybrid_v1",
        "promotion_basis": {
            "overall_branch": "thermal_group_zscore_only",
            "manufacturer_2_sh_branch": "event_context_only",
            "selection_reason": "combined experiment showed overall/group winners differ, so promoted as hybrid branch",
        },
        "primary_split_column": PRIMARY_SPLIT_COLUMN,
        "base_thresholds": BASE_THRESHOLDS,
        "group_overrides": [
            {
                "manufacturer": manufacturer,
                "configuration_type": configuration_type,
                "high_threshold": override["high"],
            }
            for (manufacturer, configuration_type), override in GROUP_OVERRIDES.items()
        ],
        "overall_feature_count": len(overall_features),
        "group_feature_count": len(group_features),
        "overall_feature_columns": overall_features,
        "group_feature_columns": group_features,
        "input_base_model_version": base_metadata.get("model_version"),
        "output_scores_path": str(PROMOTED_SCORES_PATH),
        "output_metrics_path": str(PROMOTED_METRICS_PATH),
        "output_thresholds_path": str(PROMOTED_THRESHOLDS_PATH),
        "output_group_override_path": str(PROMOTED_GROUP_OVERRIDES_PATH),
        "overall_model_path": str(OVERALL_MODEL_PATH),
        "group_model_path": str(GROUP_MODEL_PATH),
    }
    PROMOTED_METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(PROMOTED_SCORES_PATH)
    print(PROMOTED_METRICS_PATH)
    print(PROMOTED_THRESHOLDS_PATH)
    print(PROMOTED_GROUP_OVERRIDES_PATH)
    print(PROMOTED_METADATA_PATH)
    print()
    print(metrics_df.to_string(index=False))


if __name__ == "__main__":
    main()

