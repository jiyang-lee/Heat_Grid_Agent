from __future__ import annotations

import re

import pandas as pd


WINDOW_SIZE = pd.Timedelta(hours=6)
WINDOW_FREQ = "6h"
MIN_ROW_RATIO = 0.5
MAX_MISSING_RATE = 0.3
HEATING_SEASON_MONTHS = {11, 12, 1, 2, 3}
CONTROL_CONTEXT_PATTERN = re.compile(r"(mode|status|state|operation)", re.IGNORECASE)
EVENT_CONTEXT_SENTINEL_DAYS = 9999.0

CORE_SENSOR_COLUMNS = [
    "outdoor_temperature",
    "s_hc1_supply_temperature",
    "s_hc1_supply_temperature_setpoint",
    "s_dhw_supply_temperature",
    "s_dhw_supply_temperature_setpoint",
    "p_hc1_return_temperature",
    "p_dhw_return_temperature",
    "s_dhw_upper_storage_temperature",
    "s_dhw_lower_storage_temperature",
    "p_net_meter_energy",
    "p_net_meter_volume",
    "p_net_meter_heat_power",
    "p_net_meter_flow",
    "p_net_supply_temperature",
    "p_net_return_temperature",
    "p_hc1_control_valve_position_setpoint",
    "p_dhw_control_valve_position",
]

DERIVED_PAIRS = {
    "hc1_supply_temperature_gap": (
        "s_hc1_supply_temperature",
        "s_hc1_supply_temperature_setpoint",
    ),
    "dhw_supply_temperature_gap": (
        "s_dhw_supply_temperature",
        "s_dhw_supply_temperature_setpoint",
    ),
    "network_temperature_gap": (
        "p_net_supply_temperature",
        "p_net_return_temperature",
    ),
}

CUMULATIVE_COLUMNS = ["p_net_meter_energy", "p_net_meter_volume"]
TEMPERATURE_COLUMNS = [column for column in CORE_SENSOR_COLUMNS if "temperature" in column]
FLOW_COLUMNS = [column for column in CORE_SENSOR_COLUMNS if "flow" in column]
POWER_COLUMNS = [column for column in CORE_SENSOR_COLUMNS if "heat_power" in column]

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]

MANUFACTURER_CODE = {
    "manufacturer 1": 0,
    "manufacturer 2": 1,
}

CONFIGURATION_CODE = {
    "SH": 0,
    "SH + DHW": 1,
    "SH + DHW with sub-circuits": 2,
    "SH with buffer tank": 3,
    "SH with sub-circuits": 4,
    "missing": 5,
}

LEADTIME_LABELS = ["0-24h", "1-3d", "3-7d"]

TIMEFLOW_SOURCE_COLUMNS = [
    "anomaly_score",
    "risk_probability",
    "network_temperature_gap__mean",
    "p_net_return_temperature__mean",
    "p_net_supply_temperature__mean",
    "days_since_last_task_event",
    "days_since_last_any_event",
]
