from __future__ import annotations

import json
import shutil
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from . import config
from .common import write_json


MODEL_FILES = {
    "fault_gate": "m1_fault_gate_rf_depth3.joblib",
    "task_gate": "m1_task_gate_rf_depth3.joblib",
    "activity_gate": "m1_activity_gate_rf_depth3.joblib",
    "fault_pre_event_gate": "m1_fault_pre_event_logistic.joblib",
}


def _third_model_dir() -> Path:
    if not config.THIRD_PROJECT_ROOT.exists():
        raise FileNotFoundError(f"Missing 3rd project root: {config.THIRD_PROJECT_ROOT}")
    return next(p for p in config.THIRD_PROJECT_ROOT.iterdir() if p.is_dir() and p.name.startswith("08_"))


def _load_runtime_metadata() -> dict:
    local_path = config.M1_SPECIALIST_MODEL_DIR / "m1_full_gate_runtime_policy_metadata.json"
    if local_path.exists():
        path = local_path
    else:
        path = _third_model_dir() / "m1_full_gate_runtime_policy_metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_m1_specialist_models(force: bool = False) -> dict[str, str]:
    model_dir = _third_model_dir() if config.THIRD_PROJECT_ROOT.exists() else None
    copied: dict[str, str] = {}
    config.M1_SPECIALIST_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for key, name in MODEL_FILES.items():
        target = config.M1_SPECIALIST_MODEL_DIR / name
        source = model_dir / name if model_dir is not None else None
        if source is not None and source.exists() and (force or not target.exists()):
            shutil.copy2(source, target)
        elif not target.exists():
            if source is None or not source.exists():
                raise FileNotFoundError(f"Missing M1 specialist model: {target}")
        copied[key] = str(target)
    meta_target = config.M1_SPECIALIST_MODEL_DIR / "m1_full_gate_runtime_policy_metadata.json"
    meta_source = model_dir / "m1_full_gate_runtime_policy_metadata.json" if model_dir is not None else None
    if meta_source is not None and meta_source.exists() and (force or not meta_target.exists()):
        shutil.copy2(meta_source, meta_target)
    elif not meta_target.exists():
        if model_dir is None or not meta_source.exists():
            raise FileNotFoundError(f"Missing M1 specialist runtime metadata: {meta_target}")
    copied["runtime_metadata"] = str(meta_target)
    return copied


def materialize_m1_specialist_models(force: bool = False) -> dict[str, str]:
    """Refresh the packaged M1 specialist gate artifacts from the source project if needed."""
    config.ensure_dirs()
    copied = _copy_m1_specialist_models(force=force)
    return {key: config.path_label(value) for key, value in copied.items()}


def _raw_path(manufacturer: str, substation_id: int) -> Path:
    return config.SOURCE_RAW_ROOT / manufacturer / "operational_data" / f"substation_{int(substation_id)}.csv"


@lru_cache(maxsize=128)
def _load_operational(manufacturer: str, substation_id: int) -> pd.DataFrame:
    path = _raw_path(manufacturer, int(substation_id))
    if not path.exists():
        return pd.DataFrame(columns=["timestamp"])
    df = pd.read_csv(path, sep=";", low_memory=False)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for column in df.columns:
        if column != "timestamp":
            df[column] = pd.to_numeric(df[column], errors="coerce")
    for column in [
        "outdoor_temperature",
        "s_hc1_supply_temperature",
        "s_hc1_supply_temperature_setpoint",
        "p_hc1_return_temperature",
        "p_net_return_temperature",
        "p_net_meter_flow",
    ]:
        if column not in df.columns:
            df[column] = np.nan
    df["s_hc1_supply_temperature_error"] = df["s_hc1_supply_temperature"] - df["s_hc1_supply_temperature_setpoint"]
    df["p_return_gap"] = df["p_hc1_return_temperature"] - df["p_net_return_temperature"]
    return df


def _period_stat(window: pd.DataFrame, signal: str, start: pd.Timestamp, end: pd.Timestamp, stat: str) -> float:
    if signal not in window.columns:
        return np.nan
    subset = pd.to_numeric(
        window.loc[window["timestamp"].ge(start) & window["timestamp"].lt(end), signal],
        errors="coerce",
    ).dropna()
    if subset.empty:
        return np.nan
    if stat == "mean":
        return float(subset.mean())
    if stat == "std":
        return float(subset.std(ddof=0))
    raise ValueError(stat)


def _last_minus_first(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < 2:
        return np.nan
    return float(clean.iloc[-1] - clean.iloc[0])


def _compute_feature(window: pd.DataFrame, signal: str, feature_stat: str, window_start: pd.Timestamp, window_end: pd.Timestamp) -> float:
    if signal not in window.columns:
        return np.nan
    series = pd.to_numeric(window[signal], errors="coerce")
    if feature_stat == "last_minus_first":
        return _last_minus_first(series)
    if feature_stat == "last_1d_mean_minus_prev_6d_mean":
        return _period_stat(window, signal, window_end - pd.Timedelta(days=1), window_end, "mean") - _period_stat(
            window, signal, window_start, window_end - pd.Timedelta(days=1), "mean"
        )
    if feature_stat == "last_12h_mean_minus_prev_12h_mean":
        return _period_stat(window, signal, window_end - pd.Timedelta(hours=12), window_end, "mean") - _period_stat(
            window, signal, window_end - pd.Timedelta(hours=24), window_end - pd.Timedelta(hours=12), "mean"
        )
    if feature_stat == "last_6h_mean_minus_prev_6h_mean":
        return _period_stat(window, signal, window_end - pd.Timedelta(hours=6), window_end, "mean") - _period_stat(
            window, signal, window_end - pd.Timedelta(hours=12), window_end - pd.Timedelta(hours=6), "mean"
        )
    if feature_stat == "last_1d_std_minus_prev_6d_std":
        return _period_stat(window, signal, window_end - pd.Timedelta(days=1), window_end, "std") - _period_stat(
            window, signal, window_start, window_end - pd.Timedelta(days=1), "std"
        )
    raise ValueError(feature_stat)


def _coverage(window_start: pd.Timestamp, window_end: pd.Timestamp, sample_count: int) -> tuple[int, float]:
    expected = int(round((window_end - window_start).total_seconds() / 600.0))
    return expected, sample_count / expected if expected else 0.0


def build_compact13_features() -> tuple[pd.DataFrame, list[str]]:
    metadata = _load_runtime_metadata()
    features = list(metadata["models"]["fault_gate"]["features"])
    if not config.SOURCE_RAW_ROOT.exists() and config.M1_SPECIALIST_COMPACT13_FEATURES_PATH.exists():
        compact = pd.read_csv(config.M1_SPECIALIST_COMPACT13_FEATURES_PATH)
        return compact, features
    windows = pd.read_csv(config.TRAINABLE_WINDOWS_PATH)
    rows: list[dict[str, object]] = []
    for rec in windows.itertuples(index=False):
        manufacturer = str(getattr(rec, "manufacturer"))
        substation_id = int(getattr(rec, "substation_id"))
        window_end = pd.to_datetime(getattr(rec, "window_end"), errors="coerce")
        window_start = window_end - pd.Timedelta(days=7) if pd.notna(window_end) else pd.NaT
        row = {column: getattr(rec, column) for column in config.KEY_COLUMNS}
        row["m1_specialist_model_scope"] = "m1_runtime_model" if manufacturer == "manufacturer 1" else "out_of_scope_m1_model"
        row["m1_specialist_compact_window_start"] = "" if pd.isna(window_start) else str(window_start)
        row["m1_specialist_compact_window_end"] = "" if pd.isna(window_end) else str(window_end)
        if manufacturer != "manufacturer 1" or pd.isna(window_end):
            row["m1_specialist_sample_count"] = 0
            row["m1_specialist_expected_count"] = 0
            row["m1_specialist_coverage_rate"] = 0.0
            for feature in features:
                row[feature] = np.nan
            rows.append(row)
            continue
        raw = _load_operational(manufacturer, substation_id)
        if raw.empty:
            sample_count = 0
            expected = 0
            coverage = 0.0
            window = raw
        else:
            window = raw.loc[raw["timestamp"].ge(window_start) & raw["timestamp"].lt(window_end)].copy()
            sample_count = int(len(window))
            expected, coverage = _coverage(window_start, window_end, sample_count)
        row["m1_specialist_sample_count"] = sample_count
        row["m1_specialist_expected_count"] = expected
        row["m1_specialist_coverage_rate"] = coverage
        for feature in features:
            signal, feature_stat = feature.split("__", 1)
            row[feature] = _compute_feature(window, signal, feature_stat, window_start, window_end) if len(window) else np.nan
        rows.append(row)
    compact = pd.DataFrame(rows)
    compact.to_csv(config.M1_SPECIALIST_COMPACT13_FEATURES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return compact, features


def _class_one_probability(model, frame: pd.DataFrame) -> np.ndarray:
    probabilities = model.predict_proba(frame)
    classes = list(getattr(model, "classes_", [0, 1]))
    if 1 in classes:
        return probabilities[:, classes.index(1)]
    return probabilities[:, -1]


def _compat_model(model):
    """Patch small sklearn persistence differences for imported 3rd project joblibs."""
    estimators = []
    if hasattr(model, "steps"):
        estimators.extend(step for _, step in model.steps)
    estimators.append(model)
    for estimator in estimators:
        if estimator.__class__.__name__ == "LogisticRegression" and not hasattr(estimator, "multi_class"):
            estimator.multi_class = "auto"
    return model


def _fault_group_and_weight(label: object) -> tuple[str, float]:
    text = "" if pd.isna(label) else str(label).lower()
    if any(key in text for key in ["control", "controller", "parameter", "monitor"]):
        return "control_controller", 1.0
    if "pump" in text:
        return "pump_failure", 0.636043
    if any(key in text for key in ["valve", "actuator", "shut-off", "shut off"]):
        return "valve_actuator", 0.580894
    if "pressure" in text:
        return "pressure_regulator", 0.521702
    if any(key in text for key in ["leak", "water loss", "relief"]):
        return "leakage_water_loss", 0.444043
    return "unknown_review", 0.1


def _leadtime_urgency(row: pd.Series) -> float:
    for column in ["leadtime_urgency_score", "leadtime_near_term_probability"]:
        value = pd.to_numeric(row.get(column), errors="coerce")
        if pd.notna(value):
            return float(np.clip(value, 0.0, 1.0))
    bucket = row.get("predicted_lead_time_bucket", row.get("lead_time_bucket"))
    return {"0-24h": 1.0, "1-3d": 0.65, "3-7d": 0.35}.get(bucket, 0.2)


def score_m1_specialist_gates() -> pd.DataFrame:
    """Run original 3rd_project gate models as a parallel M1 specialist branch.

    This branch is intentionally scoped as M1 runtime context. It does not
    replace current best priority and is not used as a hard router.
    """
    config.ensure_dirs()
    copied = materialize_m1_specialist_models()
    metadata = _load_runtime_metadata()
    compact, features = build_compact13_features()
    context = pd.read_csv(config.PRIORITY_SCORES_PATH) if config.PRIORITY_SCORES_PATH.exists() else pd.read_csv(config.TRAINABLE_WINDOWS_PATH)
    context_columns = [
        *config.KEY_COLUMNS,
        "label",
        "fault_label",
        "fault_event_id",
        "risk_score",
        "risk_probability",
        "leadtime_urgency_score",
        "leadtime_near_term_probability",
        "predicted_lead_time_bucket",
        "priority_score",
        "priority_level",
    ]
    context_columns = [c for c in context_columns if c in context.columns]
    scored = compact.merge(context[context_columns].drop_duplicates(config.KEY_COLUMNS), on=config.KEY_COLUMNS, how="left", validate="one_to_one")

    m1_mask = scored["m1_specialist_model_scope"].eq("m1_runtime_model")
    x = scored[features].copy()
    models = {key: _compat_model(joblib.load(config.M1_SPECIALIST_MODEL_DIR / name)) for key, name in MODEL_FILES.items()}
    for key in ["fault_gate", "task_gate", "activity_gate", "fault_pre_event_gate"]:
        prob_column = {
            "fault_gate": "m1_specialist_fault_probability",
            "task_gate": "m1_specialist_task_probability",
            "activity_gate": "m1_specialist_activity_probability",
            "fault_pre_event_gate": "m1_specialist_pre_event_probability",
        }[key]
        scored[prob_column] = np.nan
        if int(m1_mask.sum()):
            scored.loc[m1_mask, prob_column] = _class_one_probability(models[key], x.loc[m1_mask, features])

    scored["m1_specialist_fault_prediction"] = scored["m1_specialist_fault_probability"].ge(0.5).fillna(False).astype("int8")
    scored["m1_specialist_task_prediction"] = scored["m1_specialist_task_probability"].ge(0.5).fillna(False).astype("int8")
    scored["m1_specialist_activity_prediction"] = scored["m1_specialist_activity_probability"].ge(0.5).fillna(False).astype("int8")
    scored["m1_specialist_pre_event_prediction"] = scored["m1_specialist_pre_event_probability"].ge(0.6).fillna(False).astype("int8")

    states = []
    secondary = []
    review_reasons = []
    for row in scored.itertuples(index=False):
        active = []
        if getattr(row, "m1_specialist_fault_prediction") == 1:
            active.append("fault")
        if getattr(row, "m1_specialist_task_prediction") == 1:
            active.append("task")
        if getattr(row, "m1_specialist_activity_prediction") == 1:
            active.append("activity")
        if getattr(row, "m1_specialist_model_scope") != "m1_runtime_model":
            states.append("out_of_scope")
            secondary.append("")
            review_reasons.append("m1_model_out_of_scope")
            continue
        state = "fault" if "fault" in active else "task" if "task" in active else "activity" if "activity" in active else "normal"
        states.append(state)
        secondary.append("|".join([tag for tag in active if tag != state]))
        reasons = []
        if len(active) > 1:
            reasons.append("multiple_m1_specialist_gates_positive")
        probs = [
            getattr(row, "m1_specialist_fault_probability"),
            getattr(row, "m1_specialist_task_probability"),
            getattr(row, "m1_specialist_activity_probability"),
        ]
        if any(pd.notna(p) and 0.45 <= float(p) <= 0.55 for p in probs):
            reasons.append("m1_specialist_gate_near_threshold")
        if "activity" in active:
            reasons.append("m1_specialist_activity_context")
        review_reasons.append("|".join(reasons))
    scored["m1_specialist_primary_state"] = states
    scored["m1_specialist_secondary_tags"] = secondary
    scored["m1_specialist_gate_review_reasons"] = review_reasons
    scored["m1_specialist_gate_review_required"] = scored["m1_specialist_gate_review_reasons"].astype(str).ne("")

    groups = scored.get("fault_label", pd.Series(index=scored.index, dtype=object)).map(_fault_group_and_weight)
    scored["m1_specialist_fault_group"] = [g for g, _ in groups]
    scored["m1_specialist_group_weight"] = [w for _, w in groups]
    scored["m1_specialist_leadtime_urgency"] = scored.apply(_leadtime_urgency, axis=1)
    scored["m1_specialist_priority_score"] = 100.0 * (
        0.55 * pd.to_numeric(scored["m1_specialist_pre_event_probability"], errors="coerce").fillna(0.0)
        + 0.30 * scored["m1_specialist_leadtime_urgency"]
        + 0.15 * scored["m1_specialist_group_weight"]
    )

    keep_context = [
        *config.KEY_COLUMNS,
        "label",
        "fault_label",
        "fault_event_id",
        "m1_specialist_model_scope",
        "m1_specialist_compact_window_start",
        "m1_specialist_compact_window_end",
        "m1_specialist_sample_count",
        "m1_specialist_expected_count",
        "m1_specialist_coverage_rate",
        "m1_specialist_fault_probability",
        "m1_specialist_task_probability",
        "m1_specialist_activity_probability",
        "m1_specialist_pre_event_probability",
        "m1_specialist_fault_prediction",
        "m1_specialist_task_prediction",
        "m1_specialist_activity_prediction",
        "m1_specialist_pre_event_prediction",
        "m1_specialist_primary_state",
        "m1_specialist_secondary_tags",
        "m1_specialist_fault_group",
        "m1_specialist_group_weight",
        "m1_specialist_leadtime_urgency",
        "m1_specialist_priority_score",
        "m1_specialist_gate_review_required",
        "m1_specialist_gate_review_reasons",
    ]
    keep_context = [c for c in keep_context if c in scored.columns]
    scored[keep_context].to_csv(config.M1_SPECIALIST_GATE_SCORES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    scored[keep_context].to_csv(config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    write_json(
        config.M1_SPECIALIST_GATE_METADATA_PATH,
        {
            "source": "3rd_project_for_ML-main",
            "model_scope": "manufacturer 1 runtime context branch",
            "copied_models": copied,
            "feature_count": len(features),
            "features": features,
            "thresholds": {
                "fault_gate": 0.5,
                "task_gate": 0.5,
                "activity_gate": 0.5,
                "fault_pre_event_gate": 0.6,
            },
            "role": "parallel M1 specialist gate/context branch; used by M1 hybrid priority, not a standalone risk/leadtime replacement",
            "parallel_agent_card_path": config.path_label(config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH),
            "python_executable": config.path_label(config.M1_SPECIALIST_PYTHON_PATH, "THIRD_MODEL_M1_SPECIALIST_PYTHON"),
            "sklearn_version": sklearn.__version__,
            "runtime_policy_source": metadata.get("package_id"),
        },
    )
    return scored[keep_context].copy()


if __name__ == "__main__":
    score_m1_specialist_gates()
