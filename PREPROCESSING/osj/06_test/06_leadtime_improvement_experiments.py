from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, f1_score


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
ML_FEATURES_DIR = DATA_DIR / "ml_features"
ML_RISK_DIR = DATA_DIR / "ml_risk"
ML_LEADTIME_DIR = DATA_DIR / "ml_leadtime"
LEADTIME_MODEL_DIR = ML_LEADTIME_DIR / "models"

TRAINABLE_WINDOWS_PATH = ML_FEATURES_DIR / "trainable_windows.csv"
RISK_SCORES_PATH = ML_RISK_DIR / "lgbm_risk_scores.csv"
LEADTIME_METADATA_PATH = LEADTIME_MODEL_DIR / "leadtime_bucket_model_metadata.json"

TIMEFLOW_OUTPUT_PATH = ML_LEADTIME_DIR / "leadtime_timeflow_experiment.csv"
TIMEFLOW_HOLDOUT_PATH = ML_LEADTIME_DIR / "leadtime_timeflow_experiment_holdout.csv"
BUCKET_OUTPUT_PATH = ML_LEADTIME_DIR / "leadtime_bucket_redesign_experiment.csv"
BUCKET_HOLDOUT_PATH = ML_LEADTIME_DIR / "leadtime_bucket_redesign_experiment_holdout.csv"
LABEL_OUTPUT_PATH = ML_LEADTIME_DIR / "leadtime_label_refinement_experiment.csv"
LABEL_HOLDOUT_PATH = ML_LEADTIME_DIR / "leadtime_label_refinement_experiment_holdout.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
SPLIT_VALUES = ["train", "validation", "holdout"]
RANDOM_STATE = 42

BUCKET_MAPPINGS = {
    "current_3bucket": {
        "labels": ["0-24h", "1-3d", "3-7d"],
        "map": {"0-6h": "0-24h", "6-24h": "0-24h", "1-3d": "1-3d", "3-7d": "3-7d"},
    },
    "original_4bucket": {
        "labels": ["0-6h", "6-24h", "1-3d", "3-7d"],
        "map": {"0-6h": "0-6h", "6-24h": "6-24h", "1-3d": "1-3d", "3-7d": "3-7d"},
    },
    "binary_24h_vs_1_7d": {
        "labels": ["0-24h", "1-7d"],
        "map": {"0-6h": "0-24h", "6-24h": "0-24h", "1-3d": "1-7d", "3-7d": "1-7d"},
    },
}

TIMEFLOW_SOURCE_COLUMNS = [
    "anomaly_score",
    "risk_probability",
    "network_temperature_gap__mean",
    "p_net_return_temperature__mean",
    "p_net_supply_temperature__mean",
    "days_since_last_task_event",
    "days_since_last_any_event",
]


def load_base_frame() -> tuple[pd.DataFrame, list[str]]:
    trainable_windows = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(LEADTIME_METADATA_PATH.read_text(encoding="utf-8"))

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

    for column in ["maintenance_related"]:
        if column in modeling_df.columns:
            modeling_df[column] = modeling_df[column].fillna(False).astype("int8")
    for column in ["disturbance_count"]:
        if column in modeling_df.columns:
            modeling_df[column] = modeling_df[column].fillna(0)

    pre_fault_df = modeling_df.loc[modeling_df["label"].eq("pre_fault")].copy()
    return pre_fault_df, model_feature_columns


def make_numeric_frame(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    x_all = frame[feature_columns].copy()
    for column in x_all.columns:
        if x_all[column].dtype == "bool":
            x_all[column] = x_all[column].astype("int8")
        elif x_all[column].dtype == "object":
            x_all[column] = pd.to_numeric(x_all[column], errors="coerce")
    return x_all


def add_timeflow_features(frame: pd.DataFrame, x_all: pd.DataFrame, variant: str) -> pd.DataFrame:
    if variant == "baseline":
        return x_all

    result = x_all.copy()
    working = frame.copy()
    working["window_end"] = pd.to_datetime(working["window_end"])
    working = working.sort_values(["fault_event_id", "window_end", "window_start"]).copy()

    extra = pd.DataFrame(index=working.index)
    available = [column for column in TIMEFLOW_SOURCE_COLUMNS if column in working.columns]
    grouped = working.groupby("fault_event_id", dropna=False)

    for column in available:
        numeric = pd.to_numeric(working[column], errors="coerce")
        lag1 = grouped[column].shift(1)
        delta1 = numeric - pd.to_numeric(lag1, errors="coerce")
        extra[f"{column}__lag1"] = pd.to_numeric(lag1, errors="coerce").fillna(numeric).astype("float64")
        extra[f"{column}__delta1"] = delta1.fillna(0.0).astype("float64")

        if variant == "timeflow_lag_delta_roll3":
            lag2 = grouped[column].shift(2)
            roll3 = grouped[column].rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
            extra[f"{column}__lag2"] = pd.to_numeric(lag2, errors="coerce").fillna(numeric).astype("float64")
            extra[f"{column}__roll3_mean"] = pd.to_numeric(roll3, errors="coerce").fillna(numeric).astype("float64")

    extra = extra.reindex(frame.index)
    result = pd.concat([result, extra], axis=1)
    return result


def prepare_target(frame: pd.DataFrame, mapping_name: str) -> tuple[pd.DataFrame, list[str], dict[str, int]]:
    mapping = BUCKET_MAPPINGS[mapping_name]
    labels = mapping["labels"]
    target_frame = frame.copy()
    target_frame["lead_time_bucket_variant"] = target_frame["lead_time_bucket"].map(mapping["map"])
    target_frame = target_frame.loc[target_frame["lead_time_bucket_variant"].isin(labels)].copy()
    label_to_index = {label: index for index, label in enumerate(labels)}
    target_frame["lead_time_target"] = target_frame["lead_time_bucket_variant"].map(label_to_index).astype(int)
    return target_frame, labels, label_to_index


def top2_accuracy(probabilities, y_true: pd.Series) -> float | None:
    if probabilities.shape[1] < 3:
        return None
    top2 = probabilities.argsort(axis=1)[:, -2:]
    truth = y_true.to_numpy().reshape(-1, 1)
    return float((top2 == truth).any(axis=1).mean())


def bucket_distance(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float((y_true - y_pred).abs().mean())


def train_and_score(
    frame: pd.DataFrame,
    x_all: pd.DataFrame,
    labels: list[str],
    experiment_name: str,
    extra_info: dict[str, str],
) -> list[dict]:
    train_mask = frame[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = frame[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = frame[PRIMARY_SPLIT_COLUMN].eq("holdout")
    y_all = frame["lead_time_target"].astype(int)

    model = LGBMClassifier(
        objective="multiclass",
        num_class=len(labels),
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
    model.fit(
        x_all.loc[train_mask],
        y_all.loc[train_mask],
        eval_set=[(x_all.loc[validation_mask], y_all.loc[validation_mask])],
        eval_metric="multi_logloss",
    )

    probabilities = model.predict_proba(x_all)
    predicted = probabilities.argmax(axis=1)

    rows: list[dict] = []
    for split_name, split_mask in {
        "train": train_mask,
        "validation": validation_mask,
        "holdout": holdout_mask,
    }.items():
        y_true = y_all.loc[split_mask]
        y_pred = pd.Series(predicted[split_mask.to_numpy()], index=y_true.index)
        probs = probabilities[split_mask.to_numpy()]
        rows.append(
            {
                "experiment_name": experiment_name,
                "feature_count": int(x_all.shape[1]),
                "label_count": int(len(labels)),
                "split": split_name,
                "row_count": int(split_mask.sum()),
                "accuracy": float(accuracy_score(y_true, y_pred)),
                "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
                "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
                "top2_accuracy": top2_accuracy(probs, y_true),
                "bucket_distance_mae": bucket_distance(y_true, y_pred),
                **extra_info,
            }
        )
    return rows


def run_timeflow_experiment(pre_fault_df: pd.DataFrame, base_feature_columns: list[str]) -> pd.DataFrame:
    target_df, labels, _ = prepare_target(pre_fault_df, "current_3bucket")
    rows: list[dict] = []
    for variant in ["baseline", "timeflow_lag_delta", "timeflow_lag_delta_roll3"]:
        x_all = make_numeric_frame(target_df, base_feature_columns)
        x_all = add_timeflow_features(target_df, x_all, variant).fillna(0.0)
        rows.extend(
            train_and_score(
                target_df,
                x_all,
                labels,
                experiment_name=variant,
                extra_info={"bucket_mapping": "current_3bucket", "filter_name": "no_filter"},
            )
        )
    return pd.DataFrame(rows)


def run_bucket_experiment(pre_fault_df: pd.DataFrame, base_feature_columns: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for mapping_name in BUCKET_MAPPINGS:
        target_df, labels, _ = prepare_target(pre_fault_df, mapping_name)
        x_all = make_numeric_frame(target_df, base_feature_columns)
        x_all = add_timeflow_features(target_df, x_all, "timeflow_lag_delta_roll3").fillna(0.0)
        rows.extend(
            train_and_score(
                target_df,
                x_all,
                labels,
                experiment_name=f"bucket_redesign::{mapping_name}",
                extra_info={"bucket_mapping": mapping_name, "filter_name": "no_filter"},
            )
        )
    return pd.DataFrame(rows)


def apply_label_filter(frame: pd.DataFrame, filter_name: str) -> pd.DataFrame:
    filtered = frame.copy()
    task_days = pd.to_numeric(filtered.get("days_since_last_task_event"), errors="coerce").fillna(9999.0)
    any_days = pd.to_numeric(filtered.get("days_since_last_any_event"), errors="coerce").fillna(9999.0)
    maintenance = filtered.get("maintenance_related", pd.Series(0, index=filtered.index)).fillna(0).astype(int)

    if filter_name == "no_filter":
        return filtered
    if filter_name == "exclude_recent_task_3d":
        return filtered.loc[task_days > 3].copy()
    if filter_name == "exclude_recent_task_7d":
        return filtered.loc[task_days > 7].copy()
    if filter_name == "exclude_recent_any_event_3d":
        return filtered.loc[any_days > 3].copy()
    if filter_name == "exclude_recent_any_event_7d":
        return filtered.loc[any_days > 7].copy()
    if filter_name == "exclude_maintenance_related":
        return filtered.loc[maintenance.eq(0)].copy()
    raise ValueError(f"Unknown filter: {filter_name}")


def run_label_refinement_experiment(pre_fault_df: pd.DataFrame, base_feature_columns: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for filter_name in [
        "no_filter",
        "exclude_recent_task_3d",
        "exclude_recent_task_7d",
        "exclude_recent_any_event_3d",
        "exclude_recent_any_event_7d",
        "exclude_maintenance_related",
    ]:
        filtered = apply_label_filter(pre_fault_df, filter_name)
        target_df, labels, _ = prepare_target(filtered, "current_3bucket")
        x_all = make_numeric_frame(target_df, base_feature_columns)
        x_all = add_timeflow_features(target_df, x_all, "timeflow_lag_delta_roll3").fillna(0.0)
        rows.extend(
            train_and_score(
                target_df,
                x_all,
                labels,
                experiment_name=f"label_refine::{filter_name}",
                extra_info={"bucket_mapping": "current_3bucket", "filter_name": filter_name},
            )
        )
    return pd.DataFrame(rows)


def write_outputs(df: pd.DataFrame, full_path: Path, holdout_path: Path) -> None:
    holdout_df = df.loc[df["split"].eq("holdout")].copy()
    holdout_df = holdout_df.sort_values(
        ["macro_f1", "accuracy", "bucket_distance_mae"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    df.to_csv(full_path, index=False, encoding="utf-8-sig")
    holdout_df.to_csv(holdout_path, index=False, encoding="utf-8-sig")


def main() -> None:
    pre_fault_df, base_feature_columns = load_base_frame()

    timeflow_df = run_timeflow_experiment(pre_fault_df, base_feature_columns)
    bucket_df = run_bucket_experiment(pre_fault_df, base_feature_columns)
    label_df = run_label_refinement_experiment(pre_fault_df, base_feature_columns)

    write_outputs(timeflow_df, TIMEFLOW_OUTPUT_PATH, TIMEFLOW_HOLDOUT_PATH)
    write_outputs(bucket_df, BUCKET_OUTPUT_PATH, BUCKET_HOLDOUT_PATH)
    write_outputs(label_df, LABEL_OUTPUT_PATH, LABEL_HOLDOUT_PATH)

    print(TIMEFLOW_HOLDOUT_PATH)
    print(BUCKET_HOLDOUT_PATH)
    print(LABEL_HOLDOUT_PATH)
    print()
    print("[timeflow holdout]")
    print(pd.read_csv(TIMEFLOW_HOLDOUT_PATH).to_string(index=False))
    print()
    print("[bucket redesign holdout]")
    print(pd.read_csv(BUCKET_HOLDOUT_PATH).to_string(index=False))
    print()
    print("[label refinement holdout]")
    print(pd.read_csv(LABEL_HOLDOUT_PATH).to_string(index=False))


if __name__ == "__main__":
    main()
