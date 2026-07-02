from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from heatgrid_inference.constants import (
    CONTROL_CONTEXT_PATTERN,
    CORE_SENSOR_COLUMNS,
    CUMULATIVE_COLUMNS,
    DERIVED_PAIRS,
    EVENT_CONTEXT_SENTINEL_DAYS,
    FLOW_COLUMNS,
    HEATING_SEASON_MONTHS,
    MAX_MISSING_RATE,
    MIN_ROW_RATIO,
    POWER_COLUMNS,
    TEMPERATURE_COLUMNS,
    WINDOW_FREQ,
    WINDOW_SIZE,
)


def read_predist_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";", low_memory=False)


def extract_substation_id(path: Path) -> int:
    match = re.search(r"substation_(\d+)\.csv$", path.name)
    if not match:
        raise ValueError(f"Cannot extract substation id from: {path.name}")
    return int(match.group(1))


def infer_manufacturer_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("manufacturer "):
            return part
    raise ValueError(f"Cannot infer manufacturer from path: {path}")


def parse_datetime_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_datetime(result[column], errors="coerce")
    return result


def load_configuration_table(raw_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(raw_root.glob("manufacturer */configuration_types.csv")):
        manufacturer = path.parent.name
        df = read_predist_csv(path).rename(columns={"substation ID": "substation_id"})
        df["manufacturer"] = manufacturer
        frames.append(df[["manufacturer", "substation_id", "configuration_type"]])

    if not frames:
        return pd.DataFrame(
            columns=[
                "manufacturer",
                "substation_id",
                "configuration_type",
                "has_dhw",
                "has_buffer_tank",
            ]
        )

    result = pd.concat(frames, ignore_index=True)
    result["substation_id"] = pd.to_numeric(result["substation_id"], errors="coerce").astype("Int64")
    result["configuration_type"] = result["configuration_type"].fillna("missing")
    result["has_dhw"] = result["configuration_type"].str.contains("DHW", case=False, na=False)
    result["has_buffer_tank"] = result["configuration_type"].str.contains("buffer", case=False, na=False)
    return result


def load_event_history(raw_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for fault_path in sorted(raw_root.glob("manufacturer */faults.csv")):
        manufacturer = fault_path.parent.name
        faults = read_predist_csv(fault_path).rename(
            columns={"substation ID": "substation_id", "Report date": "event_time"}
        )
        if {"substation_id", "event_time"}.issubset(faults.columns):
            faults = faults[["substation_id", "event_time"]].copy()
            faults["manufacturer"] = manufacturer
            faults["event_type"] = "fault"
            frames.append(faults)

    for task_path in sorted(raw_root.glob("manufacturer */disturbances.csv")):
        manufacturer = task_path.parent.name
        tasks = read_predist_csv(task_path).rename(
            columns={"substation ID": "substation_id", "Event start": "event_time"}
        )
        if {"substation_id", "event_time"}.issubset(tasks.columns):
            tasks = tasks[["substation_id", "event_time"]].copy()
            tasks["manufacturer"] = manufacturer
            tasks["event_type"] = "task"
            frames.append(tasks)

    if not frames:
        return pd.DataFrame(columns=["manufacturer", "substation_id", "event_time", "event_type"])

    result = pd.concat(frames, ignore_index=True)
    result["substation_id"] = pd.to_numeric(result["substation_id"], errors="coerce").astype("Int64")
    result["event_time"] = pd.to_datetime(result["event_time"], errors="coerce")
    return result.dropna(subset=["event_time", "substation_id"])


def season_bucket_from_month(month: int) -> str:
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "autumn"


def add_time_context_features(result: pd.DataFrame) -> pd.DataFrame:
    if result.empty:
        return result

    window_mid = result["window_start"] + (WINDOW_SIZE / 2)
    hour_of_day = window_mid.dt.hour + (window_mid.dt.minute / 60.0)
    day_of_week = window_mid.dt.dayofweek.astype("int64")
    day_of_year = window_mid.dt.dayofyear.astype("int64")
    month = window_mid.dt.month.astype("int64")

    time_features = pd.DataFrame(
        {
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "day_of_year": day_of_year,
            "month": month,
            "is_weekend": day_of_week.isin([5, 6]),
            "is_heating_season": month.isin(sorted(HEATING_SEASON_MONTHS)),
            "season_bucket": month.map(season_bucket_from_month),
            "hour_sin": np.sin(2 * np.pi * hour_of_day / 24.0),
            "hour_cos": np.cos(2 * np.pi * hour_of_day / 24.0),
            "dow_sin": np.sin(2 * np.pi * day_of_week / 7.0),
            "dow_cos": np.cos(2 * np.pi * day_of_week / 7.0),
            "doy_sin": np.sin(2 * np.pi * day_of_year / 366.0),
            "doy_cos": np.cos(2 * np.pi * day_of_year / 366.0),
        },
        index=result.index,
    )
    return pd.concat([result, time_features], axis=1)


def prepare_operational_frame(path: Path) -> tuple[pd.DataFrame, list[str], list[str], int]:
    df = read_predist_csv(path)
    if "timestamp" not in df.columns:
        raise ValueError(f"Missing timestamp column: {path}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    invalid_timestamp_rows = int(df["timestamp"].isna().sum())
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

    numeric_columns = [column for column in CORE_SENSOR_COLUMNS if column in df.columns]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    context_columns = [
        column
        for column in df.columns
        if column != "timestamp" and CONTROL_CONTEXT_PATTERN.search(column)
    ]
    for column in context_columns:
        df[column] = df[column].astype("string").fillna("missing")

    return df, numeric_columns, context_columns, invalid_timestamp_rows


def estimate_expected_rows(df: pd.DataFrame) -> tuple[int, float]:
    diffs = df["timestamp"].diff().dropna()
    if diffs.empty:
        return 1, np.nan
    median_interval = diffs.median()
    if pd.isna(median_interval) or median_interval <= pd.Timedelta(0):
        return 1, np.nan
    expected_rows = max(1, int(math.ceil(WINDOW_SIZE / median_interval)))
    return expected_rows, median_interval.total_seconds() / 60


def summarize_top_sensors(values: dict[str, float], limit: int = 5) -> str:
    valid_items = [(key, value) for key, value in values.items() if pd.notna(value) and value > 0]
    valid_items = sorted(valid_items, key=lambda item: item[1], reverse=True)
    return "|".join(key for key, _ in valid_items[:limit])


def add_sensor_error_count(df: pd.DataFrame, filled: pd.DataFrame, numeric_columns: list[str]) -> pd.Series:
    error_count = pd.Series(0, index=df.index, dtype="int64")
    for column in TEMPERATURE_COLUMNS:
        if column in numeric_columns:
            error_count += ((filled[column] < -50) | (filled[column] > 150)).astype("int64")
    for column in FLOW_COLUMNS + POWER_COLUMNS:
        if column in numeric_columns:
            error_count += (filled[column] < 0).astype("int64")
    for column in CUMULATIVE_COLUMNS:
        if column in numeric_columns:
            error_count += (filled[column].groupby(df["window_start"]).diff() < 0).astype("int64")
    return error_count.groupby(df["window_start"]).sum()


def add_extreme_change_count(df: pd.DataFrame, filled: pd.DataFrame, numeric_columns: list[str]) -> pd.Series:
    total_extreme = pd.Series(0, index=df.index, dtype="int64")
    for column in numeric_columns:
        diff = filled[column].groupby(df["window_start"]).diff().abs()
        baseline = diff.groupby(df["window_start"]).transform("median")
        extreme = (baseline > 0) & (diff > baseline * 10)
        total_extreme += extreme.fillna(False).astype("int64")
    return total_extreme.groupby(df["window_start"]).sum()


def summarize_context_mode(series: pd.Series) -> str:
    modes = series.mode(dropna=False)
    if modes.empty:
        return "missing"
    return str(modes.iloc[0])


def latest_past_event_days(events: pd.DataFrame, event_type: str, window_start: pd.Timestamp) -> float:
    if events.empty or pd.isna(window_start):
        return EVENT_CONTEXT_SENTINEL_DAYS
    event_times = events.loc[events["event_type"].eq(event_type), "event_time"]
    earlier_events = event_times.loc[event_times < window_start]
    if earlier_events.empty:
        return EVENT_CONTEXT_SENTINEL_DAYS
    latest_event = earlier_events.max()
    return float((window_start - latest_event).total_seconds() / 86400.0)


def attach_configuration(windows: pd.DataFrame, configuration_table: pd.DataFrame | None) -> pd.DataFrame:
    if windows.empty:
        return windows
    result = windows.copy()
    if configuration_table is not None and not configuration_table.empty:
        result = result.merge(
            configuration_table,
            on=["manufacturer", "substation_id"],
            how="left",
        )
    for column, default in {
        "configuration_type": "missing",
        "has_dhw": False,
        "has_buffer_tank": False,
    }.items():
        if column not in result.columns:
            result[column] = default
    result["configuration_type"] = result["configuration_type"].fillna("missing")
    result["normal_reference_group"] = (
        result["manufacturer"].fillna("missing")
        + "|"
        + result["configuration_type"].fillna("missing")
        + "|"
        + result["season_bucket"].fillna("missing")
    )
    return result


def attach_event_context(windows: pd.DataFrame, event_history: pd.DataFrame | None) -> pd.DataFrame:
    if windows.empty:
        return windows
    result = windows.copy()
    if event_history is None or event_history.empty:
        relevant = pd.DataFrame(columns=["event_time", "event_type"])
    else:
        relevant = event_history.loc[
            event_history["manufacturer"].eq(result["manufacturer"].iloc[0])
            & event_history["substation_id"].astype("Int64").eq(int(result["substation_id"].iloc[0]))
        ].copy()

    rows: list[dict] = []
    for row in result.itertuples(index=False):
        fault_days = latest_past_event_days(relevant, "fault", row.window_start)
        task_days = latest_past_event_days(relevant, "task", row.window_start)
        any_days = min(fault_days, task_days)
        rows.append(
            {
                "days_since_last_fault_event": fault_days,
                "days_since_last_task_event": task_days,
                "days_since_last_any_event": any_days,
                "maintenance_related": False,
                "disturbance_count": 0,
            }
        )
    return pd.concat([result.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def build_window_features_from_file(
    path: Path,
    configuration_table: pd.DataFrame | None = None,
    event_history: pd.DataFrame | None = None,
    manufacturer: str | None = None,
    substation_id: int | None = None,
) -> pd.DataFrame:
    path = Path(path)
    manufacturer = manufacturer or infer_manufacturer_from_path(path)
    substation_id = substation_id if substation_id is not None else extract_substation_id(path)
    df, numeric_columns, context_columns, invalid_timestamp_rows = prepare_operational_frame(path)
    if df.empty or not numeric_columns:
        return pd.DataFrame()

    expected_rows, median_interval_minutes = estimate_expected_rows(df)
    df["window_start"] = df["timestamp"].dt.floor(WINDOW_FREQ)
    grouped = df.groupby("window_start", sort=True)

    result = pd.DataFrame(index=grouped.size().index)
    result["manufacturer"] = manufacturer
    result["substation_id"] = int(substation_id)
    result["source_file"] = path.name
    result["window_start"] = result.index
    result["window_end"] = result["window_start"] + WINDOW_SIZE
    result["row_count"] = grouped.size().astype("int64")
    result["expected_row_count"] = int(expected_rows)
    result["median_interval_minutes"] = median_interval_minutes
    result["invalid_timestamp_rows_in_file"] = invalid_timestamp_rows

    timestamp_diffs = df.groupby("window_start")["timestamp"].diff()
    timestamp_gap_minutes = timestamp_diffs.dt.total_seconds() / 60
    if pd.notna(median_interval_minutes):
        result["timestamp_gap_count"] = (
            (timestamp_gap_minutes > median_interval_minutes * 1.5)
            .groupby(df["window_start"])
            .sum()
            .reindex(result.index, fill_value=0)
            .astype("int64")
        )
    else:
        result["timestamp_gap_count"] = 0
    result["max_timestamp_gap_minutes"] = (
        timestamp_gap_minutes.groupby(df["window_start"]).max().reindex(result.index).fillna(0)
    )

    raw_numeric = df[numeric_columns]
    filled = raw_numeric.groupby(df["window_start"]).ffill()
    filled = filled.groupby(df["window_start"]).bfill()
    window_medians = raw_numeric.groupby(df["window_start"]).transform("median")
    filled = filled.fillna(window_medians)
    missing_mask = raw_numeric.isna()

    result["missing_count"] = (
        missing_mask.sum(axis=1).groupby(df["window_start"]).sum().reindex(result.index, fill_value=0).astype("int64")
    )
    total_values = result["row_count"] * len(numeric_columns)
    result["missing_rate"] = result["missing_count"] / total_values.replace(0, np.nan)
    result["sensor_error_candidate_count"] = (
        add_sensor_error_count(df, filled, numeric_columns).reindex(result.index, fill_value=0).astype("int64")
    )
    result["extreme_change_count"] = (
        add_extreme_change_count(df, filled, numeric_columns).reindex(result.index, fill_value=0).astype("int64")
    )

    missing_sum = missing_mask.groupby(df["window_start"]).sum().reindex(result.index, fill_value=0)
    missing_rate = missing_mask.groupby(df["window_start"]).mean().reindex(result.index, fill_value=0)

    engineered_columns: dict[str, pd.Series] = {}

    for column in numeric_columns:
        stats = filled[column].groupby(df["window_start"]).agg(["mean", "min", "max", "std", "first", "last"])
        stats = stats.reindex(result.index)
        engineered_columns[f"{column}__mean"] = stats["mean"]
        engineered_columns[f"{column}__min"] = stats["min"]
        engineered_columns[f"{column}__max"] = stats["max"]
        engineered_columns[f"{column}__std"] = stats["std"]
        engineered_columns[f"{column}__first"] = stats["first"]
        engineered_columns[f"{column}__last"] = stats["last"]
        engineered_columns[f"{column}__delta"] = stats["last"] - stats["first"]
        engineered_columns[f"{column}__missing_count"] = missing_sum[column].astype("int64")
        engineered_columns[f"{column}__missing_rate"] = missing_rate[column]

    for feature_name, (left_column, right_column) in DERIVED_PAIRS.items():
        if left_column in filled.columns and right_column in filled.columns:
            diff = filled[left_column] - filled[right_column]
            diff_grouped = diff.groupby(df["window_start"])
            engineered_columns[f"{feature_name}__mean"] = diff_grouped.mean().reindex(result.index)
            engineered_columns[f"{feature_name}__max_abs"] = diff.abs().groupby(df["window_start"]).max().reindex(result.index)
            engineered_columns[f"{feature_name}__last"] = diff_grouped.last().reindex(result.index)

    for column in context_columns:
        grouped_context = df.groupby("window_start")[column]
        engineered_columns[f"{column}__dominant"] = (
            grouped_context.agg(summarize_context_mode).reindex(result.index).fillna("missing")
        )
        engineered_columns[f"{column}__nunique"] = (
            grouped_context.nunique(dropna=False).reindex(result.index, fill_value=0).astype("int64")
        )
        engineered_columns[f"{column}__change_count"] = (
            df[column]
            .ne(df.groupby("window_start")[column].shift())
            .groupby(df["window_start"])
            .sum()
            .sub(1)
            .clip(lower=0)
            .reindex(result.index, fill_value=0)
            .astype("int64")
        )

    if engineered_columns:
        result = pd.concat([result, pd.DataFrame(engineered_columns, index=result.index)], axis=1)

    result["main_missing_sensors"] = missing_sum.apply(lambda row: summarize_top_sensors(row.to_dict()), axis=1)
    delta_values = pd.DataFrame(
        {column: result[f"{column}__delta"].abs() for column in numeric_columns if f"{column}__delta" in result.columns}
    )
    result["main_changed_sensors"] = delta_values.apply(lambda row: summarize_top_sensors(row.to_dict()), axis=1)
    result["data_quality_issue"] = (
        (result["row_count"] < expected_rows * MIN_ROW_RATIO)
        | (result["missing_rate"] > MAX_MISSING_RATE)
        | (result["sensor_error_candidate_count"] > 0)
    )

    result = add_time_context_features(result)
    result = attach_configuration(result.reset_index(drop=True), configuration_table)
    result = attach_event_context(result, event_history)
    return result.reset_index(drop=True)


def build_window_features_from_raw_root(raw_root: Path) -> pd.DataFrame:
    raw_root = Path(raw_root)
    configuration_table = load_configuration_table(raw_root)
    event_history = load_event_history(raw_root)
    frames = [
        build_window_features_from_file(path, configuration_table, event_history)
        for path in sorted(raw_root.glob("manufacturer */operational_data/substation_*.csv"))
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
