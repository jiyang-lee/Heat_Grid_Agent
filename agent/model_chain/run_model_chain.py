"""Run raw/preprocessed fixture rows through IF + LGBM risk + LGBM leadtime."""

from __future__ import annotations

import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from agent.io import paths
from agent.model_chain.feature_adapter import (
    build_feature_matrix,
    load_feature_list,
    write_feature_report,
)
from agent.priority import contracts as priority_contracts

ANOMALY_META = paths.MODEL_HANDOFF_DIR / "anomaly" / "baseline_model_metadata.json"
ANOMALY_SCALER = paths.MODEL_HANDOFF_DIR / "anomaly" / "standard_scaler.joblib"
ANOMALY_MODEL = paths.MODEL_HANDOFF_DIR / "anomaly" / "isolation_forest.joblib"
RISK_META = paths.MODEL_HANDOFF_DIR / "risk" / "risk_model_metadata.json"
RISK_MODEL = paths.MODEL_HANDOFF_DIR / "risk" / "lightgbm_risk_model.joblib"
RISK_CALIBRATION = paths.MODEL_HANDOFF_DIR / "risk" / "risk_model_group_calibration.json"
LEADTIME_META = paths.MODEL_HANDOFF_DIR / "leadtime" / "leadtime_bucket_model_promoted_metadata.json"
LEADTIME_MODEL = paths.MODEL_HANDOFF_DIR / "leadtime" / "lightgbm_leadtime_bucket_model_promoted.joblib"


def run(
    preprocessed_path: Path | None = None,
    labels_path: Path | None = None,
    dst: Path | None = None,
    report_path: Path | None = None,
) -> pd.DataFrame:
    """Run the handoff model chain and write model-chain ML output."""

    preprocessed_path = preprocessed_path or (
        paths.REPO_ROOT
        / "agent"
        / "fixtures"
        / "preprocessing"
        / "predist_sample"
        / "output"
        / "preprocessed_windows_sample.csv"
    )
    labels_path = labels_path or (
        paths.REPO_ROOT
        / "agent"
        / "fixtures"
        / "preprocessing"
        / "predist_sample"
        / "output"
        / "supervised_window_labels.csv"
    )
    dst = dst or paths.MODEL_CHAIN_OUTPUT_CSV
    report_path = report_path or paths.MODEL_CHAIN_FEATURE_REPORT_JSON

    preprocessed = pd.read_csv(preprocessed_path)
    labels = pd.read_csv(labels_path) if labels_path.exists() else pd.DataFrame()
    context = _context_frame(preprocessed, labels)

    anomaly_features = load_feature_list(ANOMALY_META, "selected_feature_columns")
    risk_features = load_feature_list(RISK_META, "model_feature_columns")
    leadtime_features = load_feature_list(LEADTIME_META, "model_feature_columns")

    anomaly_matrix = build_feature_matrix(preprocessed, anomaly_features, extra_columns=context)
    scaler = joblib.load(ANOMALY_SCALER)
    isolation_forest = joblib.load(ANOMALY_MODEL)
    raw_anomaly = -isolation_forest.decision_function(scaler.transform(anomaly_matrix.frame.to_numpy()))
    anomaly_score = _minmax(raw_anomaly)

    risk_extra = context.copy()
    risk_extra["anomaly_score"] = anomaly_score
    risk_matrix = build_feature_matrix(preprocessed, risk_features, extra_columns=risk_extra)
    risk_model = joblib.load(RISK_MODEL)
    risk_probability = risk_model.predict_proba(risk_matrix.frame)[:, 1]
    risk_score = np.clip(risk_probability * 100.0, 0, 100)
    risk_levels = _risk_levels(risk_probability, context)

    lead_extra = risk_extra.copy()
    lead_extra["risk_probability"] = risk_probability
    lead_extra["risk_score"] = risk_score
    lead_matrix = build_feature_matrix(preprocessed, leadtime_features, extra_columns=lead_extra)
    leadtime_model = joblib.load(LEADTIME_MODEL)
    lead_probs = leadtime_model.predict_proba(lead_matrix.frame)
    lead_labels = _leadtime_labels()
    lead_index = np.argmax(lead_probs, axis=1)
    lead_bucket = [lead_labels[index] for index in lead_index]
    lead_confidence = lead_probs.max(axis=1)

    output = context.copy()
    output["anomaly_score"] = np.round(anomaly_score, 6)
    output["risk_score"] = np.round(risk_score, 4)
    output["risk_probability"] = np.round(risk_probability, 6)
    output["risk_level_calibrated"] = risk_levels
    for index, bucket in enumerate(priority_contracts.LEAD_TIME_BUCKETS):
        output[f"leadtime_prob_{bucket}"] = np.round(lead_probs[:, index], 6)
    output["predicted_lead_time_bucket"] = lead_bucket
    output["predicted_lead_time_confidence"] = np.round(lead_confidence, 6)
    output["lead_time_bucket_distance"] = _lead_bucket_distance(output)
    output["main_abnormal_sensors"] = _main_abnormal_sensors(preprocessed)

    columns = priority_contracts.MOCK_ML_OUTPUT_COLUMNS
    for column in columns:
        if column not in output.columns:
            output[column] = "" if column in {"fault_label", "lead_time_bucket"} else np.nan
    output = output[columns]
    paths.ensure_dir(dst.parent)
    output.to_csv(dst, index=False, encoding="utf-8")

    write_feature_report(
        {
            "input_rows": len(preprocessed),
            "output_rows": len(output),
            "anomaly": anomaly_matrix.report,
            "risk": risk_matrix.report,
            "leadtime": lead_matrix.report,
            "model_chain": "preprocessed_windows -> IsolationForest -> LGBM risk -> LGBM leadtime",
            "zero_fill_policy": "Missing handoff model features are deterministically filled with 0.0 and listed here.",
        },
        report_path,
    )
    print(
        "[run_model_chain] wrote "
        f"{dst} rows={len(output)} "
        f"risk_levels={output['risk_level_calibrated'].value_counts().to_dict()} "
        f"leadtime={output['predicted_lead_time_bucket'].value_counts().to_dict()}"
    )
    return output


def _context_frame(preprocessed: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    context = preprocessed[["substation_id", "window_start", "window_end"]].copy()
    if "source_file" in preprocessed.columns:
        context["source_file"] = preprocessed["source_file"].astype(str)
        context["manufacturer"] = context["source_file"].map(_normalize_manufacturer)
    else:
        context["manufacturer"] = "unknown"
    if "manufacturer" in preprocessed.columns:
        context["manufacturer"] = preprocessed["manufacturer"].map(_normalize_manufacturer)

    for column in [
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
        "configuration_type",
        "has_dhw",
        "has_buffer_tank",
    ]:
        context[column] = preprocessed[column] if column in preprocessed.columns else np.nan

    if not labels.empty:
        context["_window_start_key"] = _parse_window_ts(context["window_start"])
        context["_window_end_key"] = _parse_window_ts(context["window_end"])
        labels = labels.copy()
        labels["_window_start_key"] = _parse_window_ts(labels["window_start"])
        labels["_window_end_key"] = _parse_window_ts(labels["window_end"])
        labels["manufacturer"] = labels["manufacturer"].map(_normalize_manufacturer)
        label_columns = [
            "manufacturer",
            "substation_id",
            "_window_start_key",
            "_window_end_key",
            "label",
            "lead_time_bucket",
            "estimated_lead_time_hours",
            "fault_event_id",
        ]
        available = [column for column in label_columns if column in labels.columns]
        merge_keys = [
            "substation_id",
            "_window_start_key",
            "_window_end_key",
        ]
        if "manufacturer" in available:
            merge_keys.insert(1, "manufacturer")
        context = context.merge(
            labels[available],
            on=merge_keys,
            how="left",
        )
        context = context.drop(columns=["_window_start_key", "_window_end_key"])

    context["label"] = context.get("label", pd.Series(index=context.index, dtype="object")).fillna("")
    context["lead_time_bucket"] = context.get("lead_time_bucket", pd.Series(index=context.index, dtype="object")).fillna("")
    context["fault_label"] = ""
    if "estimated_lead_time_hours" not in context.columns:
        context["estimated_lead_time_hours"] = np.nan
    return context


def _normalize_manufacturer(value: object) -> str:
    if pd.isna(value):
        return "unknown"
    text = str(value).strip().lower()
    match = re.search(r"manufacturer[ _-]*([0-9]+)", text, re.IGNORECASE)
    if match:
        return f"manufacturer {int(match.group(1))}"
    return "unknown" if not text else text.replace("_", " ")


def _parse_window_ts(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", utc=True)


def _minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    low = values.min()
    high = values.max()
    if np.isclose(low, high):
        return np.full_like(values, 0.5, dtype=float)
    return (values - low) / (high - low)


def _risk_levels(probabilities: np.ndarray, context: pd.DataFrame) -> list[str]:
    calibration = json.loads(RISK_CALIBRATION.read_text(encoding="utf-8"))
    base = calibration["base_thresholds"]
    levels = []
    for prob, row in zip(probabilities, context.to_dict(orient="records")):
        thresholds = dict(base)
        for override in calibration.get("group_overrides", []):
            if (
                str(row.get("manufacturer")) == str(override.get("manufacturer"))
                and str(row.get("configuration_type", "")).upper() == str(override.get("configuration_type", "")).upper()
            ):
                thresholds.update(override["applied_thresholds"])
        if prob >= thresholds["critical"]:
            levels.append("critical")
        elif prob >= thresholds["high"]:
            levels.append("high")
        elif prob >= thresholds["medium"]:
            levels.append("medium")
        else:
            levels.append("low")
    return levels


def _leadtime_labels() -> list[str]:
    metadata = json.loads(LEADTIME_META.read_text(encoding="utf-8"))
    return list(metadata["leadtime_labels"])


def _lead_bucket_distance(output: pd.DataFrame) -> list[int]:
    order = {bucket: index for index, bucket in enumerate(priority_contracts.LEAD_TIME_BUCKETS)}
    distances = []
    for row in output.to_dict(orient="records"):
        actual = row.get("lead_time_bucket")
        predicted = row.get("predicted_lead_time_bucket")
        if actual in order and predicted in order:
            distances.append(abs(order[actual] - order[predicted]))
        else:
            distances.append(0)
    return distances


def _main_abnormal_sensors(preprocessed: pd.DataFrame) -> list[str]:
    sensor_cols = [
        column
        for column in preprocessed.columns
        if column.endswith("__missing_rate") or column.endswith("__delta")
    ]
    if not sensor_cols:
        return [""] * len(preprocessed)
    values = preprocessed[sensor_cols].apply(pd.to_numeric, errors="coerce").abs().fillna(0.0)
    top_columns = values.apply(lambda row: ";".join(row.nlargest(3).index.str.replace("__missing_rate", "").str.replace("__delta", "")), axis=1)
    return top_columns.tolist()


if __name__ == "__main__":
    run()
