from __future__ import annotations

import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_sample_weight

from . import config
from .anomaly import train_score_anomaly
from .common import (
    add_causal_lag_features,
    add_sensor_horizon_features,
    binary_metrics,
    model_matrix,
    read_json,
    split_masks,
    write_json,
)
from .data_io import build_raw_inventory, import_canonical_windows


warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

NEW_ANOMALY_FEATURES = [
    "iforest_anomaly_score",
    "mahalanobis_score",
    "iforest_score_ratio",
    "mahalanobis_score_ratio",
    "anomaly_consensus_count",
    "strong_anomaly_label",
    "anomaly_criticality",
    "anomaly_event_label",
]

RAW_POINT_AE_FEATURES = [
    "raw_ae_score_mean",
    "raw_ae_score_max",
    "raw_ae_score_p95",
    "raw_ae_score_ratio_q999_max",
    "raw_ae_score_ratio_q998_max",
    "raw_ae_seq_cmax_q999",
    "raw_ae_seq_cmax_q998",
    "raw_ae_roll5d_cmax_q999",
    "raw_ae_roll5d_cmax_q998",
    "raw_ae_alarm_q999_c24",
    "raw_ae_alarm_q999_c32",
    "raw_ae_alarm_q998_c48",
    "raw_ae_alarm_union_q998_c48_or_q999_spike",
    "raw_ae_has_model",
]

MULTI_WINDOW_FEATURES = [
    f"mw_anomaly_{horizon}_{suffix}"
    for horizon in ["1h", "3h", "6h", "12h"]
    for suffix in [
        "iforest_score_ratio",
        "mahalanobis_score_ratio",
        "score",
        "label",
        "strong_label",
        "criticality",
        "event_label",
    ]
] + [
    "mw_anomaly_multi_window_count",
    "mw_anomaly_short_term_confirmed",
    "mw_anomaly_main_confirmed",
    "mw_anomaly_persistent_confirmed",
    "mw_anomaly_fast_spike",
    "mw_anomaly_operational_confirmed",
    "mw_anomaly_context_score",
    "mw_anomaly_has_raw_data",
    "group_mahalanobis_global_score_ratio",
    "group_mahalanobis_global_label",
    "group_mahalanobis_manufacturer_score_ratio",
    "group_mahalanobis_manufacturer_label",
    "group_mahalanobis_configuration_score_ratio",
    "group_mahalanobis_configuration_label",
    "group_mahalanobis_aux_count",
]

RISK_TEMPORAL_FEATURES = [
    "risk_probability_raw",
    "risk_probability_roll4_max",
    "risk_probability_roll8_mean",
    "risk_probability_roll8_max",
    "risk_probability_delta1",
    "risk_temporal_boost",
]

RISK_EPISODE_FEATURES = [
    "risk_watch_label",
    "risk_recent_high_count_48h",
    "risk_recent_watch_count_48h",
    "risk_repeated_high_48h",
    "risk_repeated_watch_48h",
    "risk_high_episode_start",
]

RISK_HORIZON_FEATURES = [
    "risk_score_24h_max",
    "risk_score_24h_mean",
    "risk_high_count_24h",
    "risk_watch_count_24h",
    "risk_score_3d_max",
    "risk_score_3d_mean",
    "risk_score_3d_slope",
    "risk_high_count_3d",
    "risk_watch_count_3d",
    "risk_episode_start_count_3d",
    "risk_score_7d_max",
    "risk_score_7d_mean",
    "risk_score_7d_slope",
    "risk_high_count_7d",
    "risk_watch_count_7d",
    "risk_episode_start_count_7d",
    "anomaly_criticality_24h_max",
    "anomaly_criticality_3d_max",
    "anomaly_criticality_7d_max",
    "raw_ae_alarm_count_24h",
    "raw_ae_alarm_count_3d",
    "raw_ae_alarm_count_7d",
    "mw_anomaly_confirmed_count_24h",
    "mw_anomaly_confirmed_count_3d",
    "mw_anomaly_confirmed_count_7d",
    "mw_anomaly_persistent_count_3d",
    "mw_anomaly_persistent_count_7d",
    "multi_horizon_persistence_score",
]

SENSOR_HORIZON_SOURCE_COLUMNS = [
    "network_temperature_gap__mean",
    "network_temperature_gap__max_abs",
    "network_temperature_gap__last",
    "hc1_supply_temperature_gap__last",
    "dhw_supply_temperature_gap__last",
    "outdoor_temperature__mean",
    "outdoor_temperature__std",
    "p_net_supply_temperature__mean",
    "p_net_return_temperature__mean",
    "p_net_meter_flow__mean",
    "p_net_meter_heat_power__mean",
    "s_hc1_supply_temperature__mean",
    "s_hc1_supply_temperature_setpoint__mean",
    "s_dhw_supply_temperature__mean",
    "s_dhw_supply_temperature_setpoint__mean",
]

TIMEFLOW_SOURCE_COLUMNS = [
    "anomaly_ensemble_score",
    "iforest_anomaly_score",
    "mahalanobis_score",
    "mw_anomaly_1h_score",
    "mw_anomaly_3h_score",
    "mw_anomaly_6h_score",
    "mw_anomaly_12h_score",
    "mw_anomaly_context_score",
    "group_mahalanobis_manufacturer_score_ratio",
    "group_mahalanobis_configuration_score_ratio",
    "raw_ae_score_max",
    "raw_ae_score_ratio_q999_max",
    "raw_ae_roll5d_cmax_q999",
    "raw_ae_roll5d_cmax_q998",
    "risk_probability",
    "risk_score",
    "risk_probability_roll4_max",
    "risk_probability_roll8_mean",
    "risk_temporal_boost",
    "network_temperature_gap__mean",
    "p_net_return_temperature__mean",
    "p_net_supply_temperature__mean",
]

PRIORITY_RISK_LEVEL_POINTS = {"critical": 38.0, "high": 28.0, "medium": 15.0, "low": 4.0}
PRIORITY_LEADTIME_BUCKET_POINTS = {"0-24h": 18.0, "1-3d": 10.0, "3-7d": 4.0}
PRIORITY_LEVEL_THRESHOLDS = {"urgent": 70.0, "high": 48.0, "medium": 34.0}
LEADTIME_LABEL_TO_INDEX = {label: index for index, label in enumerate(config.LEADTIME_LABELS)}


def _load_lgbm_classifier():
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier
    except Exception:
        return None


def _numeric_series(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column in frame.columns:
        source = frame[column]
    else:
        source = pd.Series(default, index=frame.index)
    return pd.to_numeric(source, errors="coerce").fillna(default)


def _ensure_prerequisites() -> None:
    config.ensure_dirs()
    if not config.TRAINABLE_WINDOWS_PATH.exists():
        build_raw_inventory()
        import_canonical_windows()
    if not config.ANOMALY_SCORES_PATH.exists():
        train_score_anomaly()


def _lead_time_bucket(hours: object) -> str:
    value = pd.to_numeric(hours, errors="coerce")
    if pd.isna(value):
        return ""
    if float(value) <= 24.0:
        return "0-24h"
    if float(value) <= 72.0:
        return "1-3d"
    return "3-7d"


def _load_windows() -> pd.DataFrame:
    windows = pd.read_csv(config.TRAINABLE_WINDOWS_PATH)
    if config.RISK_SPLIT_COLUMN not in windows.columns:
        source_split = "split_regime_based" if "split_regime_based" in windows.columns else config.ANOMALY_SPLIT_COLUMN
        windows[config.RISK_SPLIT_COLUMN] = windows[source_split]
    if "split_event_based" not in windows.columns:
        windows["split_event_based"] = windows[config.RISK_SPLIT_COLUMN]
    if "lead_time_bucket" not in windows.columns:
        windows["lead_time_bucket"] = windows["estimated_lead_time_hours"].map(_lead_time_bucket)
    for column in ["days_since_last_task_event", "days_since_last_any_event"]:
        if column not in windows.columns:
            windows[column] = np.nan
    return windows


def _base_modeling_frame() -> pd.DataFrame:
    windows = _load_windows()
    anomaly = pd.read_csv(config.ANOMALY_SCORES_PATH)
    anomaly_columns = [*config.KEY_COLUMNS, "anomaly_ensemble_score", "anomaly_score", *NEW_ANOMALY_FEATURES]
    anomaly_columns = [column for column in anomaly_columns if column in anomaly.columns]
    modeling = windows.merge(
        anomaly[anomaly_columns].drop_duplicates(config.KEY_COLUMNS),
        on=config.KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_anomaly"),
    )
    if "anomaly_ensemble_score" not in modeling.columns and "anomaly_score" in modeling.columns:
        modeling["anomaly_ensemble_score"] = modeling["anomaly_score"]
    modeling["anomaly_score"] = modeling["anomaly_ensemble_score"]
    for column in [*MULTI_WINDOW_FEATURES, *RAW_POINT_AE_FEATURES]:
        if column not in modeling.columns:
            modeling[column] = 0.0
    modeling, sensor_horizon_features = add_sensor_horizon_features(modeling, SENSOR_HORIZON_SOURCE_COLUMNS)
    modeling.attrs["sensor_horizon_features"] = sensor_horizon_features
    return modeling


def _binary_model():
    lgbm = _load_lgbm_classifier()
    if lgbm is not None:
        return lgbm(
            objective="binary",
            n_estimators=180,
            learning_rate=0.04,
            num_leaves=15,
            min_child_samples=45,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.1,
            reg_lambda=1.0,
            class_weight="balanced",
            random_state=config.RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
        ), "LightGBM LGBMClassifier"
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=220,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=config.RANDOM_STATE,
    ), "sklearn HistGradientBoostingClassifier fallback"


def _multiclass_model():
    lgbm = _load_lgbm_classifier()
    if lgbm is not None:
        return lgbm(
            objective="multiclass",
            num_class=len(config.LEADTIME_LABELS),
            n_estimators=220,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=18,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_alpha=0.1,
            reg_lambda=1.0,
            class_weight="balanced",
            random_state=config.RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
        ), "LightGBM LGBMClassifier multiclass"
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=260,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=config.RANDOM_STATE,
    ), "sklearn HistGradientBoostingClassifier fallback"


def _fit_model(model, x: pd.DataFrame, y: pd.Series):
    sample_weight = compute_sample_weight("balanced", y)
    return model.fit(x, y, sample_weight=sample_weight)


def _add_temporal_risk_score(scored: pd.DataFrame) -> pd.DataFrame:
    result = scored.copy()
    result["risk_probability_raw"] = pd.to_numeric(result["risk_probability"], errors="coerce").fillna(0.0)
    working = result.copy()
    working["window_start"] = pd.to_datetime(working["window_start"], errors="coerce")
    working["window_end"] = pd.to_datetime(working["window_end"], errors="coerce")
    working["_original_index"] = working.index
    working = working.sort_values(["manufacturer", "substation_id", "window_end", "window_start"])
    previous_end = working.groupby(["manufacturer", "substation_id"], dropna=False)["window_end"].shift(1)
    gap_hours = (working["window_start"] - previous_end).dt.total_seconds() / 3600.0
    new_segment = previous_end.isna() | gap_hours.gt(24.0)
    working["_risk_segment_id"] = new_segment.groupby(
        [working["manufacturer"], working["substation_id"]], dropna=False
    ).cumsum()
    grouped = working.groupby(["manufacturer", "substation_id", "_risk_segment_id"], dropna=False)["risk_probability_raw"]
    working["risk_probability_roll4_max"] = grouped.transform(lambda series: series.rolling(4, min_periods=1).max())
    working["risk_probability_roll8_mean"] = grouped.transform(lambda series: series.rolling(8, min_periods=1).mean())
    working["risk_probability_roll8_max"] = grouped.transform(lambda series: series.rolling(8, min_periods=1).max())
    working["risk_probability_delta1"] = grouped.diff().fillna(0.0)
    temporal = working.set_index("_original_index")[
        ["risk_probability_roll4_max", "risk_probability_roll8_mean", "risk_probability_roll8_max", "risk_probability_delta1"]
    ].reindex(result.index)
    result = pd.concat([result, temporal], axis=1)
    roll4 = pd.to_numeric(result["risk_probability_roll4_max"], errors="coerce").fillna(0.0) * 0.90
    roll8 = (pd.to_numeric(result["risk_probability_roll8_mean"], errors="coerce").fillna(0.0) * 1.05).clip(upper=1.0)
    result["risk_score"] = np.maximum.reduce(
        [result["risk_probability_raw"].to_numpy("float64"), roll4.to_numpy("float64"), roll8.to_numpy("float64")]
    )
    result["risk_temporal_boost"] = (result["risk_score"] - result["risk_probability_raw"]).clip(lower=0.0)
    return result


def _risk_level(score: float, medium: float, high: float, critical: float) -> str:
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def _apply_risk_thresholds(scored: pd.DataFrame, metadata: dict[str, object]) -> pd.DataFrame:
    result = scored.copy()
    thresholds = metadata.get("base_thresholds") or config.RISK_BASE_THRESHOLDS
    medium = float(thresholds.get("medium", config.RISK_BASE_THRESHOLDS["medium"]))
    high = float(thresholds.get("high", config.RISK_BASE_THRESHOLDS["high"]))
    critical = float(thresholds.get("critical", config.RISK_BASE_THRESHOLDS["critical"]))
    result["risk_threshold_medium_applied"] = medium
    result["risk_threshold_high_applied"] = high
    result["risk_threshold_critical_applied"] = critical
    result["group_threshold_override_applied"] = 0
    result["risk_level"] = result["risk_score"].map(lambda score: _risk_level(float(score), medium, high, critical))
    result["risk_level_calibrated"] = result["risk_level"]
    result["risk_high_or_critical"] = result["risk_level"].isin(["high", "critical"]).astype("int8")
    return result


def _add_risk_episode_features(scored: pd.DataFrame) -> pd.DataFrame:
    result = scored.copy()
    result["risk_watch_label"] = result["risk_level"].isin(["medium", "high", "critical"]).astype("int8")
    working = result.copy()
    working["window_start"] = pd.to_datetime(working["window_start"], errors="coerce")
    working["window_end"] = pd.to_datetime(working["window_end"], errors="coerce")
    working["_original_index"] = working.index
    working = working.sort_values(["manufacturer", "substation_id", "window_end", "window_start"])
    previous_end = working.groupby(["manufacturer", "substation_id"], dropna=False)["window_end"].shift(1)
    gap_hours = (working["window_start"] - previous_end).dt.total_seconds() / 3600.0
    new_segment = previous_end.isna() | gap_hours.gt(24.0)
    working["_risk_segment_id"] = new_segment.groupby(
        [working["manufacturer"], working["substation_id"]], dropna=False
    ).cumsum()
    group_keys = [working["manufacturer"], working["substation_id"], working["_risk_segment_id"]]
    high = pd.to_numeric(working["risk_high_or_critical"], errors="coerce").fillna(0).astype("int8")
    watch = pd.to_numeric(working["risk_watch_label"], errors="coerce").fillna(0).astype("int8")
    working["risk_recent_high_count_48h"] = high.groupby(group_keys).transform(lambda s: s.rolling(8, min_periods=1).sum())
    working["risk_recent_watch_count_48h"] = watch.groupby(group_keys).transform(lambda s: s.rolling(8, min_periods=1).sum())
    previous_high = working.groupby(["manufacturer", "substation_id", "_risk_segment_id"], dropna=False)[
        "risk_high_or_critical"
    ].shift(1).fillna(0)
    working["risk_repeated_high_48h"] = working["risk_recent_high_count_48h"].ge(2).astype("int8")
    working["risk_repeated_watch_48h"] = working["risk_recent_watch_count_48h"].ge(3).astype("int8")
    working["risk_high_episode_start"] = (working["risk_high_or_critical"].eq(1) & previous_high.eq(0)).astype("int8")
    episode = working.set_index("_original_index")[RISK_EPISODE_FEATURES].reindex(result.index)
    for column in RISK_EPISODE_FEATURES:
        result[column] = pd.to_numeric(episode[column], errors="coerce").fillna(0)
    return result


def _rolling_slope(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).to_numpy("float64")
    if len(numeric) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(numeric), dtype="float64"), numeric, 1)[0])


def _add_multi_horizon_features(scored: pd.DataFrame) -> pd.DataFrame:
    result = scored.copy()
    working = result.copy()
    working["window_start"] = pd.to_datetime(working["window_start"], errors="coerce")
    working["window_end"] = pd.to_datetime(working["window_end"], errors="coerce")
    working["_original_index"] = working.index
    working = working.sort_values(["manufacturer", "substation_id", "window_end", "window_start"])
    previous_end = working.groupby(["manufacturer", "substation_id"], dropna=False)["window_end"].shift(1)
    gap_hours = (working["window_start"] - previous_end).dt.total_seconds() / 3600.0
    new_segment = previous_end.isna() | gap_hours.gt(24.0)
    working["_risk_segment_id"] = new_segment.groupby(
        [working["manufacturer"], working["substation_id"]], dropna=False
    ).cumsum()
    group_keys = [working["manufacturer"], working["substation_id"], working["_risk_segment_id"]]

    risk_score = _numeric_series(working, "risk_score")
    high = _numeric_series(working, "risk_high_or_critical").astype("int8")
    watch = _numeric_series(working, "risk_watch_label").astype("int8")
    episode_start = _numeric_series(working, "risk_high_episode_start").astype("int8")
    anomaly_criticality = _numeric_series(working, "anomaly_criticality")
    raw_alarm = (
        _numeric_series(working, "raw_ae_alarm_q999_c32").astype("int8")
        | _numeric_series(working, "raw_ae_alarm_q998_c48").astype("int8")
        | _numeric_series(working, "raw_ae_alarm_union_q998_c48_or_q999_spike").astype("int8")
    ).astype("int8")
    mw_confirmed = (
        _numeric_series(working, "mw_anomaly_main_confirmed").astype("int8")
        | _numeric_series(working, "mw_anomaly_operational_confirmed").astype("int8")
    ).astype("int8")
    mw_persistent = _numeric_series(working, "mw_anomaly_persistent_confirmed").astype("int8")
    horizon = pd.DataFrame(index=working.index)
    for name, window in {"24h": 4, "3d": 12, "7d": 28}.items():
        horizon[f"risk_score_{name}_max"] = risk_score.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).max())
        horizon[f"risk_score_{name}_mean"] = risk_score.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).mean())
        horizon[f"risk_high_count_{name}"] = high.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).sum())
        horizon[f"risk_watch_count_{name}"] = watch.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).sum())
        horizon[f"anomaly_criticality_{name}_max"] = anomaly_criticality.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).max())
        horizon[f"raw_ae_alarm_count_{name}"] = raw_alarm.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).sum())
        horizon[f"mw_anomaly_confirmed_count_{name}"] = mw_confirmed.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).sum())
        if name in {"3d", "7d"}:
            horizon[f"risk_score_{name}_slope"] = risk_score.groupby(group_keys).transform(
                lambda s, w=window: s.rolling(w, min_periods=2).apply(_rolling_slope, raw=False)
            ).fillna(0.0)
            horizon[f"risk_episode_start_count_{name}"] = episode_start.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).sum())
            horizon[f"mw_anomaly_persistent_count_{name}"] = mw_persistent.groupby(group_keys).transform(lambda s, w=window: s.rolling(w, min_periods=1).sum())
    horizon["_original_index"] = working["_original_index"]
    horizon = horizon.set_index("_original_index").reindex(result.index)
    for column in RISK_HORIZON_FEATURES:
        if column not in horizon.columns and column != "multi_horizon_persistence_score":
            horizon[column] = 0.0
        if column != "multi_horizon_persistence_score":
            result[column] = pd.to_numeric(horizon[column], errors="coerce").fillna(0.0)
    result["multi_horizon_persistence_score"] = (
        (result["risk_high_count_24h"].clip(upper=4) / 4.0) * 4.0
        + (result["risk_high_count_3d"].clip(upper=12) / 12.0) * 5.0
        + (result["risk_high_count_7d"].clip(upper=28) / 28.0) * 5.0
        + result["risk_score_3d_slope"].clip(lower=0.0, upper=0.08) * 25.0
        + result["risk_score_7d_slope"].clip(lower=0.0, upper=0.05) * 20.0
        + result["raw_ae_alarm_count_7d"].clip(upper=3) * 1.5
        + result["mw_anomaly_confirmed_count_24h"].clip(upper=4) * 0.6
        + result["mw_anomaly_confirmed_count_3d"].clip(upper=12) * 0.25
        + result["mw_anomaly_persistent_count_7d"].clip(upper=4) * 0.8
    ).clip(upper=18.0)
    return result


def train_score_risk_internal() -> pd.DataFrame:
    metadata = read_json(config.RISK_METADATA_PATH) if config.RISK_METADATA_PATH.exists() else read_json(config.PACKAGED_RISK_METADATA_PATH)
    modeling = _base_modeling_frame()
    features = list(metadata["model_feature_columns"])
    x_all = model_matrix(modeling, features)
    y_all = modeling["label"].eq("pre_fault").astype(int)
    train_mask = modeling[config.RISK_SPLIT_COLUMN].eq("train")
    if y_all.loc[train_mask].nunique() < 2:
        raise ValueError("Risk internal retrain requires both normal and pre_fault rows in train split.")
    model, model_type = _binary_model()
    _fit_model(model, x_all.loc[train_mask], y_all.loc[train_mask])
    class_index = list(getattr(model, "classes_", [0, 1])).index(1)
    scored = modeling.copy()
    scored["risk_probability"] = model.predict_proba(x_all)[:, class_index]
    scored = _add_temporal_risk_score(scored)
    scored = _apply_risk_thresholds(scored, metadata)
    scored = _add_risk_episode_features(scored)
    scored = _add_multi_horizon_features(scored)

    metrics = []
    for split, mask in split_masks(scored, config.RISK_SPLIT_COLUMN).items():
        if int(mask.sum()):
            metrics.append(binary_metrics(scored.loc[mask], "risk_score", "risk_high_or_critical", split, "internal_m1_risk"))
    pd.DataFrame(metrics).to_csv(config.REPORT_DIR / "internal_current_best_risk_metrics.csv", index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)

    output_columns = [
        *config.KEY_COLUMNS,
        "source_file",
        "configuration_type",
        "season_bucket",
        "label",
        "fault_label",
        "fault_event_id",
        "estimated_lead_time_hours",
        "lead_time_bucket",
        "maintenance_related",
        "disturbance_count",
        "days_since_last_task_event",
        "days_since_last_any_event",
        "split_event_based",
        config.RISK_SPLIT_COLUMN,
        "split_regime_based",
        config.ANOMALY_SPLIT_COLUMN,
        "split_substation_based",
        "anomaly_score",
        "anomaly_ensemble_score",
        *NEW_ANOMALY_FEATURES,
        *MULTI_WINDOW_FEATURES,
        *RAW_POINT_AE_FEATURES,
        *list(modeling.attrs.get("sensor_horizon_features", [])),
        "risk_probability",
        *RISK_TEMPORAL_FEATURES,
        "risk_score",
        *RISK_EPISODE_FEATURES,
        *RISK_HORIZON_FEATURES,
        "risk_level",
        "risk_level_calibrated",
        "risk_threshold_medium_applied",
        "risk_threshold_high_applied",
        "risk_threshold_critical_applied",
        "group_threshold_override_applied",
        "risk_high_or_critical",
    ]
    output_columns = [column for column in output_columns if column in scored.columns]
    scored[output_columns].to_csv(config.RISK_SCORES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    joblib.dump(model, config.RISK_MODEL_PATH)
    metadata.update(
        {
            "model_type": model_type,
            "feature_count": len(features),
            "model_feature_columns": features,
            "internal_regeneration": True,
            "internal_regeneration_scope": config.PROJECT_SCOPE,
            "output_scores_path": config.path_label(config.RISK_SCORES_PATH),
            "output_model_path": config.path_label(config.RISK_MODEL_PATH),
        }
    )
    write_json(config.RISK_METADATA_PATH, metadata)
    return scored[output_columns].copy()


def _leadtime_metrics(y_true: pd.Series, y_pred: pd.Series, probabilities: np.ndarray, split: str) -> dict[str, object]:
    return {
        "split": split,
        "row_count": int(len(y_true)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "top2_accuracy": float((probabilities.argsort(axis=1)[:, -2:] == y_true.to_numpy().reshape(-1, 1)).any(axis=1).mean())
        if len(y_true)
        else float("nan"),
    }


def train_score_leadtime_internal() -> pd.DataFrame:
    metadata = read_json(config.LEADTIME_METADATA_PATH) if config.LEADTIME_METADATA_PATH.exists() else read_json(config.PACKAGED_LEADTIME_METADATA_PATH)
    windows = _load_windows()
    risk = pd.read_csv(config.RISK_SCORES_PATH)
    risk_columns = [
        *config.KEY_COLUMNS,
        "anomaly_score",
        "anomaly_ensemble_score",
        *NEW_ANOMALY_FEATURES,
        *MULTI_WINDOW_FEATURES,
        *RAW_POINT_AE_FEATURES,
        "risk_probability",
        "risk_score",
        *RISK_TEMPORAL_FEATURES,
        "risk_level",
        "risk_level_calibrated",
        "risk_high_or_critical",
        "risk_threshold_medium_applied",
        "risk_threshold_high_applied",
        "risk_threshold_critical_applied",
        *RISK_EPISODE_FEATURES,
        *RISK_HORIZON_FEATURES,
    ]
    risk_columns = [column for column in risk_columns if column in risk.columns]
    modeling = windows.merge(
        risk[risk_columns].drop_duplicates(config.KEY_COLUMNS),
        on=config.KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
    )
    if "risk_probability" not in modeling.columns and "risk_score" in modeling.columns:
        modeling["risk_probability"] = modeling["risk_score"]
    modeling["manufacturer_code"] = modeling["manufacturer"].map({"manufacturer 1": 0, "manufacturer 2": 1}).fillna(-1).astype("int16")
    config_map = {
        "SH": 0,
        "SH + DHW": 1,
        "SH + DHW with sub-circuits": 2,
        "SH with buffer tank": 3,
        "SH with sub-circuits": 4,
        "missing": 5,
    }
    modeling["configuration_code"] = modeling["configuration_type"].fillna("missing").map(config_map).fillna(-1).astype("int16")
    modeling, timeflow_features = add_causal_lag_features(modeling, TIMEFLOW_SOURCE_COLUMNS)
    modeling, sensor_horizon_features = add_sensor_horizon_features(modeling, SENSOR_HORIZON_SOURCE_COLUMNS)
    modeling["lead_time_bucket"] = modeling["lead_time_bucket"].replace({"0-6h": "0-24h", "6-24h": "0-24h"})
    valid_target = modeling["label"].eq("pre_fault") & modeling["lead_time_bucket"].isin(config.LEADTIME_LABELS)
    modeling["lead_time_target"] = np.nan
    modeling.loc[valid_target, "lead_time_target"] = modeling.loc[valid_target, "lead_time_bucket"].map(LEADTIME_LABEL_TO_INDEX).astype(int)
    if int(valid_target.sum()) == 0:
        raise ValueError("Leadtime internal retrain requires pre_fault rows with lead_time_bucket.")

    features = list(metadata["model_feature_columns"])
    x_all = model_matrix(modeling, features)
    y = modeling.loc[valid_target, "lead_time_target"].astype(int)
    train_mask = valid_target & modeling[config.RISK_SPLIT_COLUMN].eq("train")
    if y.loc[modeling.loc[valid_target].index.intersection(modeling.index[train_mask])].nunique() < 2:
        raise ValueError("Leadtime internal retrain requires at least two classes in train split.")
    model, model_type = _multiclass_model()
    _fit_model(model, x_all.loc[train_mask], modeling.loc[train_mask, "lead_time_target"].astype(int))
    probabilities = model.predict_proba(x_all)
    classes = list(getattr(model, "classes_", range(len(config.LEADTIME_LABELS))))
    full_prob = np.zeros((len(modeling), len(config.LEADTIME_LABELS)), dtype="float64")
    for source_index, cls in enumerate(classes):
        full_prob[:, int(cls)] = probabilities[:, source_index]
    predicted_index = full_prob.argmax(axis=1)
    scored = modeling.copy()
    scored["predicted_lead_time_index"] = predicted_index
    scored["predicted_lead_time_bucket"] = [config.LEADTIME_LABELS[index] for index in predicted_index]
    scored["predicted_lead_time_confidence"] = full_prob.max(axis=1)
    scored["lead_time_bucket_distance"] = (scored["lead_time_target"] - scored["predicted_lead_time_index"]).abs()
    for index, label in enumerate(config.LEADTIME_LABELS):
        scored[f"leadtime_prob_{label}"] = full_prob[:, index]
    midpoint_hours = np.array([12.0, 48.0, 120.0], dtype="float64")
    scored["expected_lead_time_hours"] = full_prob.dot(midpoint_hours)
    scored["leadtime_near_term_probability"] = scored["leadtime_prob_0-24h"]
    scored["leadtime_within_3d_probability"] = scored["leadtime_prob_0-24h"] + scored["leadtime_prob_1-3d"]
    scored["leadtime_urgency_score"] = (
        1.0 - ((scored["expected_lead_time_hours"] - midpoint_hours.min()) / (midpoint_hours.max() - midpoint_hours.min()))
    ).clip(0.0, 1.0)

    metric_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []
    trainable = scored.loc[valid_target].copy()
    for split, mask in split_masks(trainable, config.RISK_SPLIT_COLUMN).items():
        if not int(mask.sum()):
            continue
        idx = trainable.index[mask]
        metric_rows.append(
            _leadtime_metrics(
                trainable.loc[idx, "lead_time_target"].astype(int),
                trainable.loc[idx, "predicted_lead_time_index"].astype(int),
                full_prob[idx],
                split,
            )
        )
        matrix = confusion_matrix(
            trainable.loc[idx, "lead_time_target"].astype(int),
            trainable.loc[idx, "predicted_lead_time_index"].astype(int),
            labels=list(range(len(config.LEADTIME_LABELS))),
        )
        for true_index, true_label in enumerate(config.LEADTIME_LABELS):
            for pred_index, pred_label in enumerate(config.LEADTIME_LABELS):
                confusion_rows.append({"split": split, "actual_bucket": true_label, "predicted_bucket": pred_label, "count": int(matrix[true_index, pred_index])})
    pd.DataFrame(metric_rows).to_csv(config.REPORT_DIR / "internal_current_best_leadtime_metrics.csv", index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    pd.DataFrame(confusion_rows).to_csv(config.REPORT_DIR / "internal_current_best_leadtime_confusion.csv", index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)

    output_columns = [
        *config.KEY_COLUMNS,
        "source_file",
        "configuration_type",
        "season_bucket",
        "label",
        "fault_label",
        "fault_event_id",
        "estimated_lead_time_hours",
        "lead_time_bucket",
        "lead_time_target",
        "anomaly_score",
        "anomaly_ensemble_score",
        *NEW_ANOMALY_FEATURES,
        *MULTI_WINDOW_FEATURES,
        *RAW_POINT_AE_FEATURES,
        "risk_probability",
        "risk_score",
        *RISK_TEMPORAL_FEATURES,
        *RISK_EPISODE_FEATURES,
        *RISK_HORIZON_FEATURES,
        *timeflow_features,
        *sensor_horizon_features,
        "risk_level",
        "risk_level_calibrated",
        "risk_high_or_critical",
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "predicted_lead_time_index",
        "lead_time_bucket_distance",
        *[f"leadtime_prob_{label}" for label in config.LEADTIME_LABELS],
        "expected_lead_time_hours",
        "leadtime_near_term_probability",
        "leadtime_within_3d_probability",
        "leadtime_urgency_score",
        config.RISK_SPLIT_COLUMN,
        config.ANOMALY_SPLIT_COLUMN,
        "split_substation_based",
    ]
    output_columns = [column for column in output_columns if column in scored.columns]
    scored[output_columns].to_csv(config.LEADTIME_SCORES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    joblib.dump(model, config.LEADTIME_MODEL_PATH)
    metadata.update(
        {
            "model_type": model_type,
            "feature_count": len(features),
            "model_feature_columns": features,
            "timeflow_features": timeflow_features,
            "sensor_horizon_features": sensor_horizon_features,
            "internal_regeneration": True,
            "internal_regeneration_scope": config.PROJECT_SCOPE,
            "output_scores_path": config.path_label(config.LEADTIME_SCORES_PATH),
            "output_model_path": config.path_label(config.LEADTIME_MODEL_PATH),
        }
    )
    write_json(config.LEADTIME_METADATA_PATH, metadata)
    return scored[output_columns].copy()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _leadtime_confidence_multiplier(confidence: float) -> float:
    if pd.isna(confidence):
        return 0.5
    if confidence >= 0.8:
        return 1.0
    if confidence >= 0.6:
        return 0.8
    return 0.6


def _risk_probability_component(probability: float) -> float:
    if pd.isna(probability):
        return 0.0
    return _clamp(float(probability) * 18.0, 0.0, 18.0)


def _leadtime_ordinal_component(urgency_score: float) -> float:
    if pd.isna(urgency_score):
        return 0.0
    return _clamp(float(urgency_score) * 4.0, 0.0, 4.0)


def _anomaly_component(row: pd.Series) -> float:
    score = pd.to_numeric(row.get("anomaly_ensemble_score"), errors="coerce")
    consensus = pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce")
    criticality = pd.to_numeric(row.get("anomaly_criticality"), errors="coerce")
    score = 0.0 if pd.isna(score) else float(score)
    consensus = 0.0 if pd.isna(consensus) else float(consensus)
    criticality = 0.0 if pd.isna(criticality) else float(criticality)
    return (
        _clamp((score - 0.8) * 10.0, 0.0, 8.0)
        + (3.0 if consensus >= 2 else 1.0 if consensus >= 1 else 0.0)
        + _clamp(criticality * 0.6, 0.0, 3.0)
    )


def _multi_window_anomaly_component(row: pd.Series) -> float:
    count = pd.to_numeric(row.get("mw_anomaly_multi_window_count"), errors="coerce")
    context = pd.to_numeric(row.get("mw_anomaly_context_score"), errors="coerce")
    score = _clamp((0.0 if pd.isna(context) else float(context)) * 0.45, 0.0, 4.5)
    score += _clamp((0.0 if pd.isna(count) else float(count)) * 0.8, 0.0, 3.0)
    for column, points in [
        ("mw_anomaly_short_term_confirmed", 1.5),
        ("mw_anomaly_main_confirmed", 3.0),
        ("mw_anomaly_persistent_confirmed", 2.5),
        ("mw_anomaly_operational_confirmed", 1.0),
    ]:
        if pd.to_numeric(row.get(column), errors="coerce") >= 1:
            score += points
    return _clamp(score, 0.0, 12.0)


def _risk_episode_component(row: pd.Series) -> float:
    high_count = pd.to_numeric(row.get("risk_recent_high_count_48h"), errors="coerce")
    temporal_boost = pd.to_numeric(row.get("risk_temporal_boost"), errors="coerce")
    score = _clamp((0.0 if pd.isna(high_count) else float(high_count)) * 1.5, 0.0, 4.5)
    if pd.to_numeric(row.get("risk_repeated_high_48h"), errors="coerce") >= 1:
        score += 5.0
    elif pd.to_numeric(row.get("risk_repeated_watch_48h"), errors="coerce") >= 1:
        score += 2.0
    score += _clamp((0.0 if pd.isna(temporal_boost) else float(temporal_boost)) * 8.0, 0.0, 3.0)
    return _clamp(score, 0.0, 10.0)


def _multi_horizon_component(row: pd.Series) -> float:
    score = pd.to_numeric(row.get("multi_horizon_persistence_score"), errors="coerce")
    score = 0.0 if pd.isna(score) else _clamp(float(score), 0.0, 12.0)
    if pd.to_numeric(row.get("risk_high_count_24h"), errors="coerce") >= 2:
        score += 2.0
    if pd.to_numeric(row.get("risk_high_count_3d"), errors="coerce") >= 4:
        score += 2.0
    if pd.to_numeric(row.get("risk_high_count_7d"), errors="coerce") >= 8:
        score += 2.0
    return _clamp(score, 0.0, 18.0)


def _history_adjustment(row: pd.Series) -> tuple[float, str]:
    adjustment = 0.0
    reasons: list[str] = []
    for column, week_penalty, month_penalty, reason in [
        ("days_since_last_task_event", -8.0, -4.0, "recent_task"),
        ("days_since_last_any_event", -5.0, -2.0, "recent_any_event"),
    ]:
        days = pd.to_numeric(row.get(column), errors="coerce")
        if pd.isna(days):
            continue
        if days <= 7:
            adjustment += week_penalty
            reasons.append(f"{reason}_within_7d")
        elif days <= 30:
            adjustment += month_penalty
            reasons.append(f"{reason}_within_30d")
    return adjustment, "|".join(reasons)


def _urgency_bonus(row: pd.Series) -> tuple[float, str]:
    risk_level = row.get("risk_level_calibrated")
    leadtime = row.get("predicted_lead_time_bucket")
    consensus = pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce")
    criticality = pd.to_numeric(row.get("anomaly_criticality"), errors="coerce")
    if risk_level in {"high", "critical"} and leadtime == "0-24h" and pd.notna(consensus) and consensus >= 2:
        return 8.0, "high_risk_0_24h_strong_anomaly"
    if risk_level in {"high", "critical"} and leadtime in {"0-24h", "1-3d"} and pd.notna(criticality) and criticality >= config.CRITICALITY_THRESHOLD:
        return 5.0, "high_risk_near_leadtime_criticality"
    return 0.0, ""


def _priority_level(score: float) -> str:
    if score >= PRIORITY_LEVEL_THRESHOLDS["urgent"]:
        return "urgent"
    if score >= PRIORITY_LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= PRIORITY_LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _build_reason(row: pd.Series) -> str:
    parts: list[str] = []
    if row.get("risk_level_calibrated") in {"high", "critical"}:
        parts.append(f"risk={row['risk_level_calibrated']}")
    if row.get("predicted_lead_time_bucket") in {"0-24h", "1-3d"}:
        parts.append(f"leadtime={row['predicted_lead_time_bucket']}")
    if pd.to_numeric(row.get("anomaly_consensus_count"), errors="coerce") >= 2:
        parts.append("anomaly_consensus=2")
    if pd.to_numeric(row.get("risk_repeated_high_48h"), errors="coerce") >= 1:
        parts.append("repeated_high_48h")
    if row.get("history_adjustment_reason"):
        parts.append("history_adjusted")
    if row.get("urgency_bonus_reason"):
        parts.append(str(row["urgency_bonus_reason"]))
    return "|".join(parts)


def score_priority_internal() -> pd.DataFrame:
    risk = pd.read_csv(config.RISK_SCORES_PATH)
    leadtime = pd.read_csv(config.LEADTIME_SCORES_PATH)
    leadtime_columns = [
        *config.KEY_COLUMNS,
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "predicted_lead_time_index",
        "lead_time_bucket_distance",
        *[f"leadtime_prob_{label}" for label in config.LEADTIME_LABELS],
        "expected_lead_time_hours",
        "leadtime_near_term_probability",
        "leadtime_within_3d_probability",
        "leadtime_urgency_score",
    ]
    leadtime_columns = [column for column in leadtime_columns if column in leadtime.columns]
    merged = risk.merge(
        leadtime[leadtime_columns].drop_duplicates(config.KEY_COLUMNS),
        on=config.KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    merged["risk_base_score"] = merged["risk_level_calibrated"].map(PRIORITY_RISK_LEVEL_POINTS).fillna(0.0)
    merged["risk_probability_component_score"] = merged["risk_score"].map(_risk_probability_component)
    merged["leadtime_bucket_base_score"] = merged["predicted_lead_time_bucket"].map(PRIORITY_LEADTIME_BUCKET_POINTS).fillna(0.0)
    merged["leadtime_confidence_multiplier"] = merged["predicted_lead_time_confidence"].map(_leadtime_confidence_multiplier)
    merged["leadtime_component_score"] = merged["leadtime_bucket_base_score"] * merged["leadtime_confidence_multiplier"] * 0.75
    merged["leadtime_ordinal_component_score"] = merged.get("leadtime_urgency_score", pd.Series(0.0, index=merged.index)).map(_leadtime_ordinal_component) * 0.75
    merged["anomaly_component_score"] = merged.apply(_anomaly_component, axis=1)
    merged["multi_window_anomaly_component_score"] = merged.apply(_multi_window_anomaly_component, axis=1)
    merged["risk_episode_component_score"] = merged.apply(_risk_episode_component, axis=1)
    merged["multi_horizon_component_score"] = merged.apply(_multi_horizon_component, axis=1)
    history = merged.apply(_history_adjustment, axis=1)
    merged["history_adjustment_score"] = [score for score, _ in history]
    merged["history_adjustment_reason"] = [reason for _, reason in history]
    urgency = merged.apply(_urgency_bonus, axis=1)
    merged["urgency_bonus_score"] = [score for score, _ in urgency]
    merged["urgency_bonus_reason"] = [reason for _, reason in urgency]
    merged["priority_score_raw"] = (
        merged["risk_base_score"]
        + merged["risk_probability_component_score"]
        + merged["leadtime_component_score"]
        + merged["leadtime_ordinal_component_score"]
        + merged["anomaly_component_score"]
        + merged["multi_window_anomaly_component_score"]
        + merged["risk_episode_component_score"]
        + merged["multi_horizon_component_score"]
        + merged["history_adjustment_score"]
        + merged["urgency_bonus_score"]
    )
    merged["priority_score"] = merged["priority_score_raw"].map(lambda value: round(_clamp(float(value), 0.0, 100.0), 4))
    merged["priority_level"] = merged["priority_score"].map(_priority_level)
    merged["priority_reason"] = merged.apply(_build_reason, axis=1)
    merged["engine_version"] = "internal_m1_current_best_priority_engine_v1"
    output_columns = [
        *config.KEY_COLUMNS,
        "source_file",
        "configuration_type",
        "season_bucket",
        "label",
        "fault_label",
        "fault_event_id",
        "estimated_lead_time_hours",
        "lead_time_bucket",
        "anomaly_score",
        "anomaly_ensemble_score",
        *NEW_ANOMALY_FEATURES,
        *MULTI_WINDOW_FEATURES,
        *RAW_POINT_AE_FEATURES,
        "risk_probability",
        *RISK_TEMPORAL_FEATURES,
        "risk_score",
        *RISK_EPISODE_FEATURES,
        *RISK_HORIZON_FEATURES,
        "risk_level_calibrated",
        "risk_threshold_medium_applied",
        "risk_threshold_high_applied",
        "risk_threshold_critical_applied",
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        *[f"leadtime_prob_{label}" for label in config.LEADTIME_LABELS],
        "expected_lead_time_hours",
        "leadtime_near_term_probability",
        "leadtime_within_3d_probability",
        "leadtime_urgency_score",
        "days_since_last_task_event",
        "days_since_last_any_event",
        "risk_base_score",
        "risk_probability_component_score",
        "leadtime_component_score",
        "leadtime_ordinal_component_score",
        "anomaly_component_score",
        "multi_window_anomaly_component_score",
        "risk_episode_component_score",
        "multi_horizon_component_score",
        "history_adjustment_score",
        "history_adjustment_reason",
        "urgency_bonus_score",
        "urgency_bonus_reason",
        "priority_score",
        "priority_level",
        "priority_reason",
        "engine_version",
    ]
    output_columns = [column for column in output_columns if column in merged.columns]
    output = merged[output_columns].sort_values(
        ["priority_score", "risk_score", "anomaly_ensemble_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    output.to_csv(config.PRIORITY_SCORES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    write_json(
        config.PRIORITY_METADATA_PATH,
        {
            "engine_version": "internal_m1_current_best_priority_engine_v1",
            "input_risk_scores_path": config.path_label(config.RISK_SCORES_PATH),
            "input_leadtime_scores_path": config.path_label(config.LEADTIME_SCORES_PATH),
            "output_scores_path": config.path_label(config.PRIORITY_SCORES_PATH),
            "risk_level_points": PRIORITY_RISK_LEVEL_POINTS,
            "leadtime_bucket_points": PRIORITY_LEADTIME_BUCKET_POINTS,
            "leadtime_component_scale": 0.75,
            "leadtime_ordinal_component_scale": 0.75,
            "priority_level_thresholds": PRIORITY_LEVEL_THRESHOLDS,
            "notes": [
                "Generated inside this package without calling the external current-best source project.",
                "Scope is the packaged M1 canonical windows.",
            ],
        },
    )
    return output


def regenerate_current_best_source() -> dict[str, object]:
    _ensure_prerequisites()
    risk = train_score_risk_internal()
    leadtime = train_score_leadtime_internal()
    priority = score_priority_internal()
    payload = {
        "stage": "retrain_current_best",
        "mode": "internal_m1_package",
        "source_best_available": config.SOURCE_BEST_ROOT.exists(),
        "scope": config.PROJECT_SCOPE,
        "manufacturer_filter": config.M1_MANUFACTURER,
        "outputs": {
            "risk_scores": config.path_label(config.RISK_SCORES_PATH),
            "leadtime_scores": config.path_label(config.LEADTIME_SCORES_PATH),
            "priority_scores": config.path_label(config.PRIORITY_SCORES_PATH),
            "risk_model": config.path_label(config.RISK_MODEL_PATH),
            "leadtime_model": config.path_label(config.LEADTIME_MODEL_PATH),
            "priority_metadata": config.path_label(config.PRIORITY_METADATA_PATH),
        },
        "row_counts": {
            "risk_scores": int(len(risk)),
            "leadtime_scores": int(len(leadtime)),
            "priority_scores": int(len(priority)),
        },
        "note": "Current-best source body regenerated inside this repository from packaged M1 windows and local anomaly output. It does not call THIRD_MODEL_SOURCE_BEST_ROOT.",
    }
    write_json(config.SOURCE_RETRAIN_METADATA_PATH, payload)
    return payload
