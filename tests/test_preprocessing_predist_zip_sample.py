import json
from pathlib import Path

import pandas as pd
import pytest

from agent.preprocessing import build_preprocessed_windows
from agent.preprocessing.contracts import PREPROCESSING_VERSION
from agent.preprocessing.sample_predist_zip import build_predist_sample, run_predist_sample
from agent.preprocessing import sample_predist_zip as sample_module

ZIP_PATH = Path("C:/Users/Admin/Downloads/predist_dataset.zip")
FIXTURE_DIR = Path("agent/fixtures/preprocessing/predist_sample")
RAW_DIR = FIXTURE_DIR / "raw"
OUTPUT_PATH = FIXTURE_DIR / "output" / "preprocessed_windows_sample.csv"
LABEL_PATH = FIXTURE_DIR / "output" / "supervised_window_labels.csv"


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
        LABEL_PATH,
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
    labels = pd.read_csv(LABEL_PATH)
    result = build_preprocessed_windows(
        raw["substations"],
        raw["sensor_readings"],
        raw["fault_events"],
        raw["maintenance_events"],
    )

    assert len(labels) == 300
    assert labels.duplicated(["substation_id", "window_start"]).sum() == 0
    assert labels["label"].value_counts().to_dict() == {"normal": 163, "pre_fault": 137}
    assert labels[labels["label"].eq("pre_fault")]["lead_time_bucket"].value_counts().to_dict() == {
        "3-7d": 79,
        "1-3d": 39,
        "0-24h": 19,
    }
    assert len(raw["sensor_readings"]) == 10800
    assert len(result) == len(expected)
    assert len(result) == 300
    assert list(result.columns) == list(expected.columns)
    assert set(result["preprocessing_version"]) == {PREPROCESSING_VERSION}
    assert set(result["configuration_type"]) == {"missing"}


def test_coerce_bool_like_parses_variant_efd_values():
    values = pd.Series(["TRUE", "true", "1", "0", "yes", "N", "", None, 1, 0, 2, "False"])
    parsed = sample_module._coerce_bool_like(values)
    assert parsed.tolist() == [True, True, True, False, True, False, False, False, True, False, False, False]
