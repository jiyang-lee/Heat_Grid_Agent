from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[4]
FEATURE_DIR = ROOT / "data" / "processed" / "ml_features"
OUT_DIR = ROOT / "report" / "experiment_comparison"

TRAINABLE_WINDOWS_PATH = FEATURE_DIR / "trainable_windows.csv"
FEATURE_COLUMNS_PATH = FEATURE_DIR / "feature_columns.csv"
BASE_METADATA_PATH = ROOT / "data" / "processed" / "ml_baseline" / "models" / "baseline_model_metadata.json"

METRICS_PATH = OUT_DIR / "iforest_feature_hyperparam_metrics.csv"
SUMMARY_PATH = OUT_DIR / "iforest_feature_hyperparam_summary.csv"
DETAIL_PATH = OUT_DIR / "iforest_feature_hyperparam_detail.json"

PRIMARY_SPLIT_COLUMN = "split_time_based"
EVALUATION_SPLIT_COLUMNS = ["split_time_based", "split_substation_based"]
SPLIT_VALUES = ["train", "validation", "holdout"]
THRESHOLD_QUANTILES = [0.95, 0.975, 0.99]
RANDOM_STATE = 42

DRIFT_CANDIDATE_FEATURES = [
    "day_of_year",
    "days_since_last_any_event",
    "p_net_supply_temperature__mean",
    "p_net_supply_temperature__max",
    "network_temperature_gap__mean",
]

THERMAL_KEYWORDS = [
    "temperature",
    "temperature_gap",
    "heat_power",
    "flow",
]


def safe_roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def safe_average_precision(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def false_positive_rate(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    negative_mask = y_true == 0
    if negative_mask.sum() == 0:
        return float("nan")
    return float(((y_pred == 1) & negative_mask).sum() / negative_mask.sum())


def build_feature_sets(feature_table: pd.DataFrame, selected_features: list[str]) -> dict[str, list[str]]:
    selected = feature_table[feature_table["column_name"].isin(selected_features)].copy()

    def family(names: list[str]) -> list[str]:
        return selected.loc[selected["feature_family"].isin(names), "column_name"].tolist()

    sensor = family(["sensor_numeric"])
    cyclic = family(["cyclic_time"])
    time_context = family(["time_context"])
    one_hot = family(["derived_one_hot"])
    event = family(["event_context"])

    thermal_core = [
        column
        for column in selected_features
        if any(keyword in column for keyword in THERMAL_KEYWORDS)
        or column in ["has_dhw", "has_buffer_tank", "anomaly_score"]
    ]
    thermal_core = [column for column in thermal_core if column in selected_features]

    no_drift = [column for column in selected_features if column not in DRIFT_CANDIDATE_FEATURES]
    no_context = [column for column in selected_features if column not in set(one_hot + event + time_context)]

    feature_sets = {
        "contract_195_full": selected_features,
        "sensor_numeric_only": sensor,
        "sensor_plus_cyclic": sensor + cyclic,
        "sensor_cyclic_event": sensor + cyclic + event,
        "sensor_cyclic_onehot": sensor + cyclic + one_hot,
        "no_time_context": [column for column in selected_features if column not in time_context],
        "no_drift_candidates": no_drift,
        "no_context_features": no_context,
        "thermal_core_plus_cyclic_event": sorted(set(thermal_core + cyclic + event)),
    }
    return {name: columns for name, columns in feature_sets.items() if columns}


def evaluate_scores(
    frame: pd.DataFrame,
    score: np.ndarray,
    threshold_values: dict[float, float],
    feature_set_name: str,
    param_name: str,
    feature_count: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split_column in EVALUATION_SPLIT_COLUMNS:
        for split_name in SPLIT_VALUES:
            mask = frame[split_column].eq(split_name)
            split_df = frame.loc[mask]
            y_true = (split_df["label"] == "pre_fault").astype(int).to_numpy()
            y_score = score[mask.to_numpy()]
            for quantile, threshold in threshold_values.items():
                y_pred = (y_score >= threshold).astype(int)
                precision, recall, f1, _ = precision_recall_fscore_support(
                    y_true,
                    y_pred,
                    average="binary",
                    zero_division=0,
                )
                rows.append(
                    {
                        "feature_set": feature_set_name,
                        "param_set": param_name,
                        "feature_count": feature_count,
                        "evaluation_split_column": split_column,
                        "split": split_name,
                        "threshold_quantile": quantile,
                        "threshold_value": threshold,
                        "row_count": int(len(split_df)),
                        "normal_count": int((split_df["label"] == "normal").sum()),
                        "pre_fault_count": int((split_df["label"] == "pre_fault").sum()),
                        "roc_auc": safe_roc_auc(y_true, y_score),
                        "average_precision": safe_average_precision(y_true, y_score),
                        "precision": float(precision),
                        "recall": float(recall),
                        "f1": float(f1),
                        "false_positive_rate": false_positive_rate(y_true, y_pred),
                    }
                )
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    feature_table = pd.read_csv(FEATURE_COLUMNS_PATH)
    metadata = json.loads(BASE_METADATA_PATH.read_text(encoding="utf-8"))

    selected_features = metadata["selected_feature_columns"]
    feature_sets = build_feature_sets(feature_table, selected_features)

    param_sets: dict[str, dict[str, object]] = {
        "default_300_auto": {
            "n_estimators": 300,
            "contamination": "auto",
            "max_samples": "auto",
            "max_features": 1.0,
            "bootstrap": False,
        },
        "trees_600": {
            "n_estimators": 600,
            "contamination": "auto",
            "max_samples": "auto",
            "max_features": 1.0,
            "bootstrap": False,
        },
        "max_samples_256": {
            "n_estimators": 400,
            "contamination": "auto",
            "max_samples": 256,
            "max_features": 1.0,
            "bootstrap": False,
        },
        "max_samples_512": {
            "n_estimators": 400,
            "contamination": "auto",
            "max_samples": 512,
            "max_features": 1.0,
            "bootstrap": False,
        },
        "max_features_075": {
            "n_estimators": 400,
            "contamination": "auto",
            "max_samples": "auto",
            "max_features": 0.75,
            "bootstrap": False,
        },
        "bootstrap_true": {
            "n_estimators": 400,
            "contamination": "auto",
            "max_samples": "auto",
            "max_features": 1.0,
            "bootstrap": True,
        },
    }

    train_normal_mask = trainable_windows[PRIMARY_SPLIT_COLUMN].eq("train") & trainable_windows["label"].eq("normal")
    metric_rows: list[dict[str, object]] = []
    detail: dict[str, object] = {
        "base_feature_contract_count": len(selected_features),
        "base_feature_contract_source": str(BASE_METADATA_PATH),
        "feature_sets": {name: len(columns) for name, columns in feature_sets.items()},
        "param_sets": param_sets,
    }

    for feature_set_name, columns in feature_sets.items():
        x_all = trainable_windows[columns].copy()
        for column in x_all.columns:
            if x_all[column].dtype == bool:
                x_all[column] = x_all[column].astype("int8")
        x_all = x_all.astype(float).fillna(0.0)

        scaler = StandardScaler()
        x_train_normal = scaler.fit_transform(x_all.loc[train_normal_mask])
        x_scaled = scaler.transform(x_all)

        for param_name, params in param_sets.items():
            model = IsolationForest(
                **params,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
            model.fit(x_train_normal)
            score = -model.score_samples(x_scaled)
            train_normal_scores = score[train_normal_mask.to_numpy()]
            threshold_values = {
                quantile: float(np.quantile(train_normal_scores, quantile))
                for quantile in THRESHOLD_QUANTILES
            }
            metric_rows.extend(
                evaluate_scores(
                    trainable_windows,
                    score,
                    threshold_values,
                    feature_set_name,
                    param_name,
                    len(columns),
                )
            )

    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(METRICS_PATH, index=False, encoding="utf-8-sig")

    holdout = metrics[
        metrics["evaluation_split_column"].eq("split_time_based")
        & metrics["split"].eq("holdout")
        & metrics["threshold_quantile"].eq(0.99)
    ].copy()

    baseline = holdout[
        holdout["feature_set"].eq("contract_195_full")
        & holdout["param_set"].eq("default_300_auto")
    ].iloc[0]

    holdout["delta_roc_auc_vs_baseline"] = holdout["roc_auc"] - baseline["roc_auc"]
    holdout["delta_ap_vs_baseline"] = holdout["average_precision"] - baseline["average_precision"]
    holdout["delta_f1_vs_baseline"] = holdout["f1"] - baseline["f1"]
    holdout["delta_recall_vs_baseline"] = holdout["recall"] - baseline["recall"]
    holdout["delta_fpr_vs_baseline"] = holdout["false_positive_rate"] - baseline["false_positive_rate"]
    holdout = holdout.sort_values(
        ["roc_auc", "average_precision", "f1"],
        ascending=[False, False, False],
    )
    holdout.to_csv(SUMMARY_PATH, index=False, encoding="utf-8-sig")

    detail["baseline_holdout"] = baseline.to_dict()
    detail["best_holdout_by_roc_auc"] = holdout.iloc[0].to_dict()
    detail["best_holdout_by_average_precision"] = holdout.sort_values(
        ["average_precision", "roc_auc"],
        ascending=[False, False],
    ).iloc[0].to_dict()
    DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")

    print(METRICS_PATH)
    print(SUMMARY_PATH)
    print(DETAIL_PATH)
    print("\nBaseline holdout:")
    print(baseline[["feature_set", "param_set", "feature_count", "roc_auc", "average_precision", "precision", "recall", "f1", "false_positive_rate"]].to_string())
    print("\nTop holdout by ROC-AUC:")
    print(
        holdout[
            [
                "feature_set",
                "param_set",
                "feature_count",
                "roc_auc",
                "average_precision",
                "precision",
                "recall",
                "f1",
                "false_positive_rate",
                "delta_roc_auc_vs_baseline",
                "delta_ap_vs_baseline",
            ]
        ].head(15).to_string(index=False)
    )


if __name__ == "__main__":
    main()
