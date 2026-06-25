import json
from pathlib import Path

import pandas as pd
import pytest

from agent.preprocessing import build_preprocessed_windows
from agent.preprocessing.contracts import PREPROCESSING_VERSION
from agent.preprocessing.sample_predist_zip import build_predist_sample, run_predist_sample

ZIP_PATH = Path("C:/Users/Admin/Downloads/predist_dataset.zip")
FIXTURE_DIR = Path("agent/fixtures/preprocessing/predist_sample")
RAW_DIR = FIXTURE_DIR / "raw"
OUTPUT_PATH = FIXTURE_DIR / "output" / "preprocessed_windows_sample.csv"


def test_predist_zip_sample_builds_preprocessed_windows():
    if not ZIP_PATH.exists():
        pytest.skip(f"PreDist ZIP not found: {ZIP_PATH}")

    raw = build_predist_sample(ZIP_PATH, rows_per_substation=150)

    assert set(raw) == {
        "substations",
        "sensor_readings",
        "fault_events",
        "maintenance_events",
    }
    assert 100 <= len(raw["sensor_readings"]) <= 300
    assert len(raw["substations"]) == 2

    result = run_predist_sample(ZIP_PATH)
    schema = json.loads(Path("schema/json/preprocessed_windows.schema.json").read_text(encoding="utf-8"))

    assert len(result) >= 1
    assert len(result.columns) == 211
    assert list(result.columns) == list(schema["properties"].keys())
    assert set(result["preprocessing_version"]) == {PREPROCESSING_VERSION}
    assert set(result["configuration_type"]) == {"missing"}


def test_predist_raw_fixture_rebuilds_preprocessed_windows():
    required = [
        RAW_DIR / "substations.csv",
        RAW_DIR / "sensor_readings.csv",
        RAW_DIR / "fault_events.csv",
        RAW_DIR / "maintenance_events.csv",
        OUTPUT_PATH,
    ]
    missing = [path for path in required if not path.exists()]
    assert not missing, f"missing fixture files: {missing}"

    raw = {
        "substations": pd.read_csv(RAW_DIR / "substations.csv"),
        "sensor_readings": pd.read_csv(RAW_DIR / "sensor_readings.csv"),
        "fault_events": pd.read_csv(RAW_DIR / "fault_events.csv"),
        "maintenance_events": pd.read_csv(RAW_DIR / "maintenance_events.csv"),
    }
    expected = pd.read_csv(OUTPUT_PATH)
    result = build_preprocessed_windows(
        raw["substations"],
        raw["sensor_readings"],
        raw["fault_events"],
        raw["maintenance_events"],
    )

    assert len(raw["sensor_readings"]) == 300
    assert len(result) == len(expected)
    assert list(result.columns) == list(expected.columns)
    assert set(result["preprocessing_version"]) == {PREPROCESSING_VERSION}
    assert set(result["configuration_type"]) == {"missing"}
