from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
ML_LEADTIME_DIR = DATA_DIR / "ml_leadtime"
MODEL_DIR = ML_LEADTIME_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
RISK_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores.csv"
BASE_METADATA_PATH = MODEL_DIR / "leadtime_bucket_model_metadata.json"

PROMOTED_SCORES_PATH = ML_LEADTIME_DIR / "leadtime_bucket_scores_promoted.csv"
PROMOTED_METRICS_PATH = ML_LEADTIME_DIR / "leadtime_bucket_metrics_promoted.csv"
PROMOTED_CONFUSION_PATH = ML_LEADTIME_DIR / "leadtime_bucket_confusion_matrix_promoted.csv"
PROMOTED_MODEL_PATH = MODEL_DIR / "lightgbm_leadtime_bucket_model_promoted.joblib"
PROMOTED_METADATA_PATH = MODEL_DIR / "leadtime_bucket_model_promoted_metadata.json"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
LEADTIME_LABELS = ["0-24h", "1-3d", "3-7d"]
LEADTIME_LABEL_TO_INDEX = {label: index for index, label in enumerate(LEADTIME_LABELS)}
LEADTIME_BUCKET_MAPPING = {"0-6h": "0-24h", "6-24h": "0-24h", "1-3d": "1-3d", "3-7d": "3-7d"}
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
RANDOM_STATE = 42
MODEL_VERSION = "lgbm_leadtime_bucket_v3_timeflow_3bucket"

TIMEFLOW_SOURCE_COLUMNS = [
    "anomaly_score",
    "risk_probability",
    "network_temperature_gap__mean",
    "p_net_return_temperature__mean",
    "p_net_supply_temperature__mean",
    "days_since_last_task_event",
    "days_since_last_any_event",
]


def load_base_frame() -> tuple[pd.DataFrame, list[str], dict]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(BASE_METADATA_PATH.read_text(encoding="utf-8"))

    model_feature_columns = metadata["model_feature_columns"]
    risk_context_columns = [
        column
        for column in [
            "anomaly_score",
            "risk_probability",
            "risk_score",
            "disturbance_count",
            "maintenance_related",
            "days_since_last_fault_event",
            "days_since_last_task_event",
            "days_since_last_any_event",
            "split_event_based",
            "split_event_regime_based",
            "split_regime_based",
            "split_time_based",
            "split_substation_based",
            "lead_time_bucket",
            "estimated_lead_time_hours",
            "risk_level",
            "label",
            "fault_event_id",
            "fault_label",
            "configuration_type",
        ]
        if column in risk_scores.columns
    ]

    trainable_feature_columns = [
        column
        for column in model_feature_columns
        if column in trainable_windows.columns and column not in risk_context_columns
    ]

    modeling_df = risk_scores[KEY_COLUMNS + risk_context_columns].merge(
        trainable_windows[KEY_COLUMNS + [column for column in trainable_feature_columns if column not in KEY_COLUMNS]],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )

    if "manufacturer" in modeling_df.columns:
        modeling_df["manufacturer_code"] = modeling_df["manufacturer"].astype("category").cat.codes.astype("int16")
    if "configuration_type" in modeling_df.columns:
        modeling_df["configuration_code"] = (
            modeling_df["configuration_type"].fillna("missing").astype("category").cat.codes.astype("int16")
        )

    if "maintenance_related" in modeling_df.columns:
        modeling_df["maintenance_related"] = modeling_df["maintenance_related"].fillna(False).astype("int8")
    if "disturbance_count" in modeling_df.columns:
        modeling_df["disturbance_count"] = modeling_df["disturbance_count"].fillna(0)

    modeling_df["lead_time_bucket_3"] = modeling_df["lead_time_bucket"].map(LEADTIME_BUCKET_MAPPING)
    pre_fault_df = modeling_df.loc[
        modeling_df["label"].eq("pre_fault")
        & modeling_df["lead_time_bucket_3"].isin(LEADTIME_LABELS)
    ].copy()
    pre_fault_df["lead_time_bucket"] = pre_fault_df["lead_time_bucket_3"]
    pre_fault_df["lead_time_target"] = pre_fault_df["lead_time_bucket"].map(LEADTIME_LABEL_TO_INDEX).astype(int)
    return pre_fault_df, model_feature_columns, metadata


def make_numeric_frame(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    x_all = frame[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    return x_all


def add_timeflow_features(frame: pd.DataFrame, x_all: pd.DataFrame) -> pd.DataFrame:
    result = x_all.copy()
    working = frame.copy()
    working["window_end"] = pd.to_datetime(working["window_end"])
    working = working.sort_values(["fault_event_id", "window_end", "window_start"]).copy()

    extra = pd.DataFrame(index=working.index)
    available = [column for column in TIMEFLOW_SOURCE_COLUMNS if column in working.columns]
    grouped = working.groupby("fault_event_id", dropna=False)

    for column in available:
        numeric = pd.to_numeric(working[column], errors="coerce")
        lag1 = pd.to_numeric(grouped[column].shift(1), errors="coerce")
        lag2 = pd.to_numeric(grouped[column].shift(2), errors="coerce")
        roll3 = pd.to_numeric(
            grouped[column].rolling(3, min_periods=1).mean().reset_index(level=0, drop=True),
            errors="coerce",
        )
        extra[f"{column}__lag1"] = lag1.fillna(numeric).astype("float64")
        extra[f"{column}__delta1"] = (numeric - lag1).fillna(0.0).astype("float64")
        extra[f"{column}__lag2"] = lag2.fillna(numeric).astype("float64")
        extra[f"{column}__roll3_mean"] = roll3.fillna(numeric).astype("float64")

    extra = extra.reindex(frame.index)
    return pd.concat([result, extra], axis=1).fillna(0.0)


def top2_accuracy(probabilities, y_true: pd.Series) -> float:
    top2 = probabilities.argsort(axis=1)[:, -2:]
    truth = y_true.to_numpy().reshape(-1, 1)
    return float((top2 == truth).any(axis=1).mean())


def bucket_distance(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float((y_true - y_pred).abs().mean())


def main() -> None:
    pre_fault_df, base_feature_columns, base_metadata = load_base_frame()
    x_all = make_numeric_frame(pre_fault_df, base_feature_columns)
    x_all = add_timeflow_features(pre_fault_df, x_all)

    train_mask = pre_fault_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = pre_fault_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = pre_fault_df[PRIMARY_SPLIT_COLUMN].eq("holdout")
    y_all = pre_fault_df["lead_time_target"].astype(int)

    leadtime_model = LGBMClassifier(
        objective="multiclass",
        num_class=len(LEADTIME_LABELS),
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=20,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_alpha=0.1,
        reg_lambda=1.0,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=-1,
    )
    leadtime_model.fit(
        x_all.loc[train_mask],
        y_all.loc[train_mask],
        eval_set=[(x_all.loc[validation_mask], y_all.loc[validation_mask])],
        eval_metric="multi_logloss",
    )

    probabilities = leadtime_model.predict_proba(x_all)
    predicted_index = probabilities.argmax(axis=1)
    predicted_bucket = [LEADTIME_LABELS[index] for index in predicted_index]
    predicted_confidence = probabilities.max(axis=1)

    scored_df = pre_fault_df.copy()
    scored_df["predicted_lead_time_bucket"] = predicted_bucket
    scored_df["predicted_lead_time_confidence"] = predicted_confidence
    scored_df["predicted_lead_time_index"] = predicted_index
    scored_df["lead_time_bucket_distance"] = (
        scored_df["lead_time_target"] - scored_df["predicted_lead_time_index"]
    ).abs()
    for index, label in enumerate(LEADTIME_LABELS):
        scored_df[f"leadtime_prob_{label}"] = probabilities[:, index]
    scored_df["model_version"] = MODEL_VERSION

    metric_rows: list[dict] = []
    confusion_rows: list[dict] = []
    for split_name, split_mask in {
        "train": train_mask,
        "validation": validation_mask,
        "holdout": holdout_mask,
    }.items():
        split_df = scored_df.loc[split_mask].copy()
        y_true = split_df["lead_time_target"].astype(int)
        y_pred = split_df["predicted_lead_time_index"].astype(int)
        split_prob = probabilities[split_mask.to_numpy()]
        metric_rows.append(
            {
                "split": split_name,
                "row_count": int(len(split_df)),
                "accuracy": float(accuracy_score(y_true, y_pred)),
                "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
                "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
                "top2_accuracy": float(top2_accuracy(split_prob, y_true)),
                "bucket_distance_mae": float(bucket_distance(y_true, y_pred)),
            }
        )

        matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(LEADTIME_LABELS))))
        for true_index, true_label in enumerate(LEADTIME_LABELS):
            for pred_index, pred_label in enumerate(LEADTIME_LABELS):
                confusion_rows.append(
                    {
                        "split": split_name,
                        "actual_bucket": true_label,
                        "predicted_bucket": pred_label,
                        "count": int(matrix[true_index, pred_index]),
                    }
                )

    metrics_df = pd.DataFrame(metric_rows)
    confusion_df = pd.DataFrame(confusion_rows)

    scored_df.to_csv(PROMOTED_SCORES_PATH, index=False, encoding="utf-8-sig")
    metrics_df.to_csv(PROMOTED_METRICS_PATH, index=False, encoding="utf-8-sig")
    confusion_df.to_csv(PROMOTED_CONFUSION_PATH, index=False, encoding="utf-8-sig")
    joblib.dump(leadtime_model, PROMOTED_MODEL_PATH)

    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": "LightGBM LGBMClassifier multiclass",
        "promotion_basis": "3-bucket baseline plus timeflow_lag_delta_roll3 features",
        "target_definition": "pseudo lead time bucket within pre_fault rows only",
        "leadtime_labels": LEADTIME_LABELS,
        "primary_split_column": PRIMARY_SPLIT_COLUMN,
        "feature_count": int(x_all.shape[1]),
        "model_feature_columns": x_all.columns.tolist(),
        "base_model_version": base_metadata.get("model_version"),
        "metrics": metric_rows,
        "input_trainable_windows_path": str(TRAINABLE_WINDOWS_PATH),
        "input_risk_scores_path": str(RISK_SCORES_PATH),
        "output_scores_path": str(PROMOTED_SCORES_PATH),
        "output_metrics_path": str(PROMOTED_METRICS_PATH),
        "output_confusion_path": str(PROMOTED_CONFUSION_PATH),
        "output_model_path": str(PROMOTED_MODEL_PATH),
    }
    PROMOTED_METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(PROMOTED_SCORES_PATH)
    print(PROMOTED_METRICS_PATH)
    print(PROMOTED_CONFUSION_PATH)
    print(PROMOTED_MODEL_PATH)
    print(PROMOTED_METADATA_PATH)
    print()
    print(metrics_df.to_string(index=False))


if __name__ == "__main__":
    main()
