from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import zipfile
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import config
from .common import write_json


RANDOM_STATE = 42
SOURCE_PREFIX = "manufacturer 1"

FAULT_GATE_THRESHOLD = 0.50
TASK_GATE_THRESHOLD = 0.50
ACTIVITY_GATE_THRESHOLD = 0.50
PRE_EVENT_THRESHOLD = 0.60

BASE_SIGNALS = [
    "outdoor_temperature",
    "s_hc1_supply_temperature",
    "s_hc1_supply_temperature_setpoint",
    "p_hc1_return_temperature",
    "p_net_meter_energy",
    "p_net_meter_volume",
    "p_net_meter_heat_power",
    "p_net_meter_flow",
    "p_net_supply_temperature",
    "p_net_return_temperature",
]

MODEL_PATHS = {
    "fault_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_fault_gate_rf_depth3.joblib",
    "task_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_task_gate_rf_depth3.joblib",
    "activity_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_activity_gate_rf_depth3.joblib",
    "fault_pre_event_gate": config.M1_SPECIALIST_MODEL_DIR / "m1_fault_pre_event_logistic.joblib",
}

SOURCE_INPUTS = {
    "fault_gate_predictions": (
        "m1_fault_gate_lock_predictions.csv",
        config.M1_SOURCE_FAULT_GATE_PREDICTIONS_PATH,
    ),
    "task_activity_predictions": (
        "m1_task_activity_window_candidate_predictions.csv",
        config.M1_SOURCE_TASK_ACTIVITY_PREDICTIONS_PATH,
    ),
    "pre_event_feature_pool": (
        "m1_expansion_feature_pool.csv",
        config.M1_SOURCE_PRE_EVENT_FEATURE_POOL_PATH,
    ),
    "compact_feature_set_summary": (
        "m1_compact_feature_set_summary.csv",
        config.M1_SOURCE_COMPACT_FEATURE_SET_SUMMARY_PATH,
    ),
}


def _third_project_output_dir() -> Path | None:
    root = config.THIRD_PROJECT_ROOT
    if not root.exists():
        return None
    matches = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("07_")]
    return matches[0] if matches else None


def _third_project_data_dir() -> Path | None:
    root = config.THIRD_PROJECT_ROOT
    if not root.exists():
        return None
    matches = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("05_")]
    return matches[0] if matches else None


def _source_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=config.PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _materialize_source_input_csvs() -> dict[str, object]:
    config.ensure_dirs()
    source_out = _third_project_output_dir()
    copied: dict[str, object] = {}
    missing: list[str] = []
    for key, (filename, target) in SOURCE_INPUTS.items():
        if target.exists():
            copied[key] = {
                "status": "already_present",
                "target": config.path_label(target),
                "rows": int(len(pd.read_csv(target, usecols=[0]))),
            }
            continue
        source = source_out / filename if source_out is not None else None
        if source is None or not source.exists():
            missing.append(filename)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[key] = {
            "status": "copied",
            "source": config.path_label(source, "THIRD_MODEL_3RD_PROJECT_ROOT"),
            "target": config.path_label(target),
            "rows": int(len(pd.read_csv(target, usecols=[0]))),
        }
    if missing:
        raise FileNotFoundError(
            "Missing M1 specialist source training inputs: "
            + ", ".join(missing)
            + ". Run once with THIRD_MODEL_3RD_PROJECT_ROOT available, or place the files under "
            + config.path_label(config.M1_SPECIALIST_TRAINING_INPUT_DIR)
            + "."
        )
    return copied


def _predist_zip_path() -> Path | None:
    candidates: list[Path] = []
    env_path = os.environ.get("THIRD_MODEL_PREDIST_ZIP_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend(
        [
            config.DATA_DIR / "_downloads" / "predist_dataset.zip",
            config.M1_SPECIALIST_ARTIFACT_DIR / "predist_dataset.zip",
        ]
    )
    data_dir = _third_project_data_dir()
    if data_dir is not None:
        candidates.append(data_dir / "PreDist" / "predist_dataset.zip")
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _read_zip_csv(zip_path: Path, relative_path: str, **kwargs) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{SOURCE_PREFIX}/{relative_path}") as handle:
            return pd.read_csv(handle, sep=";", **kwargs)


@lru_cache(maxsize=80)
def _load_operational_from_zip(zip_path_text: str, substation_id: int) -> pd.DataFrame:
    zip_path = Path(zip_path_text)
    df = _read_zip_csv(zip_path, f"operational_data/substation_{int(substation_id)}.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in df.columns:
        if col != "timestamp":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in BASE_SIGNALS:
        if col not in df.columns:
            df[col] = np.nan
    df["s_hc1_supply_temperature_error"] = (
        df["s_hc1_supply_temperature"] - df["s_hc1_supply_temperature_setpoint"]
    )
    df["p_net_delta_temperature"] = df["p_net_supply_temperature"] - df["p_net_return_temperature"]
    flow = df["p_net_meter_flow"].replace(0, np.nan)
    df["p_net_power_flow_ratio"] = df["p_net_meter_heat_power"] / flow
    df["p_return_gap"] = df["p_hc1_return_temperature"] - df["p_net_return_temperature"]
    return df


def _last_minus_first(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < 2:
        return np.nan
    return float(clean.iloc[-1] - clean.iloc[0])


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


def _compute_feature(
    window: pd.DataFrame,
    signal: str,
    feature_stat: str,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> float:
    if signal not in window.columns:
        return np.nan
    series = pd.to_numeric(window[signal], errors="coerce")
    if feature_stat == "mean":
        return float(series.mean()) if len(series) else np.nan
    if feature_stat == "std":
        return float(series.std(ddof=0)) if len(series) else np.nan
    if feature_stat == "min":
        return float(series.min()) if len(series) else np.nan
    if feature_stat == "max":
        return float(series.max()) if len(series) else np.nan
    if feature_stat == "median":
        return float(series.median()) if len(series) else np.nan
    if feature_stat == "missing_rate":
        return float(series.isna().mean()) if len(series) else 1.0
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


def _expected_count(window_start: pd.Timestamp, window_end: pd.Timestamp, seconds: int = 600) -> int:
    return int(round((window_end - window_start).total_seconds() / seconds))


def _compact13_features() -> list[str]:
    _materialize_source_input_csvs()
    summary = pd.read_csv(config.M1_SOURCE_COMPACT_FEATURE_SET_SUMMARY_PATH)
    for feature_set in ["compact13_overlap", "compact13"]:
        row = summary.loc[summary["feature_set"].eq(feature_set)]
        if len(row) == 1:
            return [f for f in str(row.iloc[0]["features"]).split("|") if f]
    raise ValueError("No compact13 feature set found in M1 source feature summary.")


def _filter_gate_prediction(gate: str) -> tuple[pd.DataFrame, str]:
    if gate == "fault_gate":
        pred = pd.read_csv(config.M1_SOURCE_FAULT_GATE_PREDICTIONS_PATH)
        data = pred.loc[
            pred["dataset"].eq("fault_no_overlap")
            & pred["feature_set"].eq("compact13")
            & pred["model"].eq("random_forest_balanced_depth3")
        ].copy()
        return data, "fault_no_overlap"
    if gate == "task_gate":
        pred = pd.read_csv(config.M1_SOURCE_TASK_ACTIVITY_PREDICTIONS_PATH)
        data = pred.loc[
            pred["dataset"].eq("task_post_1d")
            & pred["feature_set"].eq("compact13")
            & pred["model"].eq("random_forest_balanced_depth3")
        ].copy()
        return data, "task_post_1d"
    if gate == "activity_gate":
        pred = pd.read_csv(config.M1_SOURCE_TASK_ACTIVITY_PREDICTIONS_PATH)
        data = pred.loc[
            pred["dataset"].eq("activity_pre_1d")
            & pred["feature_set"].eq("compact13")
            & pred["model"].eq("random_forest_balanced_depth3")
        ].copy()
        return data, "activity_pre_1d"
    raise ValueError(gate)


def _build_gate_training_data(features: list[str]) -> tuple[pd.DataFrame, dict[str, object]]:
    if config.M1_GATE_TRAINING_DATA_PATH.exists():
        data = pd.read_csv(config.M1_GATE_TRAINING_DATA_PATH)
        return data, {
            "status": "already_present",
            "path": config.path_label(config.M1_GATE_TRAINING_DATA_PATH),
            "rows": int(len(data)),
        }
    zip_path = _predist_zip_path()
    if zip_path is None:
        raise FileNotFoundError(
            "Missing predist_dataset.zip needed to build M1 gate training features. "
            "Set THIRD_MODEL_PREDIST_ZIP_PATH, place it under data/_downloads, or run once with "
            "THIRD_MODEL_3RD_PROJECT_ROOT available."
        )
    rows: list[dict[str, object]] = []
    for gate in ["fault_gate", "task_gate", "activity_gate"]:
        target, dataset_id = _filter_gate_prediction(gate)
        target = target.drop_duplicates("source_id").sort_values("source_id").reset_index(drop=True)
        for rec in target.itertuples(index=False):
            substation_id = int(getattr(rec, "substation_id"))
            window_start = pd.Timestamp(getattr(rec, "window_start"))
            window_end = pd.Timestamp(getattr(rec, "window_end"))
            raw = _load_operational_from_zip(str(zip_path), substation_id)
            window = raw.loc[raw["timestamp"].ge(window_start) & raw["timestamp"].lt(window_end)].copy()
            row = rec._asdict()
            row["gate"] = gate
            row["training_dataset_id"] = dataset_id
            for feature in features:
                signal, feature_stat = feature.split("__", 1)
                row[feature] = _compute_feature(window, signal, feature_stat, window_start, window_end)
            sample_count = int(len(window))
            expected = _expected_count(window_start, window_end)
            row["recomputed_sample_count"] = sample_count
            row["recomputed_expected_count"] = expected
            row["recomputed_coverage_rate"] = sample_count / expected if expected else 0.0
            row["y"] = int(getattr(rec, "y_true"))
            rows.append(row)
    data = pd.DataFrame(rows)
    data.to_csv(
        config.M1_GATE_TRAINING_DATA_PATH,
        index=False,
        encoding="utf-8-sig",
        float_format=config.CSV_FLOAT_FORMAT,
        lineterminator=config.CSV_LINE_TERMINATOR,
    )
    return data, {
        "status": "generated",
        "path": config.path_label(config.M1_GATE_TRAINING_DATA_PATH),
        "rows": int(len(data)),
        "predist_zip_source": config.path_label(zip_path, "THIRD_MODEL_PREDIST_ZIP_PATH"),
    }


def _make_rf_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=3,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def _make_logistic_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced",
                    solver="liblinear",
                    random_state=RANDOM_STATE,
                    max_iter=1000,
                ),
            ),
        ]
    )


def _class_one_probability(model: Pipeline, x: pd.DataFrame) -> np.ndarray:
    probabilities = model.predict_proba(x)
    classes = list(getattr(model, "classes_", [0, 1]))
    if 1 not in classes:
        return np.zeros(len(x))
    return probabilities[:, classes.index(1)]


def _metric_row(component: str, y_true: pd.Series, probability: np.ndarray, threshold: float) -> dict[str, object]:
    y_true_int = y_true.astype(int)
    y_pred = (probability >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true_int, y_pred, labels=[0, 1]).ravel()
    return {
        "component": component,
        "threshold": threshold,
        "rows": int(len(y_true_int)),
        "positive_rows": int((y_true_int == 1).sum()),
        "normal_rows": int((y_true_int == 0).sum()),
        "balanced_accuracy": balanced_accuracy_score(y_true_int, y_pred),
        "precision": precision_score(y_true_int, y_pred, zero_division=0),
        "recall": recall_score(y_true_int, y_pred, zero_division=0),
        "f1": f1_score(y_true_int, y_pred, zero_division=0),
        "normal_fpr": fp / (fp + tn) if (fp + tn) else np.nan,
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


def _pre_event_training_data(features: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    pool = pd.read_csv(config.M1_SOURCE_PRE_EVENT_FEATURE_POOL_PATH)
    missing = sorted(set(features) - set(pool.columns))
    if missing:
        raise ValueError(f"M1 pre-event feature pool missing compact13 features: {missing}")
    train = pool.loc[pool["pool_role"].isin(["fixed_eval", "expansion_candidate"])].copy()
    fixed_eval = pool.loc[pool["pool_role"].eq("fixed_eval")].copy()
    train["y"] = train["y"].astype(int)
    fixed_eval["y"] = fixed_eval["y"].astype(int)
    return train, fixed_eval


def _training_data_audit(gate_training: pd.DataFrame, pre_train: pd.DataFrame, pre_fixed_eval: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for gate, data in gate_training.groupby("gate", dropna=False):
        rows.append(
            {
                "component": gate,
                "training_dataset_id": data["training_dataset_id"].iloc[0],
                "rows": int(len(data)),
                "positive_rows": int(data["y"].astype(int).sum()),
                "normal_rows": int((data["y"].astype(int) == 0).sum()),
                "feature_source": config.path_label(config.M1_GATE_TRAINING_DATA_PATH),
            }
        )
    rows.append(
        {
            "component": "fault_pre_event_gate_train",
            "training_dataset_id": "expanded_compact13_full_pool",
            "rows": int(len(pre_train)),
            "positive_rows": int(pre_train["y"].sum()),
            "normal_rows": int((pre_train["y"] == 0).sum()),
            "feature_source": config.path_label(config.M1_SOURCE_PRE_EVENT_FEATURE_POOL_PATH),
        }
    )
    rows.append(
        {
            "component": "fault_pre_event_gate_eval",
            "training_dataset_id": "strict_no_event20_fixed_eval",
            "rows": int(len(pre_fixed_eval)),
            "positive_rows": int(pre_fixed_eval["y"].sum()),
            "normal_rows": int((pre_fixed_eval["y"] == 0).sum()),
            "feature_source": config.path_label(config.M1_SOURCE_PRE_EVENT_FEATURE_POOL_PATH),
        }
    )
    audit = pd.DataFrame(rows)
    audit.to_csv(config.M1_INTERNAL_TRAINING_DATA_AUDIT_PATH, index=False, encoding="utf-8-sig")
    return audit


def _fit_and_dump_models(features: list[str], gate_training: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict]]:
    registry_rows: list[dict[str, object]] = []
    reload_rows: list[dict[str, object]] = []
    model_meta: dict[str, dict] = {}
    gate_specs = [
        ("fault_gate", _make_rf_pipeline(), FAULT_GATE_THRESHOLD, "fault_no_overlap"),
        ("task_gate", _make_rf_pipeline(), TASK_GATE_THRESHOLD, "task_post_1d"),
        ("activity_gate", _make_rf_pipeline(), ACTIVITY_GATE_THRESHOLD, "activity_pre_1d"),
    ]
    for component, model, threshold, dataset_id in gate_specs:
        data = gate_training.loc[gate_training["gate"].eq(component)].copy()
        if data.empty:
            raise ValueError(f"No M1 training rows for {component}.")
        data["y"] = data["y"].astype(int)
        model.fit(data[features], data["y"])
        probability_before = _class_one_probability(model, data[features])
        path = MODEL_PATHS[component]
        joblib.dump(model, path)
        reloaded = joblib.load(path)
        probability_after = _class_one_probability(reloaded, data[features])
        pred_before = (probability_before >= threshold).astype(int)
        pred_after = (probability_after >= threshold).astype(int)
        registry_rows.append(
            {
                "component": component,
                "model_path": config.path_label(path),
                "model_type": "RandomForestClassifier_depth3",
                "training_dataset_id": dataset_id,
                "feature_set": "compact13",
                "feature_count": len(features),
                "threshold": threshold,
                "training_rows": int(len(data)),
                "positive_rows": int(data["y"].sum()),
                "normal_rows": int((data["y"] == 0).sum()),
                "joblib_sha256": _file_sha256(path),
                "source_commit_hash": _source_commit_hash(),
            }
        )
        reload_rows.append(
            {
                **_metric_row(component, data["y"], probability_after, threshold),
                "training_dataset_id": dataset_id,
                "model_path": config.path_label(path),
                "reload_max_probability_abs_diff": float(np.max(np.abs(probability_before - probability_after))),
                "reload_probability_allclose": bool(np.allclose(probability_before, probability_after, atol=1e-12, rtol=1e-12)),
                "reload_prediction_identical": bool(np.array_equal(pred_before, pred_after)),
                "feature_count": len(features),
            }
        )
        model_meta[component] = {
            "model": "RandomForestClassifier",
            "max_depth": 3,
            "feature_set": "compact13",
            "features": features,
            "threshold": threshold,
            "training_dataset_id": dataset_id,
            "model_path": config.path_label(path),
        }

    pre_train, pre_fixed_eval = _pre_event_training_data(features)
    pre_model = _make_logistic_pipeline()
    pre_model.fit(pre_train[features], pre_train["y"].astype(int))
    probability_before = _class_one_probability(pre_model, pre_fixed_eval[features])
    pre_path = MODEL_PATHS["fault_pre_event_gate"]
    joblib.dump(pre_model, pre_path)
    pre_reloaded = joblib.load(pre_path)
    probability_after = _class_one_probability(pre_reloaded, pre_fixed_eval[features])
    pred_before = (probability_before >= PRE_EVENT_THRESHOLD).astype(int)
    pred_after = (probability_after >= PRE_EVENT_THRESHOLD).astype(int)
    registry_rows.append(
        {
            "component": "fault_pre_event_gate",
            "model_path": config.path_label(pre_path),
            "model_type": "LogisticRegression_balanced",
            "training_dataset_id": "expanded_compact13_full_pool",
            "feature_set": "compact13_overlap",
            "feature_count": len(features),
            "threshold": PRE_EVENT_THRESHOLD,
            "training_rows": int(len(pre_train)),
            "positive_rows": int(pre_train["y"].sum()),
            "normal_rows": int((pre_train["y"] == 0).sum()),
            "joblib_sha256": _file_sha256(pre_path),
            "source_commit_hash": _source_commit_hash(),
        }
    )
    reload_rows.append(
        {
            **_metric_row("fault_pre_event_gate", pre_fixed_eval["y"], probability_after, PRE_EVENT_THRESHOLD),
            "training_dataset_id": "strict_no_event20_fixed_eval",
            "model_path": config.path_label(pre_path),
            "reload_max_probability_abs_diff": float(np.max(np.abs(probability_before - probability_after))),
            "reload_probability_allclose": bool(np.allclose(probability_before, probability_after, atol=1e-12, rtol=1e-12)),
            "reload_prediction_identical": bool(np.array_equal(pred_before, pred_after)),
            "feature_count": len(features),
        }
    )
    model_meta["fault_pre_event_gate"] = {
        "model": "LogisticRegression",
        "feature_set": "compact13_overlap",
        "features": features,
        "threshold": PRE_EVENT_THRESHOLD,
        "training_dataset_id": "expanded_compact13_full_pool",
        "validation_dataset_id": "strict_no_event20_fixed_eval",
        "model_path": config.path_label(pre_path),
    }
    _training_data_audit(gate_training, pre_train, pre_fixed_eval)
    registry = pd.DataFrame(registry_rows)
    reload_validation = pd.DataFrame(reload_rows)
    registry.to_csv(config.M1_INTERNAL_MODEL_REGISTRY_PATH, index=False, encoding="utf-8-sig")
    reload_validation.to_csv(config.M1_INTERNAL_RELOAD_VALIDATION_PATH, index=False, encoding="utf-8-sig")
    return registry, reload_validation, model_meta


def _write_runtime_metadata(model_meta: dict[str, dict]) -> dict[str, object]:
    payload = {
        "package_id": "m1_full_gate_runtime_policy_joblib_v1_internal",
        "report_id": "internal_m1_specialist_retrain",
        "source_commit_hash": _source_commit_hash(),
        "sklearn_version": sklearn.__version__,
        "created_artifacts": {
            key: config.path_label(path)
            for key, path in MODEL_PATHS.items()
        }
        | {
            "runtime_metadata": config.path_label(config.M1_SPECIALIST_MODEL_DIR / "m1_full_gate_runtime_policy_metadata.json"),
            "model_registry": config.path_label(config.M1_INTERNAL_MODEL_REGISTRY_PATH),
            "reload_validation": config.path_label(config.M1_INTERNAL_RELOAD_VALIDATION_PATH),
            "training_data_audit": config.path_label(config.M1_INTERNAL_TRAINING_DATA_AUDIT_PATH),
        },
        "runtime_policy": {
            "thresholds": {
                "fault_gate": FAULT_GATE_THRESHOLD,
                "task_gate": TASK_GATE_THRESHOLD,
                "activity_gate": ACTIVITY_GATE_THRESHOLD,
                "fault_pre_event_gate": PRE_EVENT_THRESHOLD,
            },
            "primary_state_order": ["fault", "task", "activity", "normal"],
            "near_threshold_band": 0.05,
        },
        "models": model_meta,
        "external_runtime_validation": {
            "dataset": "not_run_in_internal_retrain",
            "reason": "package-local retrain focuses on M1 source gate regeneration",
        },
    }
    target = config.M1_SPECIALIST_MODEL_DIR / "m1_full_gate_runtime_policy_metadata.json"
    write_json(target, payload)
    return payload


def regenerate_m1_specialist_source() -> dict[str, object]:
    """Regenerate M1 specialist gate joblibs from package-local training inputs."""
    config.ensure_dirs()
    materialized_inputs = _materialize_source_input_csvs()
    features = _compact13_features()
    gate_training, gate_training_payload = _build_gate_training_data(features)
    registry, reload_validation, model_meta = _fit_and_dump_models(features, gate_training)
    runtime_metadata = _write_runtime_metadata(model_meta)
    payload = {
        "stage": "retrain_m1_specialist",
        "mode": "internal_m1_source_package",
        "third_project_available_for_bootstrap": config.THIRD_PROJECT_ROOT.exists(),
        "materialized_inputs": materialized_inputs,
        "gate_training_data": gate_training_payload,
        "feature_count": len(features),
        "features": features,
        "outputs_expected": {
            "fault_gate": config.path_label(MODEL_PATHS["fault_gate"]),
            "task_gate": config.path_label(MODEL_PATHS["task_gate"]),
            "activity_gate": config.path_label(MODEL_PATHS["activity_gate"]),
            "fault_pre_event_gate": config.path_label(MODEL_PATHS["fault_pre_event_gate"]),
            "runtime_metadata": config.path_label(config.M1_SPECIALIST_MODEL_DIR / "m1_full_gate_runtime_policy_metadata.json"),
            "model_registry": config.path_label(config.M1_INTERNAL_MODEL_REGISTRY_PATH),
            "reload_validation": config.path_label(config.M1_INTERNAL_RELOAD_VALIDATION_PATH),
            "training_data_audit": config.path_label(config.M1_INTERNAL_TRAINING_DATA_AUDIT_PATH),
        },
        "registry_rows": int(len(registry)),
        "reload_validation_rows": int(len(reload_validation)),
        "runtime_policy_source": runtime_metadata["package_id"],
    }
    write_json(config.M1_SOURCE_RETRAIN_METADATA_PATH, payload)
    return payload

