from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from third_model.synthetic_replay import (
    DEFAULT_REPLAY_END,
    DEFAULT_REPLAY_START,
    DEFAULT_WARMUP_START,
    ReplayGenerationConfig,
    _calendar_balanced_pair,
    _high_trajectory_heads,
    _scenario_donor_index,
    build_model_sensor_registry,
    expected_dataset_counts,
    generate_replay_dataset,
    load_sensor_manifest,
    validate_replay_dataset,
)


SENSORS = (
    "outdoor_temperature",
    "p_net_supply_temperature",
    "p_net_return_temperature",
    "p_net_meter_flow",
)


def _write_fixture_project(root: Path) -> tuple[Path, Path, Path]:
    (root / "models/anomaly").mkdir(parents=True)
    (root / "models/risk").mkdir(parents=True)
    (root / "models/leadtime").mkdir(parents=True)
    (root / "models/m1_specialist").mkdir(parents=True)
    (root / "data/interim").mkdir(parents=True)
    (root / "data/processed").mkdir(parents=True)
    raw_root = root / "raw"
    operational = raw_root / "manufacturer 1/operational_data"
    operational.mkdir(parents=True)

    feature_columns = [
        f"{sensor}__{statistic}"
        for sensor in SENSORS
        for statistic in (
            "mean",
            "min",
            "max",
            "std",
            "first",
            "last",
            "delta",
            "missing_count",
            "missing_rate",
        )
    ]
    feature_columns += [
        "network_temperature_gap__mean",
        "network_temperature_gap__last",
        "network_temperature_gap__max_abs",
        "dow_cos",
        "dow_sin",
        "doy_cos",
        "doy_sin",
        "hour_cos",
        "hour_sin",
    ]
    for base in (
        "p_net_supply_temperature__mean",
        "p_net_return_temperature__mean",
        "network_temperature_gap__mean",
    ):
        feature_columns += [
            f"{base}__lag1",
            f"{base}__lag2",
            f"{base}__delta1",
            f"{base}__roll3_mean",
        ]
    feature_columns += [
        "p_net_supply_temperature__mean__roll24h_mean",
        "p_net_supply_temperature__mean__roll24h_delta",
        "has_buffer_tank",
        "has_dhw",
    ]
    (root / "models/anomaly/anomaly_metadata.json").write_text(
        json.dumps({"feature_columns": feature_columns}), encoding="utf-8"
    )
    (root / "models/risk/risk_model_best_metadata.json").write_text(
        json.dumps({"model_feature_columns": []}), encoding="utf-8"
    )
    (root / "models/leadtime/leadtime_model_best_metadata.json").write_text(
        json.dumps({"model_feature_columns": []}), encoding="utf-8"
    )
    (root / "models/m1_specialist/m1_specialist_gate_metadata.json").write_text(
        json.dumps({"features": []}), encoding="utf-8"
    )

    schema_rows = []
    timestamps = pd.date_range("2019-12-20", periods=14 * 144, freq="10min")
    for station in (1, 2):
        day = np.arange(len(timestamps), dtype="float64") / 144.0
        outdoor = 1.5 + 5.0 * np.sin(day * 2 * np.pi / 7) + station * 0.1
        returned = 42.0 - outdoor * 0.2 + station
        supply = returned + 45.0 + np.sin(day * 2 * np.pi)
        flow = 500.0 - outdoor * 12.0 + station * 5.0
        if station == 2:
            returned = np.full(len(timestamps), np.nan)
            supply = np.full(len(timestamps), np.nan)
            flow = np.full(len(timestamps), np.nan)
        raw = pd.DataFrame(
            {
                "timestamp": timestamps,
                "outdoor_temperature": outdoor,
                "p_net_supply_temperature": supply,
                "p_net_return_temperature": returned,
                "p_net_meter_flow": flow,
                "s_hc1_supply_temperature_setpoint": 50.0,
            }
        )
        if station == 2:
            raw = raw.drop(
                columns=[
                    "p_net_supply_temperature",
                    "p_net_return_temperature",
                    "p_net_meter_flow",
                ]
            )
        raw.to_csv(
            operational / f"substation_{station}.csv",
            sep=";",
            index=False,
            encoding="utf-8",
        )
        for column in raw.columns:
            schema_rows.append(
                {
                    "manufacturer": "manufacturer 1",
                    "substation_id": station,
                    "column_name": column,
                    "sample_non_null_count": int(raw[column].notna().sum()),
                }
            )
    pd.DataFrame(schema_rows).to_csv(root / "data/interim/raw_schema_summary.csv", index=False)

    donors = []
    for station in (1, 2):
        row = {
            "manufacturer": "manufacturer 1",
            "substation_id": station,
            "window_start": "2019-12-20 00:00:00",
            "window_end": "2019-12-20 06:00:00",
            "season_bucket": "winter",
            "label": "normal",
            "split_regime_based": "train",
            "split_time_based": "train",
        }
        row.update({feature: 0.0 for feature in feature_columns})
        row["has_buffer_tank"] = station == 1
        row["has_dhw"] = station != 1
        donors.append(row)
    donor_path = root / "data/processed/trainable_windows.csv"
    pd.DataFrame(donors).to_csv(donor_path, index=False)

    manifest_path = root / "sensor_manifest.csv"
    pd.DataFrame(
        [
            {
                "sensor_key": sensor,
                "source_column": sensor,
                "label_ko": sensor,
                "unit": "degC" if "temperature" in sensor else "L/h",
                "display_order": index,
                "sensor_type": "temperature" if "temperature" in sensor else "flow",
                "model_feature_prefix": f"{sensor}__",
                "nullable": False,
                "enabled": True,
            }
            for index, sensor in enumerate(SENSORS, start=1)
        ]
    ).to_csv(manifest_path, index=False)
    return raw_root, donor_path, manifest_path


def test_default_three_year_counts_are_exact(tmp_path: Path) -> None:
    generation = ReplayGenerationConfig(
        project_root=tmp_path,
        output_root=tmp_path / "out",
        sensor_manifest_path=tmp_path / "sensors.csv",
        raw_root=tmp_path / "raw",
        donor_windows_path=tmp_path / "windows.csv",
        warmup_start=DEFAULT_WARMUP_START,
        replay_start=DEFAULT_REPLAY_START,
        replay_end=DEFAULT_REPLAY_END,
    )
    counts = expected_dataset_counts(generation)
    assert counts["warmup_raw_rows"] == 31_248
    assert counts["replay_raw_rows"] == 4_892_544
    assert counts["total_raw_rows"] == 4_923_792
    assert counts["warmup_window_rows"] == 868
    assert counts["replay_window_rows"] == 135_904
    assert counts["total_window_rows"] == 136_772


def test_calendar_audit_treats_naive_source_timestamps_as_kst() -> None:
    reference = pd.DataFrame(
        {
            "substation_id": [1, 1],
            "simulated_at": ["2023-01-31 23:50:00", "2023-02-01 00:00:00"],
            "sensor": [1.0, 2.0],
        }
    )
    synthetic = pd.DataFrame(
        {
            "substation_id": [1, 1],
            "simulated_at": [
                "2023-01-31T23:50:00+09:00",
                "2023-02-01T00:00:00+09:00",
            ],
            "sensor": [1.0, 2.0],
        }
    )
    balanced_reference, balanced_synthetic = _calendar_balanced_pair(
        reference, synthetic
    )
    assert balanced_reference["sensor"].tolist() == [1.0, 2.0]
    assert balanced_synthetic["sensor"].tolist() == [1.0, 2.0]


def test_fault_trajectory_reaches_its_endpoint_in_the_final_window() -> None:
    donors = pd.DataFrame(
        {
            "donor_id": ["early", "middle", "late"],
        }
    )
    scenarios = pd.DataFrame(
        {
            "scenario_id": ["fault-01"],
            "scenario_type": ["pre_fault_drift"],
            "start": ["2023-01-08T00:00:00+09:00"],
            "end": ["2023-01-08T12:00:00+09:00"],
            "donor_id": ["early"],
            "donor_sequence_json": ['["early","middle","late"]'],
        }
    )

    first = _scenario_donor_index(
        donors,
        "fault-01",
        scenarios,
        pd.Timestamp("2023-01-08T00:00:00+09:00"),
    )
    final = _scenario_donor_index(
        donors,
        "fault-01",
        scenarios,
        pd.Timestamp("2023-01-08T06:00:00+09:00"),
    )

    assert donors.loc[first, "donor_id"] == "middle"
    assert donors.loc[final, "donor_id"] == "late"


def test_model_guided_selection_keeps_best_high_row_per_fault_trajectory() -> None:
    scored = pd.DataFrame(
        {
            "donor_id": ["event-a-early", "event-a-late", "event-b"],
            "substation_id": [30, 30, 26],
            "fault_event_id": [10.0, 10.0, 69.0],
            "_runtime_priority_level": ["medium", "high", "high"],
            "_runtime_priority_score": [79.0, 93.0, 88.0],
        }
    )

    selected = _high_trajectory_heads(scored)

    assert selected["donor_id"].tolist() == ["event-a-late", "event-b"]


def test_registry_and_manifest_allow_only_four_physical_model_sensors(tmp_path: Path) -> None:
    _, _, manifest_path = _write_fixture_project(tmp_path)
    schema_path = tmp_path / "data/interim/raw_schema_summary.csv"
    schema = pd.read_csv(schema_path)
    schema = pd.concat(
        [
            schema,
            pd.DataFrame(
                [
                    {
                        "manufacturer": "manufacturer 2",
                        "substation_id": 2,
                        "column_name": "p_net_meter_flow",
                        "sample_non_null_count": 200,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    schema.to_csv(schema_path, index=False)
    registry = build_model_sensor_registry(tmp_path)
    assert set(SENSORS).issubset(set(registry["source_column"]))
    assert "s_hc1_supply_temperature_setpoint" not in set(registry["source_column"])
    assert bool(
        registry.loc[registry["source_column"].eq("p_net_meter_flow"), "nullable"].iloc[0]
    )
    assert int(
        registry.loc[
            registry["source_column"].eq("p_net_meter_flow"), "available_station_count"
        ].iloc[0]
    ) == 1
    enabled = load_sensor_manifest(manifest_path, registry)
    assert enabled["source_column"].tolist() == list(SENSORS)

    invalid = pd.read_csv(manifest_path)
    invalid.loc[0, "enabled"] = False
    invalid.to_csv(manifest_path, index=False)
    with pytest.raises(ValueError, match="exactly four"):
        load_sensor_manifest(manifest_path, registry)


def test_small_dataset_is_deterministic_and_window_aggregates_match_raw(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw_root, donor_path, sensor_manifest = _write_fixture_project(project)
    outputs = []
    for name in ("first", "second"):
        output = tmp_path / name
        generation = ReplayGenerationConfig(
            project_root=project,
            output_root=output,
            sensor_manifest_path=sensor_manifest,
            raw_root=raw_root,
            donor_windows_path=donor_path,
            warmup_start="2023-01-01T00:00:00+09:00",
            replay_start="2023-01-01T06:00:00+09:00",
            replay_end="2023-01-01T12:00:00+09:00",
            stations=(1, 2),
            seed=77,
            fault_scenario_count=0,
            quality_scenario_count=0,
        )
        manifest = generate_replay_dataset(generation)
        result = validate_replay_dataset(output, project_root=project)
        assert result["valid"]
        assert result["raw_rows"] == 144
        assert result["window_rows"] == 4
        outputs.append((output, manifest))

    assert outputs[0][1]["raw_shards"][0]["sha256"] == outputs[1][1]["raw_shards"][0]["sha256"]
    raw = pd.read_csv(outputs[0][0] / outputs[0][1]["raw_shards"][0]["path"])
    windows = pd.read_csv(outputs[0][0] / outputs[0][1]["window_shards"][0]["path"])
    first_replay = raw.loc[raw["phase"].eq("replay"), "simulated_at"].min()
    assert pd.Timestamp(first_replay) == pd.Timestamp("2023-01-01T06:00:00+09:00")
    station_raw = raw.loc[(raw["substation_id"].eq(1)) & (raw["sequence"].lt(36))]
    station_window = windows.loc[
        (windows["substation_id"].eq(1)) & (windows["sequence_end"].eq(35))
    ].iloc[0]
    for sensor in SENSORS:
        values = station_raw[sensor]
        assert station_window[f"{sensor}__mean"] == pytest.approx(values.mean())
        assert station_window[f"{sensor}__min"] == pytest.approx(values.min())
        assert station_window[f"{sensor}__max"] == pytest.approx(values.max())
        assert station_window[f"{sensor}__delta"] == pytest.approx(values.iloc[-1] - values.iloc[0])

    donor_map = pd.read_csv(outputs[0][0] / "sensor_donor_map.csv")
    assert set(donor_map.loc[donor_map["substation_id"].eq(2), "donor_station_id"]) == {1}

    no_seek_manifest = outputs[1][0] / "dataset_manifest.json"
    no_seek_payload = json.loads(no_seek_manifest.read_text(encoding="utf-8"))
    no_seek_payload["scenario_runtime_validation"] = {
        "status": "completed",
        "candidate_count": 1,
        "eligible_count": 0,
    }
    no_seek_manifest.write_text(json.dumps(no_seek_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="no model-approved seek point"):
        validate_replay_dataset(outputs[1][0], project_root=project)

    window_path = outputs[0][0] / outputs[0][1]["window_shards"][0]["path"]
    corrupted = pd.read_csv(window_path)
    corrupted.loc[corrupted.index[-1], "p_net_meter_flow__mean"] += 1.0
    corrupted.to_csv(window_path, index=False)
    digest = hashlib.sha256(window_path.read_bytes()).hexdigest()
    manifest_path = outputs[0][0] / "dataset_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["window_shards"][0]["sha256"] = digest
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="aggregate parity"):
        validate_replay_dataset(outputs[0][0], project_root=project)


def test_quality_scenario_missing_values_are_intentional_and_keep_parity(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw_root, donor_path, sensor_manifest = _write_fixture_project(project)
    output = tmp_path / "quality"
    generation = ReplayGenerationConfig(
        project_root=project,
        output_root=output,
        sensor_manifest_path=sensor_manifest,
        raw_root=raw_root,
        donor_windows_path=donor_path,
        warmup_start="2023-01-01T00:00:00+09:00",
        replay_start="2023-01-01T06:00:00+09:00",
        replay_end="2023-01-07T00:00:00+09:00",
        stations=(1,),
        seed=91,
        fault_scenario_count=0,
        quality_scenario_count=1,
    )
    generate_replay_dataset(generation)
    result = validate_replay_dataset(output, project_root=project)
    assert result["valid"]
    assert result["timing_and_parity"]["raw_window_aggregate_parity"]
    assert result["intentional_quality_scenario_missing_values"] == 24
    assert result["unexpected_missing_values"] == 0


def test_window_causal_features_follow_source_model_contract(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw_root, donor_path, sensor_manifest = _write_fixture_project(project)
    output = tmp_path / "causal"
    generation = ReplayGenerationConfig(
        project_root=project,
        output_root=output,
        sensor_manifest_path=sensor_manifest,
        raw_root=raw_root,
        donor_windows_path=donor_path,
        warmup_start="2023-01-01T00:00:00+09:00",
        replay_start="2023-01-01T06:00:00+09:00",
        replay_end="2023-01-02T06:00:00+09:00",
        stations=(1,),
        seed=101,
        fault_scenario_count=0,
        quality_scenario_count=0,
    )
    manifest = generate_replay_dataset(generation)
    windows = pd.concat(
        [pd.read_csv(output / shard["path"]) for shard in manifest["window_shards"]],
        ignore_index=True,
    ).sort_values("sequence_end")

    for base in (
        "p_net_supply_temperature__mean",
        "p_net_return_temperature__mean",
        "network_temperature_gap__mean",
    ):
        source = pd.to_numeric(windows[base], errors="raise").reset_index(drop=True)
        np.testing.assert_allclose(
            windows[f"{base}__lag1"], source.shift(1).fillna(source), atol=1e-9
        )
        np.testing.assert_allclose(
            windows[f"{base}__lag2"], source.shift(2).fillna(source), atol=1e-9
        )
        np.testing.assert_allclose(
            windows[f"{base}__delta1"],
            (source - source.shift(1)).fillna(0.0),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            windows[f"{base}__roll3_mean"],
            source.rolling(3, min_periods=1).mean(),
            atol=1e-9,
        )

    supply = windows["p_net_supply_temperature__mean"].reset_index(drop=True)
    np.testing.assert_allclose(
        windows["p_net_supply_temperature__mean__roll24h_mean"],
        supply.rolling(4, min_periods=1).mean(),
        atol=1e-9,
    )
    np.testing.assert_allclose(
        windows["p_net_supply_temperature__mean__roll24h_delta"],
        (supply - supply.shift(4)).fillna(0.0),
        atol=1e-9,
    )
    midpoint = pd.to_datetime(windows["window_start"], utc=True).dt.tz_convert(
        "Asia/Seoul"
    ) + pd.Timedelta(hours=3)
    np.testing.assert_allclose(
        windows["doy_cos"], np.cos(2 * np.pi * midpoint.dt.dayofyear / 366)
    )
    np.testing.assert_allclose(
        windows["doy_sin"], np.sin(2 * np.pi * midpoint.dt.dayofyear / 366)
    )
    assert set(windows["has_buffer_tank"].unique()) == {1.0}
    assert set(windows["has_dhw"].unique()) == {0.0}
