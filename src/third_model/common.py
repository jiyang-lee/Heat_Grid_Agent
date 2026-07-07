from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from . import config


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def load_imputation_values() -> dict[str, float]:
    path = config.IMPUTATION_VALUES_PATH
    if not path.exists():
        return {}
    table = pd.read_csv(path)
    if "column_name" not in table.columns or "imputation_value" not in table.columns:
        return {}
    values: dict[str, float] = {}
    for row in table.itertuples(index=False):
        raw = getattr(row, "imputation_value")
        try:
            values[str(row.column_name)] = float(raw)
        except (TypeError, ValueError):
            values[str(row.column_name)] = 0.0
    return values


def model_matrix(
    frame: pd.DataFrame,
    feature_columns: list[str],
    imputation_values: dict[str, float] | None = None,
    fill_value: float = 0.0,
) -> pd.DataFrame:
    values = imputation_values or load_imputation_values()
    result = frame.copy()
    for column in feature_columns:
        if column not in result.columns:
            result[column] = values.get(column, fill_value)
    x = result[feature_columns].copy()
    for column in x.columns:
        if x[column].dtype == "bool":
            x[column] = x[column].astype("int8")
        x[column] = pd.to_numeric(x[column], errors="coerce")
    fill_map = {column: values.get(column, fill_value) for column in feature_columns}
    return x.fillna(fill_map).fillna(fill_value).astype("float64")


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def safe_roc_auc(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique(dropna=True) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def safe_average_precision(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique(dropna=True) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def binary_metrics(
    frame: pd.DataFrame,
    score_column: str,
    prediction_column: str,
    split_name: str,
    method: str,
) -> dict[str, object]:
    y_true = frame["label"].eq("pre_fault").astype(int)
    y_score = pd.to_numeric(frame[score_column], errors="coerce").fillna(0.0)
    y_pred = pd.to_numeric(frame[prediction_column], errors="coerce").fillna(0).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    return {
        "method": method,
        "split": split_name,
        "row_count": int(len(frame)),
        "normal_count": int((y_true == 0).sum()),
        "pre_fault_count": int((y_true == 1).sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "roc_auc": safe_roc_auc(y_true, y_score),
        "average_precision": safe_average_precision(y_true, y_score),
    }


def split_masks(frame: pd.DataFrame, split_column: str) -> dict[str, pd.Series]:
    if split_column not in frame.columns:
        return {"all": pd.Series(True, index=frame.index)}
    return {
        "train": frame[split_column].eq("train"),
        "validation": frame[split_column].eq("validation"),
        "holdout": frame[split_column].eq("holdout"),
    }


def rolling_slope(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).to_numpy(dtype="float64")
    if len(numeric) < 2:
        return 0.0
    x = np.arange(len(numeric), dtype="float64")
    try:
        return float(np.polyfit(x, numeric, 1)[0])
    except Exception:
        return 0.0


def _sorted_time_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    result["window_end"] = pd.to_datetime(result["window_end"], errors="coerce")
    result["_original_index"] = result.index
    return result.sort_values(["manufacturer", "substation_id", "window_end", "window_start"]).copy()


def add_causal_lag_features(frame: pd.DataFrame, source_columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    result = _sorted_time_frame(frame)
    created: list[str] = []
    group_keys = ["manufacturer", "substation_id"]
    for source in source_columns:
        if source not in result.columns:
            result[source] = 0.0
        numeric = pd.to_numeric(result[source], errors="coerce").fillna(0.0)
        result[source] = numeric
        for suffix, series in {
            "__lag1": result.groupby(group_keys, dropna=False)[source].shift(1),
            "__lag2": result.groupby(group_keys, dropna=False)[source].shift(2),
        }.items():
            column = f"{source}{suffix}"
            result[column] = series.fillna(0.0)
            created.append(column)
        delta_col = f"{source}__delta1"
        result[delta_col] = (result[source] - result[f"{source}__lag1"]).fillna(0.0)
        created.append(delta_col)
        roll_col = f"{source}__roll3_mean"
        result[roll_col] = (
            result.groupby(group_keys, dropna=False)[source]
            .shift(1)
            .groupby([result["manufacturer"], result["substation_id"]], dropna=False)
            .rolling(3, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
            .fillna(0.0)
        )
        created.append(roll_col)
    result = result.sort_values("_original_index").drop(columns=["_original_index"])
    return result, created


def add_sensor_horizon_features(frame: pd.DataFrame, source_columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    result = _sorted_time_frame(frame)
    created: list[str] = []
    group_keys = ["manufacturer", "substation_id"]
    horizons = {"24h": 4, "3d": 12, "7d": 28}
    for source in source_columns:
        if source not in result.columns:
            result[source] = 0.0
        result[source] = pd.to_numeric(result[source], errors="coerce").fillna(0.0)
        shifted = result.groupby(group_keys, dropna=False)[source].shift(1)
        for label, rows in horizons.items():
            mean_col = f"{source}__roll{label}_mean"
            delta_col = f"{source}__roll{label}_delta"
            slope_col = f"{source}__roll{label}_slope"
            rolled = (
                shifted.groupby([result["manufacturer"], result["substation_id"]], dropna=False)
                .rolling(rows, min_periods=1)
                .mean()
                .reset_index(level=[0, 1], drop=True)
            )
            result[mean_col] = rolled.fillna(0.0)
            result[delta_col] = (result[source] - result[mean_col]).fillna(0.0)
            result[slope_col] = (
                shifted.groupby([result["manufacturer"], result["substation_id"]], dropna=False)
                .rolling(rows, min_periods=2)
                .apply(rolling_slope, raw=False)
                .reset_index(level=[0, 1], drop=True)
                .fillna(0.0)
            )
            created.extend([mean_col, delta_col, slope_col])
    result = result.sort_values("_original_index").drop(columns=["_original_index"])
    return result, created
