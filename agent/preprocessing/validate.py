"""Validation helpers for preprocessing inputs and outputs."""

from __future__ import annotations

import pandas as pd

from agent.preprocessing.contracts import schema_columns


def require_columns(frame: pd.DataFrame, columns: set[str], table_name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{table_name} missing required columns: {missing}")


def validate_raw_inputs(
    substations: pd.DataFrame,
    sensor_readings: pd.DataFrame,
    fault_events: pd.DataFrame,
    maintenance_events: pd.DataFrame,
) -> None:
    require_columns(substations, {"substation_id"}, "substations")
    require_columns(sensor_readings, {"substation_id", "ts"}, "sensor_readings")
    require_columns(fault_events, {"substation_id"}, "fault_events")
    require_columns(maintenance_events, {"substation_id"}, "maintenance_events")


def validate_preprocessed_columns(frame: pd.DataFrame) -> None:
    expected = schema_columns()
    actual = list(frame.columns)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(
            "preprocessed_windows columns do not match schema order: "
            f"missing={missing}, extra={extra}"
        )
