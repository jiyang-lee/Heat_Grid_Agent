"""Build preprocessed window rows from raw operational tables."""

from __future__ import annotations

import math

import pandas as pd

from agent.preprocessing.contracts import (
    CONTROL_STATUS_COLUMNS,
    CUMULATIVE_COLUMNS,
    FLOW_OR_POWER_COLUMNS,
    MAX_MISSING_RATE,
    MIN_ROW_RATIO,
    NUMERIC_SENSOR_COLUMNS,
    PREPROCESSING_VERSION,
    STABILIZATION_DAYS,
    TEMPERATURE_COLUMNS,
    WINDOW_SIZE,
    schema_columns,
)
from agent.preprocessing.validate import validate_preprocessed_columns, validate_raw_inputs


def build_preprocessed_windows(
    substations: pd.DataFrame,
    sensor_readings: pd.DataFrame,
    fault_events: pd.DataFrame,
    maintenance_events: pd.DataFrame,
    *,
    window_size: str = WINDOW_SIZE,
) -> pd.DataFrame:
    """Return contract-ordered preprocessed window rows.

    The function is fail-soft after required key validation: missing optional
    sensor/context values become null or "missing" instead of stopping the batch.
    """

    validate_raw_inputs(substations, sensor_readings, fault_events, maintenance_events)
    sensors = _normalize_sensor_readings(sensor_readings)
    if sensors.empty:
        return _empty_output()

    window_delta = pd.Timedelta(window_size)
    event_context = _prepare_event_context(fault_events, maintenance_events)
    config = _prepare_substations(substations)

    frames = []
    for substation_id, group in sensors.groupby("substation_id", dropna=False):
        if pd.isna(substation_id) or group.empty:
            continue
        substation_windows = _build_substation_windows(
            int(substation_id),
            group.copy(),
            window_delta,
            event_context,
            config,
        )
        if not substation_windows.empty:
            frames.append(substation_windows)

    if not frames:
        return _empty_output()

    result = pd.concat(frames, ignore_index=True)
    result = _order_and_fill_contract_columns(result)
    validate_preprocessed_columns(result)
    return result


def _normalize_sensor_readings(sensor_readings: pd.DataFrame) -> pd.DataFrame:
    result = sensor_readings.copy()
    result["ts"] = pd.to_datetime(result["ts"], errors="coerce", utc=True)
    result["_invalid_ts"] = result["ts"].isna()
    invalid_counts = result.groupby("substation_id", dropna=False)["_invalid_ts"].sum()
    result = result.dropna(subset=["substation_id", "ts"]).sort_values(["substation_id", "ts"])
    result = result.drop_duplicates(subset=["substation_id", "ts"], keep="last").reset_index(drop=True)
    result["_invalid_ts_count"] = result["substation_id"].map(invalid_counts).fillna(0).astype("int64")

    for column in NUMERIC_SENSOR_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")

    for column in CONTROL_STATUS_COLUMNS:
        if column not in result.columns:
            result[column] = "missing"
        result[column] = result[column].astype("string").fillna("missing")

    if "source_file" not in result.columns:
        result["source_file"] = pd.NA
    return result


def _build_substation_windows(
    substation_id: int,
    group: pd.DataFrame,
    window_delta: pd.Timedelta,
    event_context: dict[str, pd.DataFrame],
    config: pd.DataFrame,
) -> pd.DataFrame:
    group = group.sort_values("ts").copy()
    group["window_start"] = group["ts"].dt.floor(window_delta)
    group["window_end"] = group["window_start"] + window_delta
    expected_rows, median_interval = _estimate_expected_rows(group, window_delta)
    group["_timestamp_gap"] = _timestamp_gap_flags(group, median_interval)

    rows = []
    grouped = group.groupby(["window_start", "window_end"], dropna=False)
    for (window_start, window_end), window in grouped:
        row = {
            "substation_id": substation_id,
            "window_start": window_start,
            "window_end": window_end,
            "source_file": _first_non_null(window.get("source_file")),
            "row_count": int(len(window)),
            "expected_row_count": expected_rows,
            "median_interval_minutes": median_interval,
            "invalid_timestamp_rows_in_file": int(group["_invalid_ts_count"].max()),
            "timestamp_gap_count": int(window["_timestamp_gap"].sum()),
            "max_timestamp_gap_minutes": _max_gap_minutes(window),
            "preprocessing_version": PREPROCESSING_VERSION,
            "created_at": pd.Timestamp.now(tz="UTC"),
        }
        row.update(_quality_metrics(window))
        row.update(_numeric_stats(window))
        row.update(_control_summaries(window))
        row.update(_event_context_for_window(substation_id, window_start, event_context))
        row.update(_config_for_substation(substation_id, config))
        rows.append(row)
    return pd.DataFrame(rows)


def _estimate_expected_rows(group: pd.DataFrame, window_delta: pd.Timedelta) -> tuple[int, float]:
    diffs = group["ts"].diff().dropna()
    if diffs.empty:
        return 1, math.nan
    median = diffs.median()
    if pd.isna(median) or median <= pd.Timedelta(0):
        return 1, math.nan
    expected = max(1, int(math.ceil(window_delta / median)))
    return expected, float(median.total_seconds() / 60)


def _timestamp_gap_flags(group: pd.DataFrame, median_interval_minutes: float) -> pd.Series:
    if pd.isna(median_interval_minutes) or median_interval_minutes <= 0:
        return pd.Series(False, index=group.index)
    threshold = pd.Timedelta(minutes=median_interval_minutes * 1.5)
    return group["ts"].diff().gt(threshold).fillna(False)


def _max_gap_minutes(window: pd.DataFrame) -> float:
    diffs = window["ts"].diff().dropna()
    if diffs.empty:
        return math.nan
    return float(diffs.max().total_seconds() / 60)


def _quality_metrics(window: pd.DataFrame) -> dict[str, object]:
    numeric = window[NUMERIC_SENSOR_COLUMNS]
    total_values = max(1, int(numeric.shape[0] * numeric.shape[1]))
    missing_count = int(numeric.isna().sum().sum())
    sensor_error_count = int(_sensor_error_flags(window).sum().sum())
    extreme_change_count = int(_extreme_change_flags(window).sum().sum())
    return {
        "missing_count": missing_count,
        "missing_rate": float(missing_count / total_values),
        "sensor_error_candidate_count": sensor_error_count,
        "extreme_change_count": extreme_change_count,
    }


def _numeric_stats(window: pd.DataFrame) -> dict[str, object]:
    stats: dict[str, object] = {}
    for sensor in NUMERIC_SENSOR_COLUMNS:
        series = window[sensor]
        stats[f"{sensor}__mean"] = series.mean(skipna=True)
        stats[f"{sensor}__min"] = series.min(skipna=True)
        stats[f"{sensor}__max"] = series.max(skipna=True)
        stats[f"{sensor}__std"] = series.std(skipna=True)
        stats[f"{sensor}__first"] = series.dropna().iloc[0] if not series.dropna().empty else math.nan
        stats[f"{sensor}__last"] = series.dropna().iloc[-1] if not series.dropna().empty else math.nan
        stats[f"{sensor}__delta"] = (
            stats[f"{sensor}__last"] - stats[f"{sensor}__first"]
            if pd.notna(stats[f"{sensor}__first"]) and pd.notna(stats[f"{sensor}__last"])
            else math.nan
        )
        stats[f"{sensor}__missing_count"] = int(series.isna().sum())
        stats[f"{sensor}__missing_rate"] = float(series.isna().mean()) if len(series) else math.nan
    return stats


def _control_summaries(window: pd.DataFrame) -> dict[str, object]:
    summaries: dict[str, object] = {}
    for sensor in CONTROL_STATUS_COLUMNS:
        series = window[sensor].astype("string").fillna("missing")
        summaries[f"{sensor}__dominant"] = _dominant_value(series)
        summaries[f"{sensor}__nunique"] = int(series.nunique(dropna=False))
        summaries[f"{sensor}__change_count"] = int(series.ne(series.shift()).sum() - 1) if len(series) else 0
    return summaries


def _sensor_error_flags(window: pd.DataFrame) -> pd.DataFrame:
    flags = pd.DataFrame(False, index=window.index, columns=NUMERIC_SENSOR_COLUMNS)
    for column in TEMPERATURE_COLUMNS:
        flags[column] = window[column].lt(-50) | window[column].gt(150)
    for column in FLOW_OR_POWER_COLUMNS:
        flags[column] = window[column].lt(0)
    for column in CUMULATIVE_COLUMNS:
        flags[column] = window[column].diff().lt(0)
    return flags.fillna(False)


def _extreme_change_flags(window: pd.DataFrame) -> pd.DataFrame:
    flags = pd.DataFrame(False, index=window.index, columns=NUMERIC_SENSOR_COLUMNS)
    for column in NUMERIC_SENSOR_COLUMNS:
        diff = window[column].diff().abs()
        baseline = diff.median(skipna=True)
        if pd.notna(baseline) and baseline > 0:
            flags[column] = diff.gt(baseline * 10)
    return flags.fillna(False)


def _prepare_event_context(
    fault_events: pd.DataFrame,
    maintenance_events: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    faults = fault_events.copy()
    tasks = maintenance_events.copy()
    if "report_date" not in faults.columns:
        faults["report_date"] = pd.NaT
    if "event_start" not in tasks.columns:
        tasks["event_start"] = pd.NaT
    faults["report_date"] = pd.to_datetime(faults["report_date"], errors="coerce", utc=True)
    tasks["event_start"] = pd.to_datetime(tasks["event_start"], errors="coerce", utc=True)
    return {"faults": faults.dropna(subset=["report_date"]), "tasks": tasks.dropna(subset=["event_start"])}


def _event_context_for_window(
    substation_id: int,
    window_start: pd.Timestamp,
    event_context: dict[str, pd.DataFrame],
) -> dict[str, object]:
    days_fault = _days_since_latest(event_context["faults"], substation_id, "report_date", window_start)
    days_task = _days_since_latest(event_context["tasks"], substation_id, "event_start", window_start)
    valid = [value for value in [days_fault, days_task] if pd.notna(value)]
    days_any = min(valid) if valid else math.nan
    post_fault = bool(pd.notna(days_fault) and days_fault <= STABILIZATION_DAYS)
    post_task = bool(pd.notna(days_task) and days_task <= STABILIZATION_DAYS)
    return {
        "days_since_last_fault_event": days_fault,
        "days_since_last_task_event": days_task,
        "days_since_last_any_event": days_any,
        "post_fault_stabilization": post_fault,
        "post_task_stabilization": post_task,
        "recent_regime_change_flag": bool(post_fault or post_task),
    }


def _days_since_latest(
    events: pd.DataFrame,
    substation_id: int,
    time_column: str,
    window_start: pd.Timestamp,
) -> float:
    if events.empty:
        return math.nan
    subset = events[(events["substation_id"] == substation_id) & (events[time_column] < window_start)]
    if subset.empty:
        return math.nan
    latest = subset[time_column].max()
    return float((window_start - latest).total_seconds() / 86400)


def _prepare_substations(substations: pd.DataFrame) -> pd.DataFrame:
    result = substations.copy()
    for column in ["configuration_type", "has_dhw", "has_buffer_tank"]:
        if column not in result.columns:
            result[column] = pd.NA
    return result


def _config_for_substation(substation_id: int, config: pd.DataFrame) -> dict[str, object]:
    row = config[config["substation_id"] == substation_id]
    if row.empty:
        return {"configuration_type": "missing", "has_dhw": pd.NA, "has_buffer_tank": pd.NA}
    first = row.iloc[0]
    configuration_type = first.get("configuration_type")
    return {
        "configuration_type": configuration_type if pd.notna(configuration_type) else "missing",
        "has_dhw": first.get("has_dhw", pd.NA),
        "has_buffer_tank": first.get("has_buffer_tank", pd.NA),
    }


def _dominant_value(series: pd.Series) -> str:
    modes = series.mode(dropna=False)
    return str(modes.iloc[0]) if not modes.empty else "missing"


def _first_non_null(series: pd.Series | None) -> object:
    if series is None:
        return pd.NA
    values = series.dropna()
    return values.iloc[0] if not values.empty else pd.NA


def _order_and_fill_contract_columns(frame: pd.DataFrame) -> pd.DataFrame:
    columns = schema_columns()
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[columns]
    return result


def _empty_output() -> pd.DataFrame:
    return pd.DataFrame(columns=schema_columns())
