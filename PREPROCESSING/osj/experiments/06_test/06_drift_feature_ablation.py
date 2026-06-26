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

OUTPUT_PATH = ML_RISK_DIR / "lgbm_risk_drift_feature_ablation.csv"
OUTPUT_HOLDOUT_PATH = ML_RISK_DIR / "lgbm_risk_drift_feature_ablation_holdout.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
FIXED_THRESHOLD = 0.44
RANDOM_STATE = 42


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = (y_true == 0)
    negative_count = int(negatives.sum())
    if negative_count == 0:
        return 0.0
    fp = int(((y_pred == 1) & negatives).sum())
    return fp / negative_count


def score_frame(frame: pd.DataFrame, threshold: float) -> dict:
    y_true = frame["risk_target"].astype(int)
    y_score = frame["risk_probability"]
    y_pred = (y_score >= threshold).astype(int)
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


def main() -> None:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_MODEL_METADATA_PATH.read_text(encoding="utf-8"))

    merge_columns = [
        *KEY_COLUMNS,
        "label",
        PRIMARY_SPLIT_COLUMN,
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
    if "maintenance_related" in modeling_df.columns:
        modeling_df["maintenance_related"] = modeling_df["maintenance_related"].map(
            {True: 1, False: 0, "True": 1, "False": 0}
        ).fillna(0).astype("int8")

    modeling_df["risk_target"] = (modeling_df["label"] == "pre_fault").astype(int)

    base_features = metadata["model_feature_columns"]
    x_all = modeling_df[base_features].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    if x_all.isna().any().any():
        missing_summary = x_all.isna().sum()
        missing_summary = missing_summary[missing_summary > 0].sort_values(ascending=False)
        raise ValueError("Ablation input contains missing values:\n" + str(missing_summary.head(20)))

    train_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = modeling_df[PRIMARY_SPLIT_COLUMN].eq("holdout")

    variants = {
        "baseline_v3": [],
        "drop_day_of_year": ["day_of_year"],
        "drop_days_since_last_any_event": ["days_since_last_any_event"],
        "drop_supply_temp_mean_max": ["p_net_supply_temperature__mean", "p_net_supply_temperature__max"],
        "drop_network_temp_gap_mean": ["network_temperature_gap__mean"],
        "drop_top5_drift": [
            "day_of_year",
            "days_since_last_any_event",
            "p_net_supply_temperature__mean",
            "p_net_supply_temperature__max",
            "network_temperature_gap__mean",
        ],
        "drop_calendar_and_supply": [
            "day_of_year",
            "p_net_supply_temperature__mean",
            "p_net_supply_temperature__max",
        ],
        "drop_event_any_and_supply": [
            "days_since_last_any_event",
            "p_net_supply_temperature__mean",
            "p_net_supply_temperature__max",
        ],
        "drop_day_any_supply": [
            "day_of_year",
            "days_since_last_any_event",
            "p_net_supply_temperature__mean",
            "p_net_supply_temperature__max",
        ],
    }

    rows: list[dict] = []
    for variant_name, dropped_features in variants.items():
        feature_columns = [column for column in base_features if column not in dropped_features]
        x_train = x_all.loc[train_mask, feature_columns]
        y_train = modeling_df.loc[train_mask, "risk_target"].astype(int)

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
            verbosity=-1,
        )
        model.fit(x_train, y_train)

        for split_name, mask in [("train", train_mask), ("validation", validation_mask), ("holdout", holdout_mask)]:
            frame = modeling_df.loc[mask].copy()
            frame["risk_probability"] = model.predict_proba(x_all.loc[mask, feature_columns])[:, 1]
            metrics = score_frame(frame, FIXED_THRESHOLD)
            rows.append(
                {
                    "variant": variant_name,
                    "dropped_feature_count": len(dropped_features),
                    "dropped_features": "|".join(dropped_features),
                    "feature_count": len(feature_columns),
                    "split": split_name,
                    **metrics,
                }
            )

    result_df = pd.DataFrame(rows)
    holdout_df = result_df.loc[result_df["split"].eq("holdout")].copy()
    holdout_df = holdout_df.sort_values(
        ["f1_high_or_critical", "false_positive_rate_high_or_critical", "average_precision"],
        ascending=[False, True, False],
    ).reset_index(drop=True)

    result_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    holdout_df.to_csv(OUTPUT_HOLDOUT_PATH, index=False, encoding="utf-8-sig")

    print(OUTPUT_PATH)
    print(OUTPUT_HOLDOUT_PATH)
    print()
    print(holdout_df.to_string(index=False))


if __name__ == "__main__":
    main()

