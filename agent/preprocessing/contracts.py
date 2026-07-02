"""Stable preprocessing contract constants."""

from __future__ import annotations

import json
from pathlib import Path

PREPROCESSING_VERSION = "preprocessed_data_v1"
WINDOW_SIZE = "6h"
MIN_ROW_RATIO = 0.5
MAX_MISSING_RATE = 0.3
STABILIZATION_DAYS = 14

NUMERIC_SENSOR_COLUMNS = [
    "outdoor_temperature",
    "p_dhw_control_valve_position",
    "p_dhw_return_temperature",
    "p_hc1_control_valve_position_setpoint",
    "p_hc1_return_temperature",
    "p_net_meter_energy",
    "p_net_meter_flow",
    "p_net_meter_heat_power",
    "p_net_meter_volume",
    "p_net_return_temperature",
    "p_net_supply_temperature",
    "s_dhw_lower_storage_temperature",
    "s_dhw_supply_temperature",
    "s_dhw_supply_temperature_setpoint",
    "s_dhw_upper_storage_temperature",
    "s_hc1_supply_temperature",
    "s_hc1_supply_temperature_setpoint",
]

CONTROL_STATUS_COLUMNS = [
    "s_dhw_3way_valve_status",
    "s_dhw_control_unit_mode",
    "s_hc1_1_control_unit_mode",
    "s_hc1_1_heating_pump_status",
    "s_hc1_2_control_unit_mode",
    "s_hc1_2_dhw_control_unit_mode",
    "s_hc1_2_heating_pump_status",
    "s_hc1_3_control_unit_mode",
    "s_hc1_3_heating_pump_status",
    "s_hc1_control_unit_mode",
    "s_hc1_heating_pump_status_setpoint",
]

NUMERIC_STAT_SUFFIXES = [
    "mean",
    "min",
    "max",
    "std",
    "first",
    "last",
    "delta",
    "missing_count",
    "missing_rate",
]

CONTROL_SUMMARY_SUFFIXES = ["dominant", "nunique", "change_count"]
CUMULATIVE_COLUMNS = {"p_net_meter_energy", "p_net_meter_volume"}
TEMPERATURE_COLUMNS = [column for column in NUMERIC_SENSOR_COLUMNS if "temperature" in column]
FLOW_OR_POWER_COLUMNS = [
    column
    for column in NUMERIC_SENSOR_COLUMNS
    if "flow" in column or "heat_power" in column
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def schema_columns() -> list[str]:
    schema_path = repo_root() / "schema" / "json" / "preprocessed_windows.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return list(schema["properties"].keys())


def numeric_derived_columns() -> list[str]:
    return [
        f"{sensor}__{suffix}"
        for sensor in NUMERIC_SENSOR_COLUMNS
        for suffix in NUMERIC_STAT_SUFFIXES
    ]


def control_derived_columns() -> list[str]:
    return [
        f"{sensor}__{suffix}"
        for sensor in CONTROL_STATUS_COLUMNS
        for suffix in CONTROL_SUMMARY_SUFFIXES
    ]
