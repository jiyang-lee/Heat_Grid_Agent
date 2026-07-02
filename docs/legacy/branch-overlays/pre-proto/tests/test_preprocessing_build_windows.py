import json
import re
from pathlib import Path

import pandas as pd

from agent.preprocessing import build_preprocessed_windows
from agent.preprocessing.contracts import (
    CONTROL_STATUS_COLUMNS,
    NUMERIC_SENSOR_COLUMNS,
    PREPROCESSING_VERSION,
)


def _sensor_rows(include_events: bool = True) -> pd.DataFrame:
    rows = []
    for ts, value, status in [
        ("2026-01-01 00:00:00", 10.0, None),
        ("2026-01-01 01:00:00", 12.0, "auto"),
        ("bad timestamp", 99.0, "manual"),
    ]:
        row = {"substation_id": 1, "ts": ts, "source_file": "substation_1.csv"}
        for column in NUMERIC_SENSOR_COLUMNS:
            row[column] = value
        for column in CONTROL_STATUS_COLUMNS:
            row[column] = status
        rows.append(row)
    return pd.DataFrame(rows)


def _substations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "substation_id": 1,
                "configuration_type": "sh_dhw",
                "has_dhw": True,
                "has_buffer_tank": False,
            }
        ]
    )


def test_build_preprocessed_windows_matches_schema_columns():
    result = build_preprocessed_windows(
        _substations(),
        _sensor_rows(),
        pd.DataFrame(columns=["substation_id", "report_date"]),
        pd.DataFrame(columns=["substation_id", "event_start"]),
    )

    schema = json.loads(Path("schema/json/preprocessed_windows.schema.json").read_text(encoding="utf-8"))
    assert list(result.columns) == list(schema["properties"].keys())
    assert len(result.columns) == 211
    assert len([column for column in result.columns if re.search(r"__(mean|min|max|std|first|last|delta|missing_count|missing_rate)$", column)]) == 153
    assert len([column for column in result.columns if re.search(r"__(dominant|nunique|change_count)$", column)]) == 33


def test_build_preprocessed_windows_fail_soft_defaults():
    result = build_preprocessed_windows(
        _substations(),
        _sensor_rows(),
        pd.DataFrame(columns=["substation_id", "report_date"]),
        pd.DataFrame(columns=["substation_id", "event_start"]),
    )

    row = result.iloc[0]
    assert len(result) == 1
    assert row["row_count"] == 2
    assert row["invalid_timestamp_rows_in_file"] == 1
    assert row["s_dhw_control_unit_mode__dominant"] == "auto"
    assert pd.isna(row["days_since_last_fault_event"])
    assert pd.isna(row["days_since_last_task_event"])
    assert row["post_fault_stabilization"] == False
    assert row["post_task_stabilization"] == False
    assert row["preprocessing_version"] == PREPROCESSING_VERSION


def test_build_preprocessed_windows_event_context():
    faults = pd.DataFrame([{"substation_id": 1, "report_date": "2025-12-30 00:00:00"}])
    tasks = pd.DataFrame([{"substation_id": 1, "event_start": "2025-12-31 00:00:00"}])

    result = build_preprocessed_windows(_substations(), _sensor_rows(), faults, tasks)
    row = result.iloc[0]

    assert row["days_since_last_fault_event"] == 2.0
    assert row["days_since_last_task_event"] == 1.0
    assert row["days_since_last_any_event"] == 1.0
    assert row["post_fault_stabilization"] == True
    assert row["post_task_stabilization"] == True
    assert row["recent_regime_change_flag"] == True


def test_missing_required_keys_fail_clearly():
    bad_sensor_readings = pd.DataFrame({"substation_id": [1]})

    try:
        build_preprocessed_windows(
            _substations(),
            bad_sensor_readings,
            pd.DataFrame(columns=["substation_id", "report_date"]),
            pd.DataFrame(columns=["substation_id", "event_start"]),
        )
    except ValueError as exc:
        assert "sensor_readings missing required columns" in str(exc)
    else:
        raise AssertionError("missing ts did not fail")
