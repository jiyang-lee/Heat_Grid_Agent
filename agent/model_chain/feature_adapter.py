"""Feature adapter from preprocessed windows to handoff model feature matrices."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from agent.io import paths


@dataclass(frozen=True)
class FeatureMatrix:
    frame: pd.DataFrame
    report: dict[str, object]


def load_feature_list(metadata_path: Path, key: str) -> list[str]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return list(metadata[key])


def build_feature_matrix(
    preprocessed: pd.DataFrame,
    feature_names: list[str],
    *,
    extra_columns: pd.DataFrame | None = None,
) -> FeatureMatrix:
    """Return model feature matrix in the requested order plus coverage report."""

    source = preprocessed.copy()
    if extra_columns is not None:
        source = _merge_extra_columns(source, extra_columns)
    source = _add_time_features(source)
    source = _add_timeflow_features(source, feature_names)

    normalized_columns = {_normalize_name(column): column for column in source.columns}
    matrix_columns: dict[str, pd.Series | float] = {}
    exact = 0
    one_hot = 0
    missing: list[str] = []

    for feature in feature_names:
        if feature in source.columns:
            matrix_columns[feature] = _to_numeric(source[feature])
            exact += 1
            continue

        normalized = _normalize_name(feature)
        if normalized in normalized_columns:
            matrix_columns[feature] = _to_numeric(source[normalized_columns[normalized]])
            exact += 1
            continue

        derived = _one_hot_feature(source, feature, normalized_columns)
        if derived is not None:
            matrix_columns[feature] = derived
            one_hot += 1
            continue

        matrix_columns[feature] = 0.0
        missing.append(feature)

    matrix = pd.DataFrame(matrix_columns, index=source.index)
    matrix = matrix.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    return FeatureMatrix(
        frame=matrix[feature_names],
        report={
            "requested_features": len(feature_names),
            "exact_or_alias_matches": exact,
            "derived_one_hot_matches": one_hot,
            "filled_zero_features": len(missing),
            "filled_zero_feature_names": missing,
        },
    )


def _merge_extra_columns(source: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    keys = ["substation_id", "window_start", "window_end"]
    if "source_file" in source.columns and "source_file" in extra.columns:
        keys.insert(0, "source_file")
    elif "manufacturer" in source.columns and "manufacturer" in extra.columns:
        keys.insert(0, "manufacturer")
    available = [key for key in keys if key in source.columns and key in extra.columns]
    if len(available) != len(keys):
        return source
    extra_columns = [
        column
        for column in extra.columns
        if column not in source.columns or column in available
    ]
    result = source.merge(extra[extra_columns], on=available, how="left")
    return result


def _add_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    window_start = pd.to_datetime(result["window_start"], errors="coerce", utc=True)
    result["hour_of_day"] = window_start.dt.hour.fillna(0).astype(int)
    result["day_of_week"] = window_start.dt.dayofweek.fillna(0).astype(int)
    result["day_of_year"] = window_start.dt.dayofyear.fillna(1).astype(int)
    result["month"] = window_start.dt.month.fillna(1).astype(int)
    result["is_weekend"] = result["day_of_week"].isin([5, 6]).astype(int)
    result["is_heating_season"] = result["month"].isin([10, 11, 12, 1, 2, 3, 4]).astype(int)
    result["hour_sin"] = np.sin(2 * math.pi * result["hour_of_day"] / 24)
    result["hour_cos"] = np.cos(2 * math.pi * result["hour_of_day"] / 24)
    result["dow_sin"] = np.sin(2 * math.pi * result["day_of_week"] / 7)
    result["dow_cos"] = np.cos(2 * math.pi * result["day_of_week"] / 7)
    result["doy_sin"] = np.sin(2 * math.pi * result["day_of_year"] / 366)
    result["doy_cos"] = np.cos(2 * math.pi * result["day_of_year"] / 366)
    return result


def _add_timeflow_features(frame: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    result = frame.copy()
    result["_sort_ts"] = pd.to_datetime(result["window_start"], errors="coerce", utc=True)
    group_keys = [key for key in ["manufacturer", "substation_id"] if key in result.columns]
    if not group_keys:
        group_keys = ["substation_id"]
    result = result.sort_values(group_keys + ["_sort_ts"]).reset_index(drop=True)

    for feature in feature_names:
        suffix = None
        for candidate in ["__lag1", "__delta1", "__lag2", "__roll3_mean"]:
            if feature.endswith(candidate):
                suffix = candidate
                break
        if suffix is None or feature in result.columns:
            continue
        base = feature[: -len(suffix)]
        source_column = _find_column(result, base)
        if source_column is None:
            continue
        values = _to_numeric(result[source_column])
        grouped = values.groupby([result[key] for key in group_keys], dropna=False)
        if suffix == "__lag1":
            result[feature] = grouped.shift(1)
        elif suffix == "__lag2":
            result[feature] = grouped.shift(2)
        elif suffix == "__delta1":
            result[feature] = values - grouped.shift(1)
        elif suffix == "__roll3_mean":
            result[feature] = grouped.transform(lambda s: s.rolling(3, min_periods=1).mean())
    return result.drop(columns=["_sort_ts"])


def _one_hot_feature(
    source: pd.DataFrame,
    feature: str,
    normalized_columns: dict[str, str],
) -> pd.Series | None:
    if "__is__" not in feature:
        return None
    source_name, expected = feature.split("__is__", 1)
    column = _find_column_by_normalized(source_name, normalized_columns)
    if column is None:
        return None
    observed = source[column].astype("string").fillna("missing").str.lower()
    expected_norm = expected.replace("_", " ").lower()
    observed_norm = observed.str.replace("_", " ", regex=False).str.replace("-", " ", regex=False)
    return observed_norm.eq(expected_norm).astype(float)


def _find_column(frame: pd.DataFrame, name: str) -> str | None:
    if name in frame.columns:
        return name
    normalized = _normalize_name(name)
    for column in frame.columns:
        if _normalize_name(column) == normalized:
            return column
    return None


def _find_column_by_normalized(name: str, normalized_columns: dict[str, str]) -> str | None:
    return normalized_columns.get(_normalize_name(name))


def _normalize_name(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("3-way", "3way")
    return re.sub(r"_+", "_", re.sub(r"[^0-9a-z]+", "_", value)).strip("_")


def _to_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    return pd.to_numeric(series, errors="coerce")


def write_feature_report(report: dict[str, object], output_path: Path = paths.MODEL_CHAIN_FEATURE_REPORT_JSON) -> Path:
    paths.ensure_dir(output_path.parent)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path
