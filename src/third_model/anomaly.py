from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from . import config
from .common import binary_metrics, model_matrix, read_json, split_masks, write_json


def _load_feature_columns() -> list[str]:
    if not config.FEATURE_COLUMNS_PATH.exists():
        if config.SOURCE_ANOMALY_METADATA_PATH.exists():
            metadata = read_json(config.SOURCE_ANOMALY_METADATA_PATH)
            return list(metadata["feature_columns"])
        raise FileNotFoundError("No anomaly feature metadata is available.")
    table = pd.read_csv(config.FEATURE_COLUMNS_PATH)
    column = "column_name" if "column_name" in table.columns else "feature_name" if "feature_name" in table.columns else table.columns[0]
    return table[column].astype(str).tolist()


def _criticality_counter(frame: pd.DataFrame, score_column: str, output_column: str) -> pd.Series:
    working = frame[[*config.KEY_COLUMNS, score_column]].copy()
    working["window_end"] = pd.to_datetime(working["window_end"], errors="coerce")
    working["_original_index"] = working.index
    working = working.sort_values(["manufacturer", "substation_id", "window_end", "window_start"])
    values = pd.Series(0, index=working.index, dtype="int64")
    for _, group in working.groupby(["manufacturer", "substation_id"], dropna=False, sort=False):
        count = 0
        for idx, row in group.iterrows():
            if float(row[score_column]) >= 1.0:
                count += 1
            else:
                count = max(0, count - 1)
            values.loc[idx] = count
    values.index = working["_original_index"]
    return values.reindex(frame.index).rename(output_column)


def train_score_anomaly() -> pd.DataFrame:
    config.ensure_dirs()
    if not config.TRAINABLE_WINDOWS_PATH.exists():
        raise FileNotFoundError("Run import_canonical_windows first.")
    windows = pd.read_csv(config.TRAINABLE_WINDOWS_PATH)
    features = _load_feature_columns()
    x_all = model_matrix(windows, features)
    train_normal = windows[config.ANOMALY_SPLIT_COLUMN].eq("train") & windows["label"].eq("normal")
    if int(train_normal.sum()) == 0:
        raise ValueError("No train-normal rows are available for anomaly model fitting.")

    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_all.loc[train_normal].to_numpy())
    x_scaled = scaler.transform(x_all.to_numpy())

    iforest = IsolationForest(
        n_estimators=300,
        contamination="auto",
        random_state=config.RANDOM_STATE,
        n_jobs=-1,
    )
    iforest.fit(x_train)
    iforest_score = -iforest.score_samples(x_scaled)

    covariance = LedoitWolf().fit(x_scaled[train_normal.to_numpy()])
    mahalanobis_score = covariance.mahalanobis(x_scaled)

    iforest_threshold = float(np.quantile(iforest_score[train_normal.to_numpy()], config.ANOMALY_THRESHOLD_QUANTILE))
    mahalanobis_threshold = float(np.quantile(mahalanobis_score[train_normal.to_numpy()], config.ANOMALY_THRESHOLD_QUANTILE))

    scored = windows[[c for c in windows.columns if c not in features]].copy()
    scored["iforest_anomaly_score"] = iforest_score
    scored["mahalanobis_score"] = mahalanobis_score
    scored["iforest_threshold"] = iforest_threshold
    scored["mahalanobis_threshold"] = mahalanobis_threshold
    scored["iforest_score_ratio"] = scored["iforest_anomaly_score"] / iforest_threshold
    scored["mahalanobis_score_ratio"] = scored["mahalanobis_score"] / mahalanobis_threshold
    scored["iforest_q99_label"] = scored["iforest_score_ratio"].ge(1.0).astype("int8")
    scored["mahalanobis_q99_label"] = scored["mahalanobis_score_ratio"].ge(1.0).astype("int8")
    scored["iforest_anomaly_label"] = scored["iforest_score_ratio"].ge(
        config.ANOMALY_IFOREST_POLICY_THRESHOLD
    ).astype("int8")
    scored["mahalanobis_anomaly_label"] = scored["mahalanobis_score_ratio"].ge(
        config.ANOMALY_MAHALANOBIS_POLICY_THRESHOLD
    ).astype("int8")
    scored["anomaly_consensus_count"] = (
        scored["iforest_anomaly_label"] + scored["mahalanobis_anomaly_label"]
    ).astype("int8")
    scored["anomaly_ensemble_score"] = (
        config.ANOMALY_WEIGHTS["iforest"] * scored["iforest_score_ratio"]
        + config.ANOMALY_WEIGHTS["mahalanobis"] * scored["mahalanobis_score_ratio"]
    )
    scored["anomaly_policy_score"] = np.minimum(
        scored["iforest_score_ratio"] / config.ANOMALY_IFOREST_POLICY_THRESHOLD,
        scored["mahalanobis_score_ratio"] / config.ANOMALY_MAHALANOBIS_POLICY_THRESHOLD,
    )
    scored["anomaly_score"] = scored["anomaly_policy_score"]
    scored["anomaly_label"] = scored["anomaly_consensus_count"].ge(2).astype("int8")
    scored["strong_anomaly_label"] = (
        scored["iforest_q99_label"].eq(1) & scored["mahalanobis_q99_label"].eq(1)
    ).astype("int8")
    scored["anomaly_criticality"] = _criticality_counter(scored, "anomaly_policy_score", "anomaly_criticality")
    scored["anomaly_event_label"] = scored["anomaly_criticality"].ge(config.CRITICALITY_THRESHOLD).astype("int8")

    metric_rows: list[dict[str, object]] = []
    methods = {
        "iforest_policy": ("iforest_score_ratio", "iforest_anomaly_label"),
        "mahalanobis_policy": ("mahalanobis_score_ratio", "mahalanobis_anomaly_label"),
        "policy_and_point": ("anomaly_policy_score", "anomaly_label"),
        "strong_q99_and_point": ("anomaly_policy_score", "strong_anomaly_label"),
        "policy_and_criticality": ("anomaly_policy_score", "anomaly_event_label"),
    }
    for split, mask in split_masks(scored, config.ANOMALY_SPLIT_COLUMN).items():
        part = scored.loc[mask].copy()
        if part.empty:
            continue
        for method, (score_col, pred_col) in methods.items():
            metric_rows.append(binary_metrics(part, score_col, pred_col, split, method))

    scored.to_csv(config.ANOMALY_SCORES_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(metric_rows).to_csv(config.ANOMALY_METRICS_PATH, index=False, encoding="utf-8-sig")
    joblib.dump(scaler, config.ANOMALY_SCALER_PATH)
    joblib.dump(iforest, config.IFOREST_MODEL_PATH)
    joblib.dump(covariance, config.MAHALANOBIS_MODEL_PATH)
    write_json(
        config.ANOMALY_METADATA_PATH,
        {
            "source": "current best anomaly design",
            "model_version": "3rd_model_m1_iforest_mahalanobis_no_ae_v1",
            "scope": config.PROJECT_SCOPE,
            "manufacturer_filter": config.M1_MANUFACTURER,
            "feature_count": len(features),
            "feature_columns": features,
            "threshold_quantile": config.ANOMALY_THRESHOLD_QUANTILE,
            "iforest_threshold": iforest_threshold,
            "mahalanobis_threshold": mahalanobis_threshold,
            "active_policy_name": config.ANOMALY_POLICY_NAME,
            "iforest_policy_ratio_threshold": config.ANOMALY_IFOREST_POLICY_THRESHOLD,
            "mahalanobis_policy_ratio_threshold": config.ANOMALY_MAHALANOBIS_POLICY_THRESHOLD,
            "anomaly_policy_score_formula": "min(iforest_score_ratio / 0.90, mahalanobis_score_ratio / 1.00)",
            "active_anomaly_label": "iforest_score_ratio >= 0.90 AND mahalanobis_score_ratio >= 1.00",
            "active_criticality_score": "anomaly_policy_score",
            "criticality_threshold": config.CRITICALITY_THRESHOLD,
            "ae_branch": "excluded from operational path",
        },
    )
    return scored
