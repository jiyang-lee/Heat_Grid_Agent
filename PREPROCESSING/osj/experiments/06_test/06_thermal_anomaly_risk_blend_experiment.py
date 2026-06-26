from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
FEATURE_DIR = DATA_DIR / "ml_features"
BASELINE_DIR = DATA_DIR / "ml_baseline" / "models"
RISK_DIR = DATA_DIR / "ml_risk"
REPORT_DIR = ROOT / "report" / "experiment_comparison"

TRAINABLE_WINDOWS_PATH = FEATURE_DIR / "trainable_windows.csv"
BASELINE_METADATA_PATH = BASELINE_DIR / "baseline_model_metadata.json"
OFFICIAL_RISK_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"

OUTPUT_METRICS_PATH = REPORT_DIR / "thermal_anomaly_risk_blend_metrics.csv"
OUTPUT_HOLDOUT_PATH = REPORT_DIR / "thermal_anomaly_risk_blend_holdout.csv"
OUTPUT_DETAIL_PATH = REPORT_DIR / "thermal_anomaly_risk_blend_detail.json"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
ANOMALY_SPLIT_COLUMN = "split_time_based"
RISK_SPLIT_COLUMN = "split_event_regime_based"
BASE_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}
THERMAL_KEYWORDS = ["temperature", "temperature_gap", "heat_power", "flow"]
CONTEXT_FEATURES = [
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
BLEND_WEIGHTS = [0.0, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30]
RANDOM_STATE = 42


def safe_roc_auc(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def safe_ap(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def risk_level_for_row(row: pd.Series, score_column: str) -> str:
    score = float(row[score_column])
    medium = BASE_THRESHOLDS["medium"]
    high = BASE_THRESHOLDS["high"]
    critical = BASE_THRESHOLDS["critical"]
    override = GROUP_OVERRIDES.get((row.get("manufacturer"), row.get("configuration_type")))
    if override:
        high = override.get("high", high)
        critical = override.get("critical", critical)
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def metric_row(df: pd.DataFrame, variant: str, scope: str, score_column: str, pred_column: str) -> dict:
    y_true = df["target"].astype(int)
    y_score = df[score_column].astype(float)
    y_pred = df[pred_column].astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    return {
        "variant": variant,
        "scope": scope,
        "rows": int(len(df)),
        "positives": int(y_true.sum()),
        "roc_auc": safe_roc_auc(y_true, y_score),
        "average_precision": safe_ap(y_true, y_score),
        "precision_high_or_critical": float(precision),
        "recall_high_or_critical": float(recall),
        "f1_high_or_critical": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "predicted_positive_rate": float(y_pred.mean()) if len(y_pred) else float("nan"),
    }


def select_thermal_features(all_features: list[str], available_columns: set[str]) -> list[str]:
    thermal = [
        col
        for col in all_features
        if col in available_columns and any(keyword in col for keyword in THERMAL_KEYWORDS)
    ]
    context = [col for col in CONTEXT_FEATURES if col in available_columns]
    selected = list(dict.fromkeys(thermal + context))
    if not selected:
        raise ValueError("No thermal/context features found for Isolation Forest experiment.")
    return selected


def empirical_percentile(scores: np.ndarray, reference_scores: np.ndarray) -> np.ndarray:
    sorted_ref = np.sort(reference_scores)
    ranks = np.searchsorted(sorted_ref, scores, side="right")
    return ranks / max(len(sorted_ref), 1)


def build_thermal_anomaly_score(features_df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    model_df = features_df[KEY_COLUMNS + ["label", ANOMALY_SPLIT_COLUMN] + feature_columns].copy()
    train_normal_mask = model_df[ANOMALY_SPLIT_COLUMN].eq("train") & model_df["label"].eq("normal")
    if int(train_normal_mask.sum()) == 0:
        raise ValueError("No train normal rows found for thermal Isolation Forest.")

    medians = model_df.loc[train_normal_mask, feature_columns].median(numeric_only=True).fillna(0.0)
    x_all = model_df[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0.0)
    x_train = x_all.loc[train_normal_mask]

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_all_scaled = scaler.transform(x_all)

    iforest = IsolationForest(
        n_estimators=600,
        contamination="auto",
        max_samples="auto",
        max_features=1.0,
        bootstrap=False,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    iforest.fit(x_train_scaled)

    raw_scores = -iforest.score_samples(x_all_scaled)
    train_ref_scores = raw_scores[train_normal_mask.to_numpy()]
    percentiles = empirical_percentile(raw_scores, train_ref_scores)

    return pd.DataFrame(
        {
            **{col: features_df[col].values for col in KEY_COLUMNS},
            "thermal_anomaly_raw_score": raw_scores,
            "thermal_anomaly_percentile": percentiles,
        }
    )


def evaluate_variant(df: pd.DataFrame, variant: str, score_column: str, level_column: str) -> list[dict]:
    eval_df = df[df[RISK_SPLIT_COLUMN].eq("holdout")].copy()
    eval_df["target"] = eval_df["label"].eq("pre_fault").astype(int)
    eval_df["predicted_positive"] = eval_df[level_column].isin(["high", "critical"]).astype(int)

    rows = [metric_row(eval_df, variant, "holdout_all", score_column, "predicted_positive")]
    group_mask = eval_df["manufacturer"].eq("manufacturer 2") & eval_df["configuration_type"].eq("SH")
    if int(group_mask.sum()) > 0:
        rows.append(metric_row(eval_df[group_mask], variant, "holdout_manufacturer2_SH", score_column, "predicted_positive"))
    return rows


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    features_df = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    official_risk_df = pd.read_csv(OFFICIAL_RISK_PATH)
    metadata = json.loads(BASELINE_METADATA_PATH.read_text(encoding="utf-8"))
    contract_features = metadata["selected_feature_columns"]
    thermal_features = select_thermal_features(contract_features, set(features_df.columns))

    thermal_scores = build_thermal_anomaly_score(features_df, thermal_features)
    base = official_risk_df.merge(thermal_scores, on=KEY_COLUMNS, how="left", validate="one_to_one")
    if base["thermal_anomaly_percentile"].isna().any():
        missing = int(base["thermal_anomaly_percentile"].isna().sum())
        raise ValueError(f"Missing thermal anomaly scores after merge: {missing}")

    base["official_high_or_critical"] = base["risk_level_calibrated"].isin(["high", "critical"]).astype(int)

    metrics: list[dict] = []
    holdout_frames: list[pd.DataFrame] = []
    for weight in BLEND_WEIGHTS:
        variant = "official_risk_calibrated" if weight == 0.0 else f"official_risk_plus_thermal_w{weight:.2f}"
        score_column = f"{variant}__risk_probability"
        level_column = f"{variant}__risk_level"
        base[score_column] = (
            (1.0 - weight) * base["risk_probability"].astype(float)
            + weight * base["thermal_anomaly_percentile"].astype(float)
        ).clip(0.0, 1.0)
        base[level_column] = base.apply(lambda row: risk_level_for_row(row, score_column), axis=1)
        metrics.extend(evaluate_variant(base, variant, score_column, level_column))

        holdout_part = base[base[RISK_SPLIT_COLUMN].eq("holdout")][
            KEY_COLUMNS
            + [
                "label",
                "fault_event_id",
                "configuration_type",
                "risk_probability",
                "risk_level_calibrated",
                "thermal_anomaly_percentile",
                score_column,
                level_column,
            ]
        ].copy()
        holdout_part["variant"] = variant
        holdout_part = holdout_part.rename(
            columns={
                score_column: "candidate_risk_probability",
                level_column: "candidate_risk_level",
            }
        )
        holdout_frames.append(holdout_part)

    metrics_df = pd.DataFrame(metrics).sort_values(["scope", "f1_high_or_critical", "roc_auc"], ascending=[True, False, False])
    holdout_df = pd.concat(holdout_frames, ignore_index=True)

    detail = {
        "experiment": "official risk score post-hoc thermal anomaly blend",
        "official_risk_path": str(OFFICIAL_RISK_PATH),
        "trainable_windows_path": str(TRAINABLE_WINDOWS_PATH),
        "baseline_metadata_path": str(BASELINE_METADATA_PATH),
        "thermal_feature_count": len(thermal_features),
        "thermal_features": thermal_features,
        "blend_weights": BLEND_WEIGHTS,
        "risk_thresholds": BASE_THRESHOLDS,
        "group_overrides": {str(k): v for k, v in GROUP_OVERRIDES.items()},
        "notes": [
            "This does not retrain or overwrite the official risk model.",
            "Thermal anomaly percentile is calibrated against train-normal empirical distribution.",
            "A replacement should only be considered if holdout F1/ROC-AUC improves without unacceptable FPR increase.",
        ],
    }

    metrics_df.to_csv(OUTPUT_METRICS_PATH, index=False, encoding="utf-8-sig")
    holdout_df.to_csv(OUTPUT_HOLDOUT_PATH, index=False, encoding="utf-8-sig")
    OUTPUT_DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")

    print(OUTPUT_METRICS_PATH)
    print(OUTPUT_HOLDOUT_PATH)
    print(OUTPUT_DETAIL_PATH)
    print()
    print(metrics_df.to_string(index=False))


if __name__ == "__main__":
    main()
