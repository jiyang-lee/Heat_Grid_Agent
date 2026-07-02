from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
FEATURE_DIR = DATA_DIR / "ml_features"
RISK_DIR = DATA_DIR / "ml_risk"
REPORT_DIR = ROOT / "report" / "experiment_comparison"

TRAINABLE_WINDOWS_PATH = FEATURE_DIR / "trainable_windows.csv"
BASELINE_METADATA_PATH = DATA_DIR / "ml_baseline" / "models" / "baseline_model_metadata.json"
RISK_SCORES_PATH = RISK_DIR / "lgbm_risk_scores.csv"
RISK_METADATA_PATH = RISK_DIR / "models" / "risk_model_metadata.json"

OUTPUT_METRICS_PATH = REPORT_DIR / "anomaly_risk_integration_metrics.csv"
OUTPUT_HOLDOUT_PATH = REPORT_DIR / "anomaly_risk_integration_holdout.csv"
OUTPUT_FN_PATH = REPORT_DIR / "anomaly_risk_integration_false_negative_summary.csv"
OUTPUT_DETAIL_PATH = REPORT_DIR / "anomaly_risk_integration_detail.json"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
ANOMALY_PRIMARY_SPLIT_COLUMN = "split_time_based"
RISK_PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
BASE_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}
RANDOM_STATE = 42

DRIFT_CANDIDATE_FEATURES = [
    "day_of_year",
    "days_since_last_any_event",
    "p_net_supply_temperature__mean",
    "p_net_supply_temperature__max",
    "network_temperature_gap__mean",
]
THERMAL_KEYWORDS = ["temperature", "temperature_gap", "heat_power", "flow"]


def safe_roc_auc(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def safe_average_precision(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def apply_base_risk_level(score: float) -> str:
    if score >= BASE_THRESHOLDS["critical"]:
        return "critical"
    if score >= BASE_THRESHOLDS["high"]:
        return "high"
    if score >= BASE_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def apply_group_calibrated_risk_level(row: pd.Series, score_column: str) -> str:
    medium = BASE_THRESHOLDS["medium"]
    high = BASE_THRESHOLDS["high"]
    critical = BASE_THRESHOLDS["critical"]
    override = GROUP_OVERRIDES.get((row["manufacturer"], row["configuration_type"]))
    if override:
        high = override.get("high", high)
        critical = max(critical, high)
    score = row[score_column]
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def score_frame(frame: pd.DataFrame, score_column: str, level_column: str) -> dict[str, float | int]:
    y_true = (frame["label"] == "pre_fault").astype(int)
    y_score = frame[score_column]
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
        "roc_auc": safe_roc_auc(y_true, y_score),
        "average_precision": safe_average_precision(y_true, y_score),
        "precision_high_or_critical": float(precision),
        "recall_high_or_critical": float(recall),
        "f1_high_or_critical": float(f1),
        "false_positive_rate_high_or_critical": false_positive_rate(y_true, y_pred),
    }


def build_thermal_feature_set(selected_features: list[str]) -> list[str]:
    return [
        column
        for column in selected_features
        if any(keyword in column for keyword in THERMAL_KEYWORDS)
        or column in [
            "dow_cos",
            "dow_sin",
            "doy_cos",
            "doy_sin",
            "hour_cos",
            "hour_sin",
            "days_since_last_any_event",
            "days_since_last_task_event",
            "has_dhw",
            "has_buffer_tank",
        ]
    ]


def fit_iforest_score(
    frame: pd.DataFrame,
    feature_columns: list[str],
    param_name: str,
) -> tuple[np.ndarray, dict[str, object]]:
    x_all = frame[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
    x_all = x_all.astype(float).fillna(0.0)
    train_normal_mask = frame[ANOMALY_PRIMARY_SPLIT_COLUMN].eq("train") & frame["label"].eq("normal")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_all.loc[train_normal_mask])
    x_scaled = scaler.transform(x_all)

    if param_name == "thermal_trees_600":
        params = {
            "n_estimators": 600,
            "contamination": "auto",
            "max_samples": "auto",
            "max_features": 1.0,
            "bootstrap": False,
        }
    elif param_name == "nodrift_bootstrap":
        params = {
            "n_estimators": 400,
            "contamination": "auto",
            "max_samples": "auto",
            "max_features": 1.0,
            "bootstrap": True,
        }
    else:
        raise ValueError(param_name)
    model = IsolationForest(**params, random_state=RANDOM_STATE, n_jobs=-1)
    model.fit(x_train)
    score = -model.score_samples(x_scaled)
    return score, {"param_name": param_name, "params": params, "feature_count": len(feature_columns)}


def add_train_group_zscore(
    frame: pd.DataFrame,
    score_column: str,
    output_column: str,
) -> pd.Series:
    train_normal = frame[ANOMALY_PRIMARY_SPLIT_COLUMN].eq("train") & frame["label"].eq("normal")
    group_columns = ["manufacturer", "configuration_type", "season_bucket"]
    stats = (
        frame.loc[train_normal]
        .groupby(group_columns, dropna=False)[score_column]
        .agg(["mean", "std"])
        .reset_index()
    )
    global_mean = frame.loc[train_normal, score_column].mean()
    global_std = frame.loc[train_normal, score_column].std()
    merged = frame[group_columns + [score_column]].merge(stats, on=group_columns, how="left")
    mean = merged["mean"].fillna(global_mean)
    std = merged["std"].replace(0, np.nan).fillna(global_std)
    return ((merged[score_column] - mean) / std).fillna(0.0).rename(output_column)


def load_modeling_frame() -> tuple[pd.DataFrame, list[str], list[str], dict]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    baseline_metadata = json.loads(BASELINE_METADATA_PATH.read_text(encoding="utf-8"))
    risk_metadata = json.loads(RISK_METADATA_PATH.read_text(encoding="utf-8"))

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        "configuration_type",
        RISK_PRIMARY_SPLIT_COLUMN,
        "lead_time_bucket",
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
    for base_name in ["label", "configuration_type", RISK_PRIMARY_SPLIT_COLUMN, "lead_time_bucket"]:
        risk_name = f"{base_name}_risk"
        if base_name not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: base_name})
    for column in risk_metadata["model_feature_columns"]:
        risk_name = f"{column}_risk"
        if column not in modeling_df.columns and risk_name in modeling_df.columns:
            modeling_df = modeling_df.rename(columns={risk_name: column})
    if "use_for_supervised_training" in modeling_df.columns:
        modeling_df = modeling_df.loc[modeling_df["use_for_supervised_training"].fillna(True).astype(bool)].copy()
    modeling_df["risk_target"] = (modeling_df["label"] == "pre_fault").astype(int)
    return modeling_df, baseline_metadata["selected_feature_columns"], risk_metadata["model_feature_columns"], risk_metadata


def make_numeric_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    x = frame[columns].copy()
    for column in x.columns:
        if x[column].dtype == "bool":
            x[column] = x[column].astype("int8")
        elif x[column].dtype == "object":
            x[column] = pd.to_numeric(x[column], errors="coerce")
    return x.fillna(0.0)


def train_risk_variant(
    frame: pd.DataFrame,
    feature_columns: list[str],
    variant_name: str,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    x_all = make_numeric_frame(frame, feature_columns)
    train_mask = frame[RISK_PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = frame[RISK_PRIMARY_SPLIT_COLUMN].eq("validation")
    y_all = frame["risk_target"].astype(int)
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
    scored = frame.copy()
    score_column = f"{variant_name}__risk_probability"
    base_level_column = f"{variant_name}__risk_level_base"
    cal_level_column = f"{variant_name}__risk_level_calibrated"
    scored[score_column] = model.predict_proba(x_all[feature_columns])[:, 1]
    scored[base_level_column] = scored[score_column].map(apply_base_risk_level)
    scored[cal_level_column] = scored.apply(lambda row: apply_group_calibrated_risk_level(row, score_column), axis=1)

    rows: list[dict[str, object]] = []
    scope_filters = {
        "overall": pd.Series(True, index=scored.index),
        "manufacturer_2_sh": scored["manufacturer"].eq("manufacturer 2") & scored["configuration_type"].eq("SH"),
    }
    for split_name, split_mask in {
        "train": scored[RISK_PRIMARY_SPLIT_COLUMN].eq("train"),
        "validation": scored[RISK_PRIMARY_SPLIT_COLUMN].eq("validation"),
        "holdout": scored[RISK_PRIMARY_SPLIT_COLUMN].eq("holdout"),
    }.items():
        for scope_name, scope_mask in scope_filters.items():
            split_frame = scored.loc[split_mask & scope_mask].copy()
            if split_frame.empty:
                continue
            for metric_type, level_column in {"base": base_level_column, "calibrated": cal_level_column}.items():
                rows.append(
                    {
                        "variant": variant_name,
                        "feature_count": len(feature_columns),
                        "split": split_name,
                        "scope": scope_name,
                        "metric_type": metric_type,
                        **score_frame(split_frame, score_column, level_column),
                    }
                )
    return scored, rows


def false_negative_summary(scored: pd.DataFrame, variant_name: str) -> list[dict[str, object]]:
    rows = []
    for metric_type in ["base", "calibrated"]:
        level_column = f"{variant_name}__risk_level_{metric_type}"
        holdout_fn = scored.loc[
            scored[RISK_PRIMARY_SPLIT_COLUMN].eq("holdout")
            & scored["label"].eq("pre_fault")
            & ~scored[level_column].isin(["high", "critical"])
        ].copy()
        rows.append(
            {
                "variant": variant_name,
                "metric_type": metric_type,
                "false_negative_count": int(len(holdout_fn)),
                "fn_1_3d_count": int(holdout_fn["lead_time_bucket"].eq("1-3d").sum()) if "lead_time_bucket" in holdout_fn.columns else None,
                "fn_medium_count": int(holdout_fn[level_column].eq("medium").sum()),
                "fn_low_count": int(holdout_fn[level_column].eq("low").sum()),
                "mean_risk_probability": float(holdout_fn[f"{variant_name}__risk_probability"].mean()) if len(holdout_fn) else np.nan,
            }
        )
    return rows


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    frame, selected_features, risk_features, risk_metadata = load_modeling_frame()

    thermal_features = build_thermal_feature_set(selected_features)
    nodrift_features = [column for column in selected_features if column not in DRIFT_CANDIDATE_FEATURES]
    thermal_score, thermal_detail = fit_iforest_score(frame, thermal_features, "thermal_trees_600")
    nodrift_score, nodrift_detail = fit_iforest_score(frame, nodrift_features, "nodrift_bootstrap")

    frame["thermal_iforest_anomaly_score"] = thermal_score
    frame["nodrift_iforest_anomaly_score"] = nodrift_score
    frame["thermal_iforest_anomaly_z_by_group"] = add_train_group_zscore(
        frame, "thermal_iforest_anomaly_score", "thermal_iforest_anomaly_z_by_group"
    ).to_numpy()
    frame["nodrift_iforest_anomaly_z_by_group"] = add_train_group_zscore(
        frame, "nodrift_iforest_anomaly_score", "nodrift_iforest_anomaly_z_by_group"
    ).to_numpy()

    variants = {
        "risk_baseline_retrained": risk_features,
        "risk_plus_thermal_iforest": risk_features + ["thermal_iforest_anomaly_score"],
        "risk_plus_thermal_iforest_z": risk_features + ["thermal_iforest_anomaly_score", "thermal_iforest_anomaly_z_by_group"],
        "risk_plus_nodrift_iforest": risk_features + ["nodrift_iforest_anomaly_score"],
        "risk_plus_both_iforest_scores": risk_features + ["thermal_iforest_anomaly_score", "nodrift_iforest_anomaly_score"],
        "risk_plus_both_iforest_z": risk_features
        + [
            "thermal_iforest_anomaly_score",
            "thermal_iforest_anomaly_z_by_group",
            "nodrift_iforest_anomaly_score",
            "nodrift_iforest_anomaly_z_by_group",
        ],
    }

    metric_rows: list[dict[str, object]] = []
    fn_rows: list[dict[str, object]] = []
    for variant_name, feature_columns in variants.items():
        scored, rows = train_risk_variant(frame, feature_columns, variant_name)
        metric_rows.extend(rows)
        fn_rows.extend(false_negative_summary(scored, variant_name))

    metrics = pd.DataFrame(metric_rows)
    holdout = metrics[metrics["split"].eq("holdout")].copy().sort_values(
        ["scope", "metric_type", "f1_high_or_critical", "false_positive_rate_high_or_critical"],
        ascending=[True, True, False, True],
    )
    fn_summary = pd.DataFrame(fn_rows).sort_values(["metric_type", "false_negative_count", "fn_1_3d_count"])

    metrics.to_csv(OUTPUT_METRICS_PATH, index=False, encoding="utf-8-sig")
    holdout.to_csv(OUTPUT_HOLDOUT_PATH, index=False, encoding="utf-8-sig")
    fn_summary.to_csv(OUTPUT_FN_PATH, index=False, encoding="utf-8-sig")
    detail = {
        "purpose": "Evaluate whether alternative Isolation Forest anomaly scores improve downstream LightGBM risk performance.",
        "contract_feature_count": len(selected_features),
        "risk_base_model_version": risk_metadata.get("model_version"),
        "thermal_iforest": {**thermal_detail, "feature_set": "thermal_core_plus_cyclic_event"},
        "nodrift_iforest": {**nodrift_detail, "feature_set": "no_drift_candidates"},
        "variants": {name: len(columns) for name, columns in variants.items()},
        "outputs": {
            "metrics": str(OUTPUT_METRICS_PATH),
            "holdout": str(OUTPUT_HOLDOUT_PATH),
            "false_negative": str(OUTPUT_FN_PATH),
        },
    }
    OUTPUT_DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")

    print(OUTPUT_METRICS_PATH)
    print(OUTPUT_HOLDOUT_PATH)
    print(OUTPUT_FN_PATH)
    print(OUTPUT_DETAIL_PATH)
    print()
    print(holdout.to_string(index=False))
    print()
    print(fn_summary.to_string(index=False))


if __name__ == "__main__":
    main()
