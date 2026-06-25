from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
MODEL_DIR = ML_RISK_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
RISK_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores.csv"
RISK_MODEL_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

OUTPUT_PATH = ML_RISK_DIR / "lgbm_event_context_reencoding_experiment.csv"
OUTPUT_HOLDOUT_PATH = ML_RISK_DIR / "lgbm_event_context_reencoding_holdout.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
BASE_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}
EVENT_DAY_COLUMNS = [
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
]
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
    score = row["risk_probability"]
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


def load_base_frame() -> tuple[pd.DataFrame, list[str]]:
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
    if "label" not in modeling_df.columns and "label_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={"label_risk": "label"})
    if "configuration_type" not in modeling_df.columns and "configuration_type_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={"configuration_type_risk": "configuration_type"})
    if PRIMARY_SPLIT_COLUMN not in modeling_df.columns and f"{PRIMARY_SPLIT_COLUMN}_risk" in modeling_df.columns:
        modeling_df = modeling_df.rename(columns={f"{PRIMARY_SPLIT_COLUMN}_risk": PRIMARY_SPLIT_COLUMN})
    base_feature_columns = metadata["model_feature_columns"]
    for column in base_feature_columns:
        risk_column = f"{column}_risk"
        if column not in modeling_df.columns and risk_column in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_column: column})

    if "use_for_supervised_training" in modeling_df.columns:
        modeling_df = modeling_df.loc[
            modeling_df["use_for_supervised_training"].fillna(True).astype(bool)
        ].copy()

    modeling_df["risk_target"] = (modeling_df["label"] == "pre_fault").astype(int)
    return modeling_df, base_feature_columns


def build_feature_matrix(modeling_df: pd.DataFrame, feature_columns: list[str], variant: str) -> tuple[pd.DataFrame, list[str]]:
    x_all = modeling_df[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")

    event_columns_present = [column for column in EVENT_DAY_COLUMNS if column in x_all.columns]
    extra_frames: list[pd.DataFrame] = []
    drop_columns: list[str] = []

    if variant == "baseline_raw":
        pass
    elif variant == "clip90_all_event_days":
        for column in event_columns_present:
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce").fillna(9999.0).clip(upper=90.0)
    elif variant == "bucket_any_task_keep_fault_raw":
        for column in ["days_since_last_task_event", "days_since_last_any_event"]:
            if column in x_all.columns:
                extra_frames.append(bucketize_event_days(x_all[column], column))
                drop_columns.append(column)
    elif variant == "bucket_all_event_days":
        for column in event_columns_present:
            extra_frames.append(bucketize_event_days(x_all[column], column))
            drop_columns.append(column)
    elif variant == "bucket_any_task_clip90_fault":
        if "days_since_last_fault_event" in x_all.columns:
            x_all["days_since_last_fault_event"] = (
                pd.to_numeric(x_all["days_since_last_fault_event"], errors="coerce")
                .fillna(9999.0)
                .clip(upper=90.0)
            )
        for column in ["days_since_last_task_event", "days_since_last_any_event"]:
            if column in x_all.columns:
                extra_frames.append(bucketize_event_days(x_all[column], column))
                drop_columns.append(column)
    else:
        raise ValueError(f"Unknown variant: {variant}")

    if drop_columns:
        x_all = x_all.drop(columns=drop_columns)
    if extra_frames:
        x_all = pd.concat([x_all, *extra_frames], axis=1)

    if x_all.isna().any().any():
        missing_summary = x_all.isna().sum()
        missing_summary = missing_summary[missing_summary > 0].sort_values(ascending=False)
        raise ValueError(f"{variant} contains missing values:\n{missing_summary.head(20)}")

    model_feature_columns = x_all.columns.tolist()
    return x_all, model_feature_columns


def train_and_score_variant(modeling_df: pd.DataFrame, base_feature_columns: list[str], variant: str) -> list[dict]:
    x_all, model_feature_columns = build_feature_matrix(modeling_df, base_feature_columns, variant)

    train_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    y_all = modeling_df["risk_target"].astype(int)

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
        x_all.loc[train_mask, model_feature_columns],
        y_all.loc[train_mask],
        eval_set=[(x_all.loc[validation_mask, model_feature_columns], y_all.loc[validation_mask])],
        eval_metric="average_precision",
    )

    scored = modeling_df.copy()
    scored["risk_probability"] = model.predict_proba(x_all[model_feature_columns])[:, 1]
    scored["risk_level_base"] = scored["risk_probability"].map(apply_base_risk_level)
    scored["risk_level_calibrated"] = scored.apply(apply_group_calibrated_risk_level, axis=1)

    rows: list[dict] = []
    group_filters = {
        "overall": pd.Series(True, index=scored.index),
        "manufacturer_2_sh": (
            scored["manufacturer"].eq("manufacturer 2")
            & scored["configuration_type"].eq("SH")
        ),
    }
    for split_name, split_mask in {
        "train": train_mask,
        "validation": validation_mask,
        "holdout": holdout_mask,
    }.items():
        for scope_name, scope_mask in group_filters.items():
            frame = scored.loc[split_mask & scope_mask].copy()
            if frame.empty:
                continue
            for metric_type, level_column in {
                "base": "risk_level_base",
                "calibrated": "risk_level_calibrated",
            }.items():
                metrics = score_frame(frame, level_column)
                rows.append(
                    {
                        "variant": variant,
                        "feature_count": len(model_feature_columns),
                        "split": split_name,
                        "scope": scope_name,
                        "metric_type": metric_type,
                        **metrics,
                    }
                )
    return rows


def main() -> None:
    modeling_df, base_feature_columns = load_base_frame()
    variants = [
        "baseline_raw",
        "clip90_all_event_days",
        "bucket_any_task_keep_fault_raw",
        "bucket_all_event_days",
        "bucket_any_task_clip90_fault",
    ]

    rows: list[dict] = []
    for variant in variants:
        rows.extend(train_and_score_variant(modeling_df, base_feature_columns, variant))

    result_df = pd.DataFrame(rows)
    holdout_df = result_df.loc[result_df["split"].eq("holdout")].copy()
    holdout_df = holdout_df.sort_values(
        ["scope", "metric_type", "f1_high_or_critical", "false_positive_rate_high_or_critical"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)

    result_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    holdout_df.to_csv(OUTPUT_HOLDOUT_PATH, index=False, encoding="utf-8-sig")

    print(OUTPUT_PATH)
    print(OUTPUT_HOLDOUT_PATH)
    print()
    print(holdout_df.to_string(index=False))


if __name__ == "__main__":
    main()
