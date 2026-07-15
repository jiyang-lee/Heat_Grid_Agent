from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

DEFAULT_WARMUP_START = pd.Timestamp("2023-01-01 00:00:00", tz="Asia/Seoul")
DEFAULT_REPLAY_START = pd.Timestamp("2023-01-08 00:00:00", tz="Asia/Seoul")
DEFAULT_REPLAY_END = pd.Timestamp("2026-01-08 00:00:00", tz="Asia/Seoul")
SOURCE_INTERVAL = pd.Timedelta(minutes=10)
WINDOW_INTERVAL = pd.Timedelta(hours=6)
WINDOW_TICKS = 36
DEFAULT_STATIONS = tuple(range(1, 32))
MANUFACTURER_ID = "manufacturer 1"
DEFAULT_FAULT_SCENARIO_COUNT = 96
DEFAULT_QUALITY_SCENARIO_COUNT = 18
DEFAULT_MINIMUM_ELIGIBLE_FAULT_SCENARIOS = 10
FAULT_EFFECT_SCALES = (1.0, 1.1, 1.2, 1.25)

RAW_METADATA_COLUMNS = [
    "dataset_version",
    "sequence",
    "phase",
    "simulated_at",
    "manufacturer_id",
    "substation_id",
]
RAW_TRAILING_COLUMNS = ["quality_flag", "is_synthetic", "scenario_id"]
WINDOW_METADATA_COLUMNS = [
    "dataset_version",
    "sequence_end",
    "phase",
    "manufacturer_id",
    "substation_id",
    "configuration_type",
    "window_start",
    "window_end",
    "expected_count",
    "observed_count",
    "feature_set_version",
    "feature_hash",
    "scenario_id",
]

MODEL_METADATA_SPECS = (
    ("models/anomaly/anomaly_metadata.json", "feature_columns"),
    ("models/risk/risk_model_best_metadata.json", "model_feature_columns"),
    ("models/leadtime/leadtime_model_best_metadata.json", "model_feature_columns"),
    ("models/m1_specialist/m1_specialist_gate_metadata.json", "features"),
)

NON_SENSOR_TOKENS = (
    "setpoint",
    "status",
    "control_unit_mode",
    "timestamp",
    "gap",
    "score",
    "label",
    "probability",
)

SENSOR_LABELS = {
    "outdoor_temperature": "외기온도",
    "p_hc1_return_temperature": "난방 1차 환수온도",
    "p_net_meter_energy": "1차 누적 열에너지",
    "p_net_meter_flow": "1차 유량",
    "p_net_meter_heat_power": "1차 열출력",
    "p_net_meter_volume": "1차 누적 유량",
    "p_net_return_temperature": "1차 환수온도",
    "p_net_supply_temperature": "1차 공급온도",
    "s_hc1_supply_temperature": "난방 2차 공급온도",
    "s_dhw_lower_storage_temperature": "급탕 하부 저장온도",
    "s_dhw_supply_temperature": "급탕 공급온도",
    "s_dhw_upper_storage_temperature": "급탕 상부 저장온도",
}


def _timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        return result.tz_localize("Asia/Seoul")
    return result.tz_convert("Asia/Seoul")


def _iso(value: pd.Timestamp) -> str:
    return value.isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _season(timestamp: pd.Timestamp) -> str:
    return {
        12: "winter",
        1: "winter",
        2: "winter",
        3: "spring",
        4: "spring",
        5: "spring",
        6: "summer",
        7: "summer",
        8: "summer",
        9: "autumn",
        10: "autumn",
        11: "autumn",
    }[timestamp.month]


def _sensor_type(name: str) -> tuple[str, str]:
    if "temperature" in name:
        return "temperature", "degC"
    if "heat_power" in name:
        return "heat_power", "kW"
    if name.endswith("_flow"):
        return "flow", "L/h"
    if name.endswith("_energy"):
        return "cumulative_energy", "kWh"
    if name.endswith("_volume"):
        return "cumulative_volume", "m3"
    return "numeric", ""


def load_model_feature_union(project_root: Path) -> list[str]:
    """Return the ordered union of every deployed model input contract."""
    features: list[str] = []
    for relative, key in MODEL_METADATA_SPECS:
        path = project_root / relative
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        features.extend(str(item) for item in payload.get(key, []))

    runtime_path = project_root / "models/m1_specialist/m1_full_gate_runtime_policy_metadata.json"
    if runtime_path.exists():
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
        for metadata in payload.get("models", {}).values():
            features.extend(str(item) for item in metadata.get("features", []))
    return list(dict.fromkeys(features))


def build_model_sensor_registry(
    project_root: Path,
    *,
    raw_schema_path: Path | None = None,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Build the selectable physical-sensor registry from raw and model contracts."""
    schema_path = raw_schema_path or project_root / "data/interim/raw_schema_summary.csv"
    schema = pd.read_csv(schema_path)
    if "column_name" not in schema.columns:
        raise ValueError(f"raw schema has no column_name: {schema_path}")
    if "manufacturer" in schema.columns:
        schema = schema.loc[schema["manufacturer"].astype(str).eq(MANUFACTURER_ID)].copy()
    features = load_model_feature_union(project_root)
    if not features:
        raise ValueError("no deployed model feature metadata was found")

    scoped_schema = schema
    if "substation_id" in schema:
        station_ids = pd.to_numeric(schema["substation_id"], errors="coerce")
        scoped_schema = schema.loc[station_ids.between(1, 31)].copy()
    expected_stations = (
        int(scoped_schema["substation_id"].dropna().nunique()) if "substation_id" in scoped_schema else 0
    )
    rows: list[dict[str, Any]] = []
    for source_column in sorted(schema["column_name"].dropna().astype(str).unique()):
        lowered = source_column.lower()
        if any(token in lowered for token in NON_SENSOR_TOKENS):
            continue
        linked = [
            feature
            for feature in features
            if feature == source_column or feature.startswith(f"{source_column}__")
        ]
        if not linked:
            continue
        sensor_type, unit = _sensor_type(source_column)
        available_rows = scoped_schema.loc[scoped_schema["column_name"].eq(source_column)]
        if "sample_non_null_count" in available_rows:
            available_rows = available_rows.loc[
                pd.to_numeric(available_rows["sample_non_null_count"], errors="coerce").fillna(0).gt(0)
            ]
        available = (
            int(available_rows["substation_id"].nunique())
            if "substation_id" in available_rows
            else 0
        )
        rows.append(
            {
                "sensor_key": source_column,
                "source_column": source_column,
                "label_ko": SENSOR_LABELS.get(source_column, source_column),
                "unit": unit,
                "display_order": len(rows) + 1,
                "sensor_type": sensor_type,
                "model_feature_prefix": f"{source_column}__",
                "nullable": available < expected_stations,
                "available_station_count": available,
                "model_feature_count": len(linked),
            }
        )
    registry = pd.DataFrame(rows)
    if registry.empty:
        raise ValueError("raw/model contract intersection has no physical numeric sensors")
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        registry.to_csv(output_path, index=False, encoding="utf-8", lineterminator="\n")
    return registry


def _boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_sensor_manifest(path: Path, registry: pd.DataFrame) -> pd.DataFrame:
    manifest = pd.read_csv(path)
    required = {
        "sensor_key",
        "source_column",
        "label_ko",
        "unit",
        "display_order",
        "sensor_type",
        "model_feature_prefix",
        "nullable",
        "enabled",
    }
    missing = sorted(required - set(manifest.columns))
    if missing:
        raise ValueError(f"sensor manifest is missing columns: {missing}")
    enabled = manifest.loc[manifest["enabled"].map(_boolean)].copy()
    if len(enabled) != 4:
        raise ValueError(f"sensor manifest must enable exactly four sensors; got {len(enabled)}")
    if enabled["sensor_key"].duplicated().any() or enabled["source_column"].duplicated().any():
        raise ValueError("enabled sensor keys and source columns must be unique")

    allowed = registry.set_index("source_column")
    unknown = sorted(set(enabled["source_column"].astype(str)) - set(allowed.index.astype(str)))
    if unknown:
        raise ValueError(f"manifest contains sensors outside the physical model registry: {unknown}")
    for source_column in enabled["source_column"].astype(str):
        if int(allowed.loc[source_column, "model_feature_count"]) <= 0:
            raise ValueError(f"sensor has no deployed model feature connection: {source_column}")
    return enabled.sort_values("display_order").reset_index(drop=True)


@dataclass(frozen=True)
class ReplayGenerationConfig:
    project_root: Path
    output_root: Path
    sensor_manifest_path: Path
    raw_root: Path
    donor_windows_path: Path
    warmup_start: pd.Timestamp = DEFAULT_WARMUP_START
    replay_start: pd.Timestamp = DEFAULT_REPLAY_START
    replay_end: pd.Timestamp = DEFAULT_REPLAY_END
    stations: tuple[int, ...] = DEFAULT_STATIONS
    seed: int = 20230710
    dataset_version: str = "predist-synthetic-replay-v2"
    fault_scenario_count: int = DEFAULT_FAULT_SCENARIO_COUNT
    quality_scenario_count: int = DEFAULT_QUALITY_SCENARIO_COUNT
    minimum_eligible_fault_scenarios: int = DEFAULT_MINIMUM_ELIGIBLE_FAULT_SCENARIOS
    overwrite: bool = False

    def validate(self) -> None:
        start = _timestamp(self.warmup_start)
        replay = _timestamp(self.replay_start)
        end = _timestamp(self.replay_end)
        if not start < replay < end:
            raise ValueError("expected warmup_start < replay_start < replay_end")
        if (replay - start) % SOURCE_INTERVAL:
            raise ValueError("warmup duration must align to the 10-minute source interval")
        if (end - start) % SOURCE_INTERVAL:
            raise ValueError("replay end must align to the 10-minute source interval")
        if (replay - start) % WINDOW_INTERVAL:
            raise ValueError("replay start must align to a 6-hour window boundary")
        if len(set(self.stations)) != len(self.stations) or not self.stations:
            raise ValueError("stations must be non-empty and unique")
        if any(station <= 0 for station in self.stations):
            raise ValueError("station IDs must be positive")
        if self.fault_scenario_count < 0 or self.quality_scenario_count < 0:
            raise ValueError("scenario counts must be non-negative")
        if self.minimum_eligible_fault_scenarios < 0:
            raise ValueError("minimum eligible fault scenarios must be non-negative")
        if (
            self.fault_scenario_count > 0
            and self.minimum_eligible_fault_scenarios > self.fault_scenario_count
        ):
            raise ValueError("minimum eligible faults cannot exceed fault scenario count")


def expected_dataset_counts(config: ReplayGenerationConfig) -> dict[str, int]:
    warmup_ticks = int((_timestamp(config.replay_start) - _timestamp(config.warmup_start)) / SOURCE_INTERVAL)
    replay_ticks = int((_timestamp(config.replay_end) - _timestamp(config.replay_start)) / SOURCE_INTERVAL)
    station_count = len(config.stations)
    return {
        "warmup_ticks": warmup_ticks,
        "replay_ticks": replay_ticks,
        "total_ticks": warmup_ticks + replay_ticks,
        "warmup_raw_rows": warmup_ticks * station_count,
        "replay_raw_rows": replay_ticks * station_count,
        "total_raw_rows": (warmup_ticks + replay_ticks) * station_count,
        "warmup_window_rows": warmup_ticks // WINDOW_TICKS * station_count,
        "replay_window_rows": replay_ticks // WINDOW_TICKS * station_count,
        "total_window_rows": (warmup_ticks + replay_ticks) // WINDOW_TICKS * station_count,
    }


def _read_csv_columns(path: Path) -> list[str]:
    return pd.read_csv(path, nrows=0).columns.astype(str).tolist()


def _merge_feature_source(
    base: pd.DataFrame,
    path: Path,
    feature_union: Sequence[str],
) -> pd.DataFrame:
    if not path.exists():
        return base
    keys = ["manufacturer", "substation_id", "window_start", "window_end"]
    header = _read_csv_columns(path)
    wanted = keys + [name for name in feature_union if name in header and name not in base.columns]
    extras = [name for name in ("anomaly_score",) if name in header and name not in wanted and name not in base.columns]
    if not set(keys).issubset(header) or len(wanted) == len(keys):
        return base
    source = pd.read_csv(path, usecols=wanted + extras, low_memory=False)
    source = source.loc[source["manufacturer"].astype(str).eq(MANUFACTURER_ID)]
    source = source.drop_duplicates(keys, keep="last")
    return base.merge(source, on=keys, how="left", validate="one_to_one")


def load_donor_feature_frame(
    project_root: Path,
    donor_windows_path: Path,
    feature_union: Sequence[str],
) -> pd.DataFrame:
    """Merge canonical windows and score artifacts into one complete donor matrix."""
    base = pd.read_csv(donor_windows_path, low_memory=False)
    base = base.loc[base["manufacturer"].astype(str).eq(MANUFACTURER_ID)].copy()
    if base.empty:
        raise ValueError("donor windows contain no manufacturer 1 rows")
    keys = ["manufacturer", "substation_id", "window_start", "window_end"]
    base = base.drop_duplicates(keys, keep="last")
    sources = (
        project_root / "artifacts/current_best/source_score_outputs/risk_scores.csv",
        project_root / "artifacts/current_best/source_score_outputs/leadtime_scores.csv",
        project_root / "output/merged_model_scores.csv",
        project_root / "output/m1_specialist_compact13_features.csv",
    )
    for source in sources:
        base = _merge_feature_source(base, source, feature_union)

    base = base.copy()

    base["window_start"] = pd.to_datetime(base["window_start"], errors="coerce")
    base["window_end"] = pd.to_datetime(base["window_end"], errors="coerce")
    base = base.dropna(subset=["window_start", "window_end"]).sort_values(
        ["substation_id", "window_end"]
    )
    if "anomaly_score" in base:
        grouped = base.groupby("substation_id", sort=False)["anomaly_score"]
        base["anomaly_score__lag1"] = grouped.shift(1)
        base["anomaly_score__lag2"] = grouped.shift(2)
        base["anomaly_score__delta1"] = base["anomaly_score"] - grouped.shift(1)
        base["anomaly_score__roll3_mean"] = grouped.transform(
            lambda values: values.rolling(3, min_periods=1).mean()
        )
    base["manufacturer_code"] = 0.0
    if "configuration_type" in base:
        names = sorted(base["configuration_type"].fillna("missing").astype(str).unique())
        codes = {name: float(index) for index, name in enumerate(names)}
        base["configuration_code"] = base["configuration_type"].fillna("missing").astype(str).map(codes)
    else:
        base["configuration_type"] = "missing"
        base["configuration_code"] = 0.0

    for feature in feature_union:
        if feature not in base:
            base[feature] = np.nan
        base[feature] = pd.to_numeric(base[feature], errors="coerce")
        median = base[feature].median()
        base[feature] = base[feature].fillna(0.0 if pd.isna(median) else float(median))
    if "season_bucket" not in base:
        base["season_bucket"] = base["window_start"].map(_season)
    if "label" not in base:
        base["label"] = "normal"
    for split in ("split_regime_based", "split_time_based"):
        if split not in base:
            base[split] = "train"
    base["donor_id"] = [
        hashlib.sha1("|".join(map(str, values)).encode("utf-8")).hexdigest()[:16]
        for values in base[keys].itertuples(index=False, name=None)
    ]
    return base.reset_index(drop=True)


def _scenario_times(
    start: pd.Timestamp,
    end: pd.Timestamp,
    count: int,
    *,
    margin: pd.Timedelta,
) -> list[pd.Timestamp]:
    if count <= 0 or end - start <= margin * 2:
        return []
    low = start + margin
    high = end - margin
    fractions = np.linspace(0.0, 1.0, count + 2)[1:-1]
    times = [low + (high - low) * float(value) for value in fractions]
    return [time.floor("6h") for time in times]


def _high_trajectory_heads(scored: pd.DataFrame) -> pd.DataFrame:
    required = {"donor_id", "substation_id", "_runtime_priority_level", "_runtime_priority_score"}
    if not required.issubset(scored.columns):
        return scored.iloc[0:0].copy()
    candidates = scored.loc[
        scored["_runtime_priority_level"].astype(str).isin({"high", "urgent", "critical"})
    ].copy()
    if candidates.empty:
        return candidates
    if "fault_event_id" in candidates:
        event = candidates["fault_event_id"]
        candidates["_trajectory_key"] = event.where(event.notna(), candidates["donor_id"]).astype(
            str
        )
    else:
        candidates["_trajectory_key"] = candidates["donor_id"].astype(str)
    return (
        candidates.sort_values("_runtime_priority_score", ascending=False)
        .drop_duplicates(["substation_id", "_trajectory_key"], keep="first")
        .reset_index(drop=True)
    )


def _model_guided_fault_trajectories(
    generation: ReplayGenerationConfig,
    holdout: pd.DataFrame,
    feature_union: Sequence[str],
) -> pd.DataFrame:
    required_models = (
        generation.project_root / "models/anomaly/isolation_forest.joblib",
        generation.project_root / "models/risk/risk_model_best.joblib",
        generation.project_root / "models/leadtime/leadtime_model_best.joblib",
    )
    if holdout.empty or not all(path.exists() for path in required_models):
        return holdout.iloc[0:0].copy()

    from heatgrid_ops.priority.inference import PriorityInferenceRuntime

    runtime = PriorityInferenceRuntime(model_root=generation.project_root / "models")
    rows = [
        {
            "manufacturer_id": MANUFACTURER_ID,
            "substation_id": int(row["substation_id"]),
            "configuration_type": str(row["configuration_type"]),
            "feature_values": {feature: float(row[feature]) for feature in feature_union},
        }
        for row in holdout.to_dict(orient="records")
    ]
    results = runtime.infer_batch(rows)
    scored = holdout.copy()
    scored["_runtime_priority_level"] = [str(result["priority_level"]) for result in results]
    scored["_runtime_priority_score"] = [float(result["priority_score"]) for result in results]
    scored["_runtime_usable"] = [bool(result["usable"]) for result in results]
    return _high_trajectory_heads(scored.loc[scored["_runtime_usable"]])


def build_scenario_manifest(
    generation: ReplayGenerationConfig,
    donors: pd.DataFrame,
    sensors: pd.DataFrame,
    feature_union: Sequence[str],
) -> pd.DataFrame:
    rng = np.random.default_rng(generation.seed + 17)
    replay_start = _timestamp(generation.replay_start)
    replay_end = _timestamp(generation.replay_end)
    holdout = donors.loc[
        donors["label"].astype(str).eq("pre_fault")
        & (
            donors["split_regime_based"].astype(str).eq("holdout")
            | donors["split_time_based"].astype(str).eq("holdout")
        )
    ]
    if holdout.empty:
        holdout = donors.loc[donors["label"].astype(str).eq("pre_fault")]
    if holdout.empty:
        holdout = donors
    normal = donors.loc[donors["label"].astype(str).eq("normal")]
    if normal.empty:
        normal = donors
    preferred_trajectories = _model_guided_fault_trajectories(
        generation,
        holdout,
        feature_union,
    )

    station_configurations: dict[int, str] = {}
    for station in generation.stations:
        station_rows = donors.loc[
            donors["substation_id"].eq(station), "configuration_type"
        ]
        station_configurations[station] = (
            str(station_rows.mode().iloc[0])
            if not station_rows.dropna().empty
            else "missing"
        )

    rows: list[dict[str, Any]] = []
    fault_times = _scenario_times(
        replay_start,
        replay_end,
        generation.fault_scenario_count,
        margin=pd.Timedelta(days=7),
    )
    shuffled_stations = list(generation.stations)
    rng.shuffle(shuffled_stations)
    for index, start in enumerate(fault_times):
        preferred_donor: pd.Series | None = None
        if not preferred_trajectories.empty:
            preferred_pool = preferred_trajectories.loc[
                preferred_trajectories["season_bucket"].astype(str).eq(_season(start))
            ]
            if not preferred_pool.empty:
                preferred_donor = preferred_pool.iloc[index % len(preferred_pool)]
        donor = (
            preferred_donor
            if preferred_donor is not None
            else holdout.iloc[index % len(holdout)]
        )
        donor_station = int(donor["substation_id"])
        donor_configuration = str(donor.get("configuration_type", "missing"))
        target_pool = [
            station
            for station in shuffled_stations
            if station_configurations.get(station) == donor_configuration
        ] or shuffled_stations
        station = target_pool[index % len(target_pool)]

        trajectory = holdout.loc[holdout["substation_id"].eq(donor_station)]
        fault_event_id = donor.get("fault_event_id")
        if "fault_event_id" in holdout and pd.notna(fault_event_id):
            same_event = holdout.loc[
                holdout["fault_event_id"].astype(str).eq(str(fault_event_id))
            ]
            if not same_event.empty:
                trajectory = same_event
        trajectory = trajectory.sort_values("window_start")
        donor_end = pd.Timestamp(donor.get("window_end"))
        if pd.notna(donor_end) and "window_end" in trajectory:
            leading = trajectory.loc[trajectory["window_end"].le(donor_end)]
            if not leading.empty:
                trajectory = leading
        donor_sequence = trajectory["donor_id"].astype(str).tolist() or [
            str(donor["donor_id"])
        ]

        target_normal = normal.loc[normal["substation_id"].eq(station)]
        if target_normal.empty:
            target_normal = normal
        effects: dict[str, float] = {}
        curves: dict[str, list[float]] = {}
        for sensor in sensors["source_column"].astype(str):
            mean_column = f"{sensor}__mean"
            delta_column = f"{sensor}__delta"
            baseline = (
                float(target_normal[mean_column].median())
                if mean_column in target_normal
                else 0.0
            )
            candidate = float(donor.get(mean_column, baseline)) - baseline
            spread = (
                float(target_normal[mean_column].std())
                if mean_column in target_normal
                else abs(candidate)
            )
            if not np.isfinite(candidate) or abs(candidate) < max(1e-9, spread * 0.05):
                candidate = float(donor.get(delta_column, spread * 0.5))
            limit = max(abs(spread) * 2.5, 1e-6)
            effects[sensor] = float(np.clip(candidate, -limit, limit))
            if mean_column in trajectory:
                series = pd.to_numeric(trajectory[mean_column], errors="coerce").dropna()
                if len(series) >= 2:
                    delta = float(series.iloc[-1] - series.iloc[0])
                    if abs(delta) > 1e-9:
                        curve = (series - float(series.iloc[0])) / delta
                        curve = curve.clip(-0.5, 1.5).astype(float).tolist()
                        curve[0] = 0.0
                        curve[-1] = 1.0
                        curves[sensor] = curve
        duration_hours = min(max(len(donor_sequence) * 6, 48), 96)
        effect_scale = FAULT_EFFECT_SCALES[index % len(FAULT_EFFECT_SCALES)]
        rows.append(
            {
                "scenario_id": f"fault-{index + 1:02d}",
                "scenario_type": "pre_fault_drift",
                "substation_id": station,
                "start": _iso(start),
                "end": _iso(min(start + pd.Timedelta(hours=duration_hours), replay_end)),
                "donor_id": donor["donor_id"],
                "donor_substation_id": donor_station,
                "donor_configuration_type": donor_configuration,
                "donor_fault_event_id": donor.get("fault_event_id", ""),
                "donor_sequence_json": json.dumps(
                    donor_sequence, separators=(",", ":")
                ),
                "sensor_effects_json": json.dumps(
                    effects, sort_keys=True, separators=(",", ":")
                ),
                "sensor_curve_json": json.dumps(
                    curves, sort_keys=True, separators=(",", ":")
                ),
                "effect_scale": effect_scale,
                "expected_behavior": "source_fault_trajectory_model_risk_change",
            }
        )

    quality_times = _scenario_times(
        replay_start, replay_end, generation.quality_scenario_count, margin=pd.Timedelta(days=2)
    )
    quality_types = ("missing", "frozen", "communication_gap")
    for index, start in enumerate(quality_times):
        station = shuffled_stations[(index + len(fault_times)) % len(shuffled_stations)]
        scenario_type = quality_types[index % len(quality_types)]
        rows.append(
            {
                "scenario_id": f"quality-{index + 1:02d}",
                "scenario_type": scenario_type,
                "substation_id": station,
                "start": _iso(start),
                "end": _iso(min(start + pd.Timedelta(hours=1), replay_end)),
                "donor_id": "",
                "donor_substation_id": "",
                "donor_configuration_type": "",
                "donor_fault_event_id": "",
                "donor_sequence_json": "[]",
                "sensor_effects_json": "{}",
                "sensor_curve_json": "{}",
                "effect_scale": 1.0,
                "expected_behavior": "data_quality_only_no_fault_truth",
            }
        )
    columns = [
        "scenario_id",
        "scenario_type",
        "substation_id",
        "start",
        "end",
        "donor_id",
        "donor_substation_id",
        "donor_configuration_type",
        "donor_fault_event_id",
        "donor_sequence_json",
        "sensor_effects_json",
        "sensor_curve_json",
        "effect_scale",
        "expected_behavior",
    ]
    return pd.DataFrame(rows, columns=columns)


def _slot_numbers(timestamps: pd.DatetimeIndex) -> np.ndarray:
    naive = timestamps.tz_localize(None) if timestamps.tz is not None else timestamps
    fixed = pd.to_datetime(
        {
            "year": np.full(len(naive), 2020),
            "month": naive.month,
            "day": naive.day,
            "hour": naive.hour,
            "minute": naive.minute,
        }
    )
    return ((fixed.dt.dayofyear.to_numpy() - 1) * 144 + fixed.dt.hour.to_numpy() * 6 + fixed.dt.minute.to_numpy() // 10).astype(int)


def _load_station_raw(path: Path, sensor_columns: Sequence[str]) -> pd.DataFrame:
    header = pd.read_csv(path, sep=";", nrows=0).columns.astype(str).tolist()
    if "timestamp" not in header:
        raise ValueError(f"{path.name} is missing required timestamp column")
    available_sensors = [sensor for sensor in sensor_columns if sensor in header]
    frame = pd.read_csv(
        path,
        sep=";",
        usecols=["timestamp", *available_sensors],
        low_memory=False,
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce").dt.floor("10min")
    for sensor in sensor_columns:
        frame[sensor] = (
            pd.to_numeric(frame[sensor], errors="coerce")
            if sensor in frame
            else np.nan
        )
    frame = frame.dropna(subset=["timestamp"]).groupby("timestamp", as_index=False)[list(sensor_columns)].mean()
    return frame.sort_values("timestamp").reset_index(drop=True)


def _build_fleet_fallback_plan(
    raw_root: Path,
    raw_schema_path: Path,
    sensor_columns: Sequence[str],
    stations: Sequence[int],
    *,
    station_context_path: Path | None = None,
) -> tuple[dict[int, dict[str, pd.DataFrame]], pd.DataFrame]:
    schema = pd.read_csv(raw_schema_path)
    if "manufacturer" in schema.columns:
        schema = schema.loc[schema["manufacturer"].astype(str).eq(MANUFACTURER_ID)].copy()
    if "sample_non_null_count" in schema:
        schema = schema.loc[
            pd.to_numeric(schema["sample_non_null_count"], errors="coerce").fillna(0).gt(0)
        ]
    configurations: dict[int, str] = {}
    if station_context_path is not None and station_context_path.exists():
        context = pd.read_csv(station_context_path)
        if {"substation_id", "predist_configuration_type"}.issubset(context.columns):
            configurations = {
                int(row.substation_id): str(row.predist_configuration_type)
                for row in context[["substation_id", "predist_configuration_type"]].itertuples(index=False)
            }
    fallbacks: dict[int, dict[str, pd.DataFrame]] = {int(station): {} for station in stations}
    provenance: list[dict[str, Any]] = []
    loaded: dict[tuple[int, tuple[str, ...]], pd.DataFrame] = {}
    for sensor in sensor_columns:
        candidate_series = schema.loc[
            schema["column_name"].astype(str).eq(sensor), "substation_id"
        ]
        candidates = sorted(
            set(pd.to_numeric(candidate_series, errors="coerce").dropna().astype(int).tolist())
        )
        if not candidates:
            continue
        for target_station in stations:
            if int(target_station) in candidates:
                continue
            target_configuration = configurations.get(int(target_station))
            same_configuration = [
                candidate
                for candidate in candidates
                if target_configuration and configurations.get(candidate) == target_configuration
            ]
            pool = same_configuration or candidates
            donor_station = min(pool, key=lambda candidate: (abs(candidate - int(target_station)), candidate))
            key = (donor_station, (sensor,))
            if key not in loaded:
                path = (
                    raw_root
                    / "manufacturer 1"
                    / "operational_data"
                    / f"substation_{donor_station}.csv"
                )
                loaded[key] = _load_station_raw(path, [sensor])
            fallbacks[int(target_station)][sensor] = loaded[key]
            provenance.append(
                {
                    "substation_id": int(target_station),
                    "sensor_key": sensor,
                    "donor_station_id": donor_station,
                    "target_configuration_type": target_configuration or "unknown",
                    "donor_configuration_type": configurations.get(donor_station, "unknown"),
                    "selection_policy": "same_configuration_nearest_station"
                    if same_configuration
                    else "nearest_available_station",
                }
            )
    columns = [
        "substation_id",
        "sensor_key",
        "donor_station_id",
        "target_configuration_type",
        "donor_configuration_type",
        "selection_policy",
    ]
    return fallbacks, pd.DataFrame(provenance, columns=columns)


def _stitch_value_blocks(
    source_values: pd.DataFrame,
    target_index: pd.DatetimeIndex,
    *,
    seed: int,
) -> np.ndarray:
    """Bootstrap joint raw-value blocks while preserving empirical signal dynamics."""
    regular = source_values.copy().sort_index()
    regular = regular.groupby(level=0).mean()
    full_index = pd.date_range(regular.index.min(), regular.index.max(), freq="10min")
    regular = regular.reindex(full_index).interpolate(
        method="time", limit=6, limit_area="inside"
    )
    source_index = regular.index
    midnight_positions = np.flatnonzero((source_index.hour == 0) & (source_index.minute == 0))
    if not len(midnight_positions):
        midnight_positions = np.arange(0, len(source_index), 144)
    complete = regular.notna().all(axis=1).to_numpy(dtype=bool)
    invalid_prefix = np.concatenate([[0], np.cumsum(~complete, dtype="int64")])
    rng = np.random.default_rng(seed)
    output = np.zeros((len(target_index), regular.shape[1]), dtype="float64")
    cursor = 0
    while cursor < len(target_index):
        days = int(rng.integers(1, 8))
        length = min(days * 144, len(target_index) - cursor)
        target_month = int(target_index[cursor].month)
        month_distance = np.minimum(
            (source_index[midnight_positions].month - target_month) % 12,
            (target_month - source_index[midnight_positions].month) % 12,
        )
        within_bounds = midnight_positions + length <= len(regular)
        valid_block = np.zeros(len(midnight_positions), dtype=bool)
        bounded = midnight_positions[within_bounds]
        valid_block[within_bounds] = (
            invalid_prefix[bounded + length] - invalid_prefix[bounded]
        ) == 0
        candidates = midnight_positions[(month_distance == 0) & valid_block]
        if not len(candidates):
            candidates = midnight_positions[(month_distance <= 1) & valid_block]
        if not len(candidates):
            candidates = midnight_positions[valid_block]
        if not len(candidates):
            raise ValueError(
                "source does not contain a complete one-day joint sensor block after "
                "limited-gap interpolation"
            )
        start = int(candidates[int(rng.integers(0, len(candidates)))])
        block = regular.iloc[start : start + length].to_numpy(dtype="float64", copy=True)
        if cursor and length:
            blend_count = min(6, length)
            boundary_offset = output[cursor - 1] - block[0]
            taper = np.linspace(1.0, 0.0, blend_count, endpoint=True)[:, None]
            block[:blend_count] += boundary_offset * taper
        output[cursor : cursor + length] = block
        cursor += length
    return output


def _generate_station_values(
    source: pd.DataFrame,
    target_index: pd.DatetimeIndex,
    sensors: pd.DataFrame,
    *,
    seed: int,
    fallback_sources: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    sensor_columns = sensors["source_column"].astype(str).tolist()
    source_index = pd.DatetimeIndex(source["timestamp"])
    numeric = source[sensor_columns].apply(pd.to_numeric, errors="coerce")
    numeric.index = source_index
    bound_sources: dict[str, pd.Series] = {}
    fallback_sources = fallback_sources or {}
    for sensor in sensor_columns:
        bound_source = numeric[sensor].dropna()
        if bound_source.empty:
            fallback = fallback_sources.get(sensor)
            if fallback is None:
                raise ValueError(f"source and fleet fallback have no usable values for sensor: {sensor}")
            fallback_series = pd.to_numeric(fallback[sensor], errors="coerce")
            fallback_series.index = pd.DatetimeIndex(fallback["timestamp"])
            fallback_series = fallback_series.groupby(level=0).mean().sort_index()
            if fallback_series.dropna().empty:
                raise ValueError(f"fleet fallback has no usable values for sensor: {sensor}")
            numeric[sensor] = fallback_series.reindex(source_index).to_numpy()
            bound_source = fallback_series.dropna()
        bound_sources[sensor] = bound_source
    values = _stitch_value_blocks(
        numeric[sensor_columns], target_index, seed=seed
    )

    for column_index, sensor in enumerate(sensor_columns):
        source_values = bound_sources[sensor]
        low = float(source_values.quantile(0.001))
        high = float(source_values.quantile(0.999))
        padding = max((high - low) * 0.1, 0.5)
        values[:, column_index] = np.clip(values[:, column_index], low - padding, high + padding)
        sensor_type = str(sensors.loc[sensors["source_column"].eq(sensor), "sensor_type"].iloc[0])
        if sensor_type in {"flow", "heat_power"}:
            values[:, column_index] = np.maximum(values[:, column_index], 0.0)
        if sensor_type.startswith("cumulative_"):
            source_deltas = source_values.diff().dropna()
            positive = source_deltas.loc[source_deltas.ge(0)]
            typical = float(positive.median()) if not positive.empty else 0.0
            increments = np.maximum(np.diff(values[:, column_index], prepend=values[0, column_index]), 0.0)
            cap = float(positive.quantile(0.999)) if not positive.empty else max(typical, 1.0)
            increments = np.clip(increments, 0.0, max(cap, typical, 1e-9))
            values[:, column_index] = float(source_values.iloc[0]) + np.cumsum(increments)

    if {"p_net_supply_temperature", "p_net_return_temperature"}.issubset(sensor_columns):
        supply = sensor_columns.index("p_net_supply_temperature")
        returned = sensor_columns.index("p_net_return_temperature")
        values[:, supply] = np.maximum(values[:, supply], values[:, returned] + 1.0)
    return pd.DataFrame(values, index=target_index, columns=sensor_columns)


def _apply_scenarios(
    values: pd.DataFrame,
    station: int,
    scenarios: pd.DataFrame,
    sensors: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    quality = np.full(len(values), "synthetic", dtype=object)
    scenario_ids = np.full(len(values), "", dtype=object)
    if scenarios.empty:
        return values, quality, scenario_ids
    selected = scenarios.loc[scenarios["substation_id"].eq(station)]
    for scenario in selected.itertuples(index=False):
        start = _timestamp(scenario.start)
        end = _timestamp(scenario.end)
        mask = (values.index >= start) & (values.index < end)
        positions = np.flatnonzero(mask)
        if not len(positions):
            continue
        scenario_ids[positions] = scenario.scenario_id
        if scenario.scenario_type == "pre_fault_drift":
            effects = json.loads(scenario.sensor_effects_json)
            curves = json.loads(getattr(scenario, "sensor_curve_json", "{}"))
            effect_scale = float(getattr(scenario, "effect_scale", 1.0) or 1.0)
            for sensor, effect in effects.items():
                if sensor in values:
                    curve = curves.get(sensor)
                    if isinstance(curve, list) and len(curve) >= 2:
                        profile = np.interp(
                            np.linspace(0.0, len(curve) - 1, len(positions)),
                            np.arange(len(curve), dtype="float64"),
                            np.asarray(curve, dtype="float64"),
                        )
                    else:
                        profile = np.linspace(0.0, 1.0, len(positions))
                    values.iloc[positions, values.columns.get_loc(sensor)] += (
                        profile * float(effect) * effect_scale
                    )
            quality[positions] = "synthetic_fault_pattern"
        elif scenario.scenario_type in {"missing", "communication_gap"}:
            values.iloc[positions, :] = np.nan
            quality[positions] = f"synthetic_{scenario.scenario_type}"
        elif scenario.scenario_type == "frozen":
            source_position = max(positions[0] - 1, 0)
            values.iloc[positions, :] = values.iloc[source_position].to_numpy()
            quality[positions] = "synthetic_frozen"

    sensor_columns = sensors["source_column"].astype(str).tolist()
    if {"p_net_supply_temperature", "p_net_return_temperature"}.issubset(sensor_columns):
        valid = values[["p_net_supply_temperature", "p_net_return_temperature"]].notna().all(axis=1)
        values.loc[valid, "p_net_supply_temperature"] = np.maximum(
            values.loc[valid, "p_net_supply_temperature"],
            values.loc[valid, "p_net_return_temperature"] + 1.0,
        )
    for sensor in sensor_columns:
        sensor_type = str(sensors.loc[sensors["source_column"].eq(sensor), "sensor_type"].iloc[0])
        if sensor_type in {"flow", "heat_power", "cumulative_energy", "cumulative_volume"}:
            values[sensor] = values[sensor].clip(lower=0.0)
        if sensor_type.startswith("cumulative_"):
            values[sensor] = values[sensor].cummax()
    return values, quality, scenario_ids


def _normal_donor_index(
    donors: pd.DataFrame,
    station: int,
    timestamp: pd.Timestamp,
    sequence: int,
) -> int:
    mask = donors["label"].astype(str).eq("normal")
    station_mask = donors["substation_id"].eq(station)
    season_mask = donors["season_bucket"].astype(str).eq(_season(timestamp))
    candidates = donors.index[mask & station_mask & season_mask]
    if not len(candidates):
        candidates = donors.index[mask & season_mask]
    if not len(candidates):
        candidates = donors.index[mask]
    if not len(candidates):
        candidates = donors.index
    return int(candidates[sequence % len(candidates)])


def _scenario_donor_index(
    donors: pd.DataFrame,
    scenario_id: str,
    scenarios: pd.DataFrame,
    window_start: pd.Timestamp,
) -> int | None:
    if not scenario_id or scenarios.empty:
        return None
    match = scenarios.loc[scenarios["scenario_id"].eq(scenario_id)]
    if match.empty or match.iloc[0]["scenario_type"] != "pre_fault_drift":
        return None
    scenario = match.iloc[0]
    sequence = json.loads(str(scenario.get("donor_sequence_json", "[]")))
    if sequence:
        start = _timestamp(scenario["start"])
        end = _timestamp(scenario["end"])
        duration = max((end - start).total_seconds(), 1.0)
        progress = float(
            np.clip(
                (window_start + WINDOW_INTERVAL - start).total_seconds() / duration,
                0.0,
                1.0,
            )
        )
        position = int(round(progress * (len(sequence) - 1)))
        donor_id = str(sequence[position])
    else:
        donor_id = str(scenario["donor_id"])
    indexes = donors.index[donors["donor_id"].eq(donor_id)]
    return int(indexes[0]) if len(indexes) else None


def _rolling_slope(values: np.ndarray) -> float:
    valid = np.isfinite(values)
    if valid.sum() < 2:
        return 0.0
    x = np.arange(len(values), dtype="float64")[valid]
    y = values[valid]
    return float(np.polyfit(x, y, 1)[0])


def _aggregate_windows(
    raw: pd.DataFrame,
    sensors: pd.DataFrame,
    donors: pd.DataFrame,
    feature_union: Sequence[str],
    scenarios: pd.DataFrame,
    generation: ReplayGenerationConfig,
) -> pd.DataFrame:
    sensor_columns = sensors["source_column"].astype(str).tolist()
    raw = raw.copy()
    raw["_window"] = raw["sequence"] // WINDOW_TICKS
    groups = raw.groupby("_window", sort=True)
    complete = [window_id for window_id, frame in groups if len(frame) == WINDOW_TICKS]
    rows: list[dict[str, Any]] = []
    feature_rows: list[pd.Series] = []
    aggregate_values: dict[str, list[float]] = {}

    for output_index, window_id in enumerate(complete):
        frame = groups.get_group(window_id).sort_values("sequence")
        start = _timestamp(frame["simulated_at"].iloc[0])
        end = start + WINDOW_INTERVAL
        scenario_ids = [value for value in frame["scenario_id"].astype(str).unique() if value]
        scenario_id = scenario_ids[0] if scenario_ids else ""
        donor_index = _scenario_donor_index(donors, scenario_id, scenarios, start)
        if donor_index is None:
            donor_index = _normal_donor_index(
                donors, int(frame["substation_id"].iloc[0]), start, output_index
            )
        feature_row = donors.loc[donor_index, list(feature_union)].copy()

        for sensor in sensor_columns:
            values = pd.to_numeric(frame[sensor], errors="coerce")
            stats = {
                "mean": values.mean(),
                "min": values.min(),
                "max": values.max(),
                "std": values.std(ddof=1),
                "first": values.dropna().iloc[0] if values.notna().any() else np.nan,
                "last": values.dropna().iloc[-1] if values.notna().any() else np.nan,
                "delta": values.dropna().iloc[-1] - values.dropna().iloc[0]
                if values.notna().any()
                else np.nan,
                "missing_count": float(values.isna().sum()),
                "missing_rate": float(values.isna().mean()),
            }
            for statistic, value in stats.items():
                name = f"{sensor}__{statistic}"
                aggregate_values.setdefault(name, []).append(float(value) if pd.notna(value) else np.nan)
                if name in feature_row.index:
                    feature_row[name] = value

        if {"p_net_supply_temperature", "p_net_return_temperature"}.issubset(sensor_columns):
            gap = frame["p_net_supply_temperature"] - frame["p_net_return_temperature"]
            for statistic, value in {
                "mean": gap.mean(),
                "last": gap.dropna().iloc[-1] if gap.notna().any() else np.nan,
                "max_abs": gap.abs().max(),
            }.items():
                name = f"network_temperature_gap__{statistic}"
                aggregate_values.setdefault(name, []).append(float(value) if pd.notna(value) else np.nan)
                if name in feature_row.index:
                    feature_row[name] = value

        midpoint = start + WINDOW_INTERVAL / 2
        day_of_week = midpoint.dayofweek
        day_of_year = midpoint.dayofyear
        hour = midpoint.hour
        time_values = {
            "day_of_week": float(day_of_week),
            "day_of_year": float(day_of_year),
            "hour_of_day": float(hour),
            "month": float(midpoint.month),
            "is_weekend": float(day_of_week >= 5),
            "is_heating_season": float(midpoint.month in {10, 11, 12, 1, 2, 3, 4}),
            "dow_cos": math.cos(2 * math.pi * day_of_week / 7),
            "dow_sin": math.sin(2 * math.pi * day_of_week / 7),
            "doy_cos": math.cos(2 * math.pi * day_of_year / 366),
            "doy_sin": math.sin(2 * math.pi * day_of_year / 366),
            "hour_cos": math.cos(2 * math.pi * hour / 24),
            "hour_sin": math.sin(2 * math.pi * hour / 24),
        }
        for name, value in time_values.items():
            if name in feature_row.index:
                feature_row[name] = value
        for name in ("winter", "spring", "summer", "autumn"):
            column = f"season_bucket__is__{name}"
            if column in feature_row.index:
                feature_row[column] = float(_season(midpoint) == name)

        observed = int(frame[sensor_columns].notna().any(axis=1).sum())
        station = int(frame["substation_id"].iloc[0])
        station_configurations = donors.loc[
            donors["substation_id"].eq(station), "configuration_type"
        ]
        target_configuration = (
            str(station_configurations.mode().iloc[0])
            if "configuration_type" in donors and not station_configurations.dropna().empty
            else str(donors.loc[donor_index].get("configuration_type", "missing"))
        )
        rows.append(
            {
                "dataset_version": generation.dataset_version,
                "sequence_end": int(frame["sequence"].iloc[-1]),
                "phase": str(frame["phase"].iloc[0]),
                "manufacturer_id": MANUFACTURER_ID,
                "substation_id": station,
                "configuration_type": target_configuration,
                "window_start": _iso(start),
                "window_end": _iso(end),
                "expected_count": WINDOW_TICKS,
                "observed_count": observed,
                "scenario_id": scenario_id,
            }
        )
        feature_rows.append(feature_row)

    metadata = pd.DataFrame(rows)
    features = pd.DataFrame(feature_rows).reset_index(drop=True)
    for column, values in aggregate_values.items():
        if column not in features:
            features[column] = values

    base_columns = list(aggregate_values)
    raw_derived_columns = set(base_columns)
    causal_operations = {
        "__lag1": lambda source: source.shift(1).fillna(source),
        "__lag2": lambda source: source.shift(2).fillna(source),
        "__delta1": lambda source: (source - source.shift(1)).fillna(0.0),
        "__roll3_mean": lambda source: source.rolling(3, min_periods=1).mean(),
    }
    for target in feature_union:
        for suffix, operation in causal_operations.items():
            if not target.endswith(suffix):
                continue
            base = target[: -len(suffix)]
            if base not in base_columns:
                continue
            source = pd.to_numeric(features[base], errors="coerce")
            features[target] = operation(source)
            raw_derived_columns.add(target)
            break

    horizon_sizes = {"roll24h": 4, "roll3d": 12, "roll7d": 28}
    for target in feature_union:
        matched_base = next((base for base in base_columns if target.startswith(f"{base}__roll")), None)
        if matched_base is None:
            continue
        suffix = target[len(matched_base) + 2 :]
        horizon = next((name for name in horizon_sizes if suffix.startswith(name + "_")), None)
        if horizon is None:
            continue
        operation = suffix[len(horizon) + 1 :]
        source = pd.to_numeric(features[matched_base], errors="coerce")
        size = horizon_sizes[horizon]
        rolling = source.rolling(size, min_periods=1)
        if operation == "mean":
            features[target] = rolling.mean()
            raw_derived_columns.add(target)
        elif operation == "delta":
            features[target] = (source - source.shift(size)).fillna(0.0)
            raw_derived_columns.add(target)
        elif operation == "slope":
            features[target] = rolling.apply(_rolling_slope, raw=True)
            raw_derived_columns.add(target)

    station_raw = raw.sort_values("sequence").reset_index(drop=True)
    sequence_positions = {
        int(value): index + 1 for index, value in enumerate(station_raw["sequence"].astype(int))
    }
    compact_suffixes = (
        "last_6h_mean_minus_prev_6h_mean",
        "last_12h_mean_minus_prev_12h_mean",
        "last_1d_mean_minus_prev_6d_mean",
        "last_1d_std_minus_prev_6d_std",
        "last_minus_first",
    )
    compact_targets = [
        target for target in feature_union if any(target.endswith(suffix) for suffix in compact_suffixes)
    ]
    raw_series = {
        sensor: pd.to_numeric(station_raw[sensor], errors="coerce") for sensor in sensor_columns
    }
    for target in compact_targets:
        sensor = next((name for name in sensor_columns if target.startswith(name + "__")), None)
        if sensor is None:
            continue
        series = raw_series[sensor]
        for row_index, sequence_end in enumerate(metadata["sequence_end"]):
            end_position = sequence_positions[int(sequence_end)]
            value: float | None = None
            if target == f"{sensor}__last_6h_mean_minus_prev_6h_mean" and end_position >= 72:
                value = float(series.iloc[end_position - 36 : end_position].mean() - series.iloc[end_position - 72 : end_position - 36].mean())
            elif target == f"{sensor}__last_12h_mean_minus_prev_12h_mean" and end_position >= 144:
                value = float(series.iloc[end_position - 72 : end_position].mean() - series.iloc[end_position - 144 : end_position - 72].mean())
            elif target == f"{sensor}__last_1d_mean_minus_prev_6d_mean" and end_position >= 1008:
                value = float(series.iloc[end_position - 144 : end_position].mean() - series.iloc[end_position - 1008 : end_position - 144].mean())
            elif target == f"{sensor}__last_1d_std_minus_prev_6d_std" and end_position >= 1008:
                value = float(series.iloc[end_position - 144 : end_position].std() - series.iloc[end_position - 1008 : end_position - 144].std())
            elif target == f"{sensor}__last_minus_first" and end_position >= 1008:
                context = series.iloc[end_position - 1008 : end_position].dropna()
                value = float(context.iloc[-1] - context.iloc[0]) if len(context) else None
            if value is not None and np.isfinite(value):
                features.iat[row_index, features.columns.get_loc(target)] = value

    features = features.apply(pd.to_numeric, errors="coerce").astype("float64")
    for column in features:
        if column in raw_derived_columns:
            features[column] = features[column].replace([np.inf, -np.inf], np.nan)
            continue
        fallback = float(donors[column].median()) if column in donors and donors[column].notna().any() else 0.0
        features[column] = features[column].replace([np.inf, -np.inf], np.nan).fillna(fallback)
    ordered_features = list(dict.fromkeys([*feature_union, *base_columns]))
    features = features.reindex(columns=ordered_features, fill_value=0.0)
    feature_set_version = "model-union-" + _json_hash(ordered_features)[:12]
    metadata["feature_set_version"] = feature_set_version
    hashes = []
    matrix = features.to_numpy(dtype="<f8", copy=False)
    for values in matrix:
        hashes.append(hashlib.sha256(values.tobytes()).hexdigest())
    metadata["feature_hash"] = hashes
    return pd.concat([metadata[WINDOW_METADATA_COLUMNS], features], axis=1)


def _write_parts(frame: pd.DataFrame, root: Path, category: str, station: int) -> None:
    timestamp_column = "simulated_at" if category == "raw" else "window_end"
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True).dt.tz_convert("Asia/Seoul")
    for month, part in frame.groupby(timestamps.dt.strftime("%Y-%m"), sort=True):
        path = root / ".parts" / category / str(month) / f"station_{station}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        part.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")


def _consolidate_parts(output_root: Path, category: str) -> list[dict[str, Any]]:
    source_root = output_root / ".parts" / category
    target_root = output_root / category
    target_root.mkdir(parents=True, exist_ok=True)
    shards: list[dict[str, Any]] = []
    if not source_root.exists():
        return shards
    timestamp_column = "simulated_at" if category == "raw" else "window_end"
    interval = SOURCE_INTERVAL if category == "raw" else WINDOW_INTERVAL
    sort_columns = [timestamp_column, "substation_id"]
    for month_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        frames = [pd.read_csv(path, low_memory=False) for path in sorted(month_dir.glob("*.csv"))]
        frame = pd.concat(frames, ignore_index=True).sort_values(sort_columns)
        target = target_root / f"{month_dir.name}.csv"
        frame.to_csv(target, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
        timestamps = pd.to_datetime(frame[timestamp_column], utc=True).dt.tz_convert("Asia/Seoul")
        shards.append(
            {
                "path": target.relative_to(output_root).as_posix(),
                "start": _iso(timestamps.min()),
                "end": _iso(timestamps.max() + interval),
                "row_count": int(len(frame)),
                "sha256": _sha256(target),
            }
        )
    return shards


def _prevalidate_fault_scenarios(
    output_root: Path,
    scenarios: pd.DataFrame,
    window_shards: Sequence[dict[str, Any]],
    feature_union: Sequence[str],
    project_root: Path,
    replay_start: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    scenarios = scenarios.copy()
    fault_mask = scenarios["scenario_type"].eq("pre_fault_drift")
    defaults: dict[str, Any] = {
        "runtime_validation_status": "not_applicable",
        "baseline_priority_median": np.nan,
        "event_priority_median": np.nan,
        "priority_delta": np.nan,
        "baseline_risk_median": np.nan,
        "event_risk_median": np.nan,
        "risk_delta": np.nan,
        "event_priority_peak": np.nan,
        "event_risk_peak": np.nan,
        "high_window_count": 0,
        "event_window_count": 0,
        "validated_high_at": "",
        "seek_eligible": False,
    }
    for column, value in defaults.items():
        scenarios[column] = value
    if not fault_mask.any():
        return scenarios, pd.DataFrame(), {"status": "no_fault_scenarios", "eligible_count": 0}

    required_models = (
        project_root / "models/anomaly/isolation_forest.joblib",
        project_root / "models/risk/risk_model_best.joblib",
        project_root / "models/leadtime/leadtime_model_best.joblib",
    )
    if not all(path.exists() for path in required_models):
        scenarios.loc[fault_mask, "runtime_validation_status"] = "skipped_model_bundle_missing"
        return scenarios, pd.DataFrame(), {
            "status": "skipped_model_bundle_missing",
            "eligible_count": 0,
        }

    selected_frames: list[pd.DataFrame] = []
    fault_rows = scenarios.loc[fault_mask]
    for shard in window_shards:
        shard_start = _timestamp(shard["start"])
        shard_end = _timestamp(shard["end"])
        relevant = fault_rows.loc[
            [
                _timestamp(row.end) > shard_start
                and _timestamp(row.start) - pd.Timedelta(days=7) < shard_end
                for row in fault_rows.itertuples(index=False)
            ]
        ]
        if relevant.empty:
            continue
        frame = pd.read_csv(output_root / shard["path"], low_memory=False)
        frame_end = pd.to_datetime(frame["window_end"], utc=True).dt.tz_convert("Asia/Seoul")
        for scenario in relevant.itertuples(index=False):
            lower = _timestamp(scenario.start) - pd.Timedelta(days=7)
            upper = _timestamp(scenario.end)
            mask = (
                frame["substation_id"].eq(int(scenario.substation_id))
                & frame_end.gt(lower)
                & frame_end.le(upper)
            )
            if mask.any():
                part = frame.loc[mask].copy()
                part["_evaluation_scenario_id"] = scenario.scenario_id
                selected_frames.append(part)
    if not selected_frames:
        scenarios.loc[fault_mask, "runtime_validation_status"] = "no_matching_windows"
        return scenarios, pd.DataFrame(), {"status": "no_matching_windows", "eligible_count": 0}

    evaluation = pd.concat(selected_frames, ignore_index=True).drop_duplicates(
        ["_evaluation_scenario_id", "substation_id", "window_end"]
    )
    from heatgrid_ops.priority.inference import PriorityInferenceRuntime

    runtime = PriorityInferenceRuntime(model_root=project_root / "models")
    runtime_rows = [
        {
            "manufacturer_id": str(row["manufacturer_id"]),
            "substation_id": int(row["substation_id"]),
            "configuration_type": str(row["configuration_type"]),
            "feature_values": {feature: float(row[feature]) for feature in feature_union},
        }
        for row in evaluation.to_dict(orient="records")
    ]
    results = runtime.infer_batch(runtime_rows)
    evaluation["_priority_score"] = [float(result["priority_score"]) for result in results]
    evaluation["_risk_score"] = [float(result["risk_score"]) for result in results]
    evaluation["_priority_level"] = [str(result["priority_level"]) for result in results]
    evaluation["_usable"] = [bool(result["usable"]) for result in results]
    level_order = {"low": 0, "medium": 1, "high": 2, "urgent": 3, "critical": 3}

    for scenario_index, scenario in scenarios.loc[fault_mask].iterrows():
        rows = evaluation.loc[evaluation["_evaluation_scenario_id"].eq(scenario["scenario_id"])].copy()
        ends = pd.to_datetime(rows["window_end"], utc=True).dt.tz_convert("Asia/Seoul")
        start = _timestamp(scenario["start"])
        baseline = rows.loc[ends.le(start) & rows["_usable"]]
        event = rows.loc[ends.gt(start) & rows["_usable"]]
        if baseline.empty or event.empty:
            scenarios.loc[scenario_index, "runtime_validation_status"] = "insufficient_windows"
            continue
        baseline_priority = float(baseline["_priority_score"].median())
        event_priority = float(event["_priority_score"].median())
        baseline_risk = float(baseline["_risk_score"].median())
        event_risk = float(event["_risk_score"].median())
        priority_delta = event_priority - baseline_priority
        risk_delta = event_risk - baseline_risk
        baseline_level = max(level_order.get(value, 0) for value in baseline["_priority_level"])
        event_level = max(level_order.get(value, 0) for value in event["_priority_level"])
        high_window_count = int(
            event["_priority_level"].map(level_order).ge(level_order["high"]).sum()
        )
        high_event = event.loc[
            event["_priority_level"].map(level_order).ge(level_order["high"])
        ]
        validated_high_at = (
            _iso(
                pd.to_datetime(high_event["window_end"], utc=True)
                .dt.tz_convert("Asia/Seoul")
                .min()
            )
            if not high_event.empty
            else ""
        )
        eligible = bool(
            event_level >= level_order["high"]
            and high_window_count >= 2
            and priority_delta >= 10.0
            and (risk_delta >= 0.05 or event_level > baseline_level)
        )
        scenarios.loc[scenario_index, [
            "runtime_validation_status",
            "baseline_priority_median",
            "event_priority_median",
            "priority_delta",
            "baseline_risk_median",
            "event_risk_median",
            "risk_delta",
            "event_priority_peak",
            "event_risk_peak",
            "high_window_count",
            "event_window_count",
            "validated_high_at",
            "seek_eligible",
        ]] = [
            "passed" if eligible else "rejected_no_validated_high_rise",
            baseline_priority,
            event_priority,
            priority_delta,
            baseline_risk,
            event_risk,
            risk_delta,
            float(event["_priority_score"].max()),
            float(event["_risk_score"].max()),
            high_window_count,
            int(len(event)),
            validated_high_at,
            eligible,
        ]

    seek = scenarios.loc[fault_mask & scenarios["seek_eligible"].map(_boolean)].copy()
    if not seek.empty:
        seek["event_at"] = seek["validated_high_at"]
        seek["seek_at"] = [
            _iso(max(_timestamp(value) - pd.Timedelta(hours=6), _timestamp(replay_start)))
            for value in seek["validated_high_at"]
        ]
        seek["label"] = "pre_fault_demo"
    seek = seek.reindex(
        columns=["scenario_id", "label", "seek_at", "event_at", "substation_id"]
    )
    return scenarios, seek, {
        "status": "completed",
        "candidate_count": int(fault_mask.sum()),
        "eligible_count": int(len(seek)),
        "minimum_eligible_count": 0,
        "evaluated_window_count": int(len(evaluation)),
    }


def generate_replay_dataset(generation: ReplayGenerationConfig) -> dict[str, Any]:
    generation.validate()
    output_root = generation.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        if not generation.overwrite:
            raise FileExistsError(f"output is not empty; pass overwrite=True: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    registry = build_model_sensor_registry(
        generation.project_root,
        output_path=output_root / "model_sensor_registry.csv",
    )
    sensors = load_sensor_manifest(generation.sensor_manifest_path, registry)
    output_manifest_path = output_root / "sensor_manifest.csv"
    manifest_columns = [
        "sensor_key",
        "source_column",
        "label_ko",
        "unit",
        "display_order",
        "sensor_type",
        "model_feature_prefix",
        "nullable",
        "enabled",
    ]
    sensors.assign(enabled=True)[manifest_columns].to_csv(
        output_manifest_path, index=False, encoding="utf-8", lineterminator="\n"
    )

    feature_union = load_model_feature_union(generation.project_root)
    donors = load_donor_feature_frame(
        generation.project_root, generation.donor_windows_path, feature_union
    )
    scenarios = build_scenario_manifest(generation, donors, sensors, feature_union)

    target_index = pd.date_range(
        _timestamp(generation.warmup_start),
        _timestamp(generation.replay_end),
        freq=SOURCE_INTERVAL,
        inclusive="left",
    )
    sensor_columns = sensors["source_column"].astype(str).tolist()
    fallback_sources_by_station, sensor_donor_map = _build_fleet_fallback_plan(
        generation.raw_root,
        generation.project_root / "data/interim/raw_schema_summary.csv",
        sensor_columns,
        generation.stations,
        station_context_path=generation.project_root
        / "data/external/predist_virtual_substation_sensor_metadata_m1.csv",
    )
    donor_map_path = output_root / "sensor_donor_map.csv"
    sensor_donor_map.to_csv(
        donor_map_path, index=False, encoding="utf-8", lineterminator="\n"
    )
    sequence = np.arange(len(target_index), dtype="int64")
    phase = np.where(target_index < _timestamp(generation.replay_start), "warmup", "replay")

    for station in generation.stations:
        source_path = generation.raw_root / "manufacturer 1" / "operational_data" / f"substation_{station}.csv"
        if not source_path.exists():
            raise FileNotFoundError(f"missing PreDist raw source: {source_path}")
        source = _load_station_raw(source_path, sensor_columns)
        values = _generate_station_values(
            source,
            target_index,
            sensors,
            seed=generation.seed + station * 1009,
            fallback_sources=fallback_sources_by_station.get(station, {}),
        )
        values, quality, scenario_ids = _apply_scenarios(values, station, scenarios, sensors)
        raw = pd.DataFrame(
            {
                "dataset_version": generation.dataset_version,
                "sequence": sequence,
                "phase": phase,
                "simulated_at": [_iso(value) for value in target_index],
                "manufacturer_id": MANUFACTURER_ID,
                "substation_id": station,
            }
        )
        for sensor in sensor_columns:
            raw[sensor] = values[sensor].to_numpy()
        raw["quality_flag"] = quality
        raw["is_synthetic"] = True
        raw["scenario_id"] = scenario_ids
        raw = raw[RAW_METADATA_COLUMNS + sensor_columns + RAW_TRAILING_COLUMNS]
        windows = _aggregate_windows(raw, sensors, donors, feature_union, scenarios, generation)
        _write_parts(raw, output_root, "raw", station)
        _write_parts(windows, output_root, "windows", station)

    raw_shards = _consolidate_parts(output_root, "raw")
    window_shards = _consolidate_parts(output_root, "windows")
    shutil.rmtree(output_root / ".parts", ignore_errors=True)
    scenarios, seek_points, scenario_validation = _prevalidate_fault_scenarios(
        output_root,
        scenarios,
        window_shards,
        feature_union,
        generation.project_root,
        _timestamp(generation.replay_start),
    )
    scenario_validation["minimum_eligible_count"] = (
        generation.minimum_eligible_fault_scenarios
    )
    scenarios.to_csv(
        output_root / "scenario_manifest.csv", index=False, encoding="utf-8", lineterminator="\n"
    )
    seek_points = seek_points.reindex(
        columns=["scenario_id", "label", "seek_at", "event_at", "substation_id"]
    )
    seek_points.to_csv(
        output_root / "seek_points.csv", index=False, encoding="utf-8", lineterminator="\n"
    )
    counts = expected_dataset_counts(generation)
    dataset_manifest = {
        "dataset_version": generation.dataset_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": generation.seed,
        "manufacturer_id": MANUFACTURER_ID,
        "source_raw_root": str(generation.raw_root.resolve()),
        "warmup_start": _iso(_timestamp(generation.warmup_start)),
        "replay_start": _iso(_timestamp(generation.replay_start)),
        "replay_end": _iso(_timestamp(generation.replay_end)),
        "source_interval_minutes": 10,
        "tick_seconds": 1,
        "window_ticks": WINDOW_TICKS,
        "window_hours": 6,
        "generation_policy": {
            "normal_pattern": "season_matched_1_to_7_day_joint_raw_value_block_bootstrap",
            "block_boundary_blend_ticks": 6,
            "station_offset": "inherited_from_station_or_configuration_matched_donor",
            "slow_drift": "inherited_from_contiguous_source_blocks",
            "noise": "empirical_joint_autocorrelation_preserved_without_additive_jitter",
            "missing_sensor_fallback": "same_configuration_nearest_available_station",
            "synthetic_use": "demo_and_integration_validation_only",
        },
        "expected_substations": len(generation.stations),
        "substation_ids": list(generation.stations),
        **counts,
        "sensor_manifest": "sensor_manifest.csv",
        "model_sensor_registry": "model_sensor_registry.csv",
        "scenario_manifest": "scenario_manifest.csv",
        "scenario_manifest_sha256": _sha256(output_root / "scenario_manifest.csv"),
        "seek_points": "seek_points.csv",
        "seek_points_sha256": _sha256(output_root / "seek_points.csv"),
        "sensor_donor_map": "sensor_donor_map.csv",
        "sensor_donor_map_sha256": _sha256(donor_map_path),
        "sensor_manifest_sha256": _sha256(output_manifest_path),
        "model_feature_count": len(feature_union),
        "model_feature_union_sha256": _json_hash(feature_union),
        "raw_shards": raw_shards,
        "window_shards": window_shards,
        "scenario_runtime_validation": scenario_validation,
        "minimum_eligible_fault_scenarios": generation.minimum_eligible_fault_scenarios,
        "validation_report": "validation_report.json",
    }
    manifest_path = output_root / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(dataset_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dataset_manifest


def _psi(reference: pd.Series, sample: pd.Series, bins: int = 10) -> float:
    reference = pd.to_numeric(reference, errors="coerce").dropna()
    sample = pd.to_numeric(sample, errors="coerce").dropna()
    if len(reference) < bins or len(sample) < bins:
        return float("nan")
    edges = np.unique(reference.quantile(np.linspace(0, 1, bins + 1)).to_numpy())
    if len(edges) < 3:
        return 0.0
    edges[0] = -np.inf
    edges[-1] = np.inf
    reference_rate = np.histogram(reference, bins=edges)[0] / len(reference)
    sample_rate = np.histogram(sample, bins=edges)[0] / len(sample)
    reference_rate = np.maximum(reference_rate, 1e-6)
    sample_rate = np.maximum(sample_rate, 1e-6)
    return float(np.sum((sample_rate - reference_rate) * np.log(sample_rate / reference_rate)))


def _ks_statistic(reference: pd.Series, sample: pd.Series) -> float:
    left = np.sort(pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype="float64"))
    right = np.sort(pd.to_numeric(sample, errors="coerce").dropna().to_numpy(dtype="float64"))
    if not len(left) or not len(right):
        return float("nan")
    values = np.sort(np.unique(np.concatenate([left, right])))
    left_cdf = np.searchsorted(left, values, side="right") / len(left)
    right_cdf = np.searchsorted(right, values, side="right") / len(right)
    return float(np.max(np.abs(left_cdf - right_cdf)))


def _sample_source_raw(
    raw_root: Path,
    stations: Sequence[int],
    sensor_columns: Sequence[str],
    *,
    rows_per_station: int = 2048,
    sensor_donor_map: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    distribution_samples: list[pd.DataFrame] = []
    temporal_samples: list[pd.DataFrame] = []
    donor_lookup: dict[tuple[int, str], int] = {}
    if sensor_donor_map is not None and not sensor_donor_map.empty:
        donor_lookup = {
            (int(row.substation_id), str(row.sensor_key)): int(row.donor_station_id)
            for row in sensor_donor_map.itertuples(index=False)
        }
    source_cache: dict[int, pd.DataFrame] = {}

    def load(station: int) -> pd.DataFrame:
        if station not in source_cache:
            path = raw_root / "manufacturer 1" / "operational_data" / f"substation_{station}.csv"
            source_cache[station] = _load_station_raw(path, sensor_columns).set_index("timestamp")
        return source_cache[station]

    for station in stations:
        path = raw_root / "manufacturer 1" / "operational_data" / f"substation_{station}.csv"
        if not path.exists():
            continue
        effective = load(int(station)).copy()
        for sensor in sensor_columns:
            if pd.to_numeric(effective[sensor], errors="coerce").notna().any():
                continue
            donor_station = donor_lookup.get((int(station), str(sensor)))
            if donor_station is None:
                continue
            donor = load(donor_station)
            effective[sensor] = donor[sensor].reindex(effective.index)
        effective = effective.reindex(
            pd.date_range(effective.index.min(), effective.index.max(), freq="10min")
        ).interpolate(method="time", limit=6, limit_area="inside")
        effective = effective.dropna(subset=list(sensor_columns)).reset_index(
            names="simulated_at"
        )
        if effective.empty:
            continue
        effective["_month"] = effective["simulated_at"].dt.month
        months = sorted(effective["_month"].unique())
        per_month = max(rows_per_station // max(len(months), 1), 1)
        station_distribution: list[pd.DataFrame] = []
        for month, group in effective.groupby("_month", sort=True):
            positions = np.unique(
                np.linspace(0, len(group) - 1, min(per_month, len(group)), dtype=int)
            )
            station_distribution.append(group.iloc[positions])
            ordered = group.sort_values("simulated_at")
            run_id = ordered["simulated_at"].diff().ne(SOURCE_INTERVAL).cumsum()
            longest = max((run for _, run in ordered.groupby(run_id, sort=False)), key=len)
            temporal = longest.head(128).copy()
            temporal["_temporal_segment"] = f"source:{station}:{int(month)}"
            temporal_samples.append(temporal)
        distribution = pd.concat(station_distribution, ignore_index=True)
        distribution["substation_id"] = station
        distribution_samples.append(distribution)
        for temporal in temporal_samples[-len(months) :]:
            temporal["substation_id"] = station
    distribution = (
        pd.concat(distribution_samples, ignore_index=True)
        if distribution_samples
        else pd.DataFrame()
    )
    temporal = (
        pd.concat(temporal_samples, ignore_index=True) if temporal_samples else pd.DataFrame()
    )
    return distribution, temporal


def _calendar_balanced_pair(
    reference: pd.DataFrame, sample: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match station-month exposure before whole-period distribution tests."""
    left = reference.copy()
    right = sample.copy()

    def kst_month(values: pd.Series) -> pd.Series:
        timestamps = pd.to_datetime(values, errors="coerce")
        if timestamps.dt.tz is None:
            timestamps = timestamps.dt.tz_localize("Asia/Seoul")
        else:
            timestamps = timestamps.dt.tz_convert("Asia/Seoul")
        return timestamps.dt.month

    left["_month"] = kst_month(left["simulated_at"])
    right["_month"] = kst_month(right["simulated_at"])
    balanced_left: list[pd.DataFrame] = []
    balanced_right: list[pd.DataFrame] = []
    common_stations = sorted(
        set(left["substation_id"].astype(int)) & set(right["substation_id"].astype(int))
    )
    for station_id in common_stations:
        station_left = left.loc[left["substation_id"].astype(int).eq(station_id)]
        station_right = right.loc[right["substation_id"].astype(int).eq(station_id)]
        common_months = sorted(
            set(station_left["_month"].astype(int))
            & set(station_right["_month"].astype(int))
        )
        if not common_months:
            continue
        for month in common_months:
            sample_size = min(
                int(station_left["_month"].eq(month).sum()),
                int(station_right["_month"].eq(month).sum()),
            )
            for source, destination in (
                (station_left, balanced_left),
                (station_right, balanced_right),
            ):
                group = source.loc[source["_month"].eq(month)]
                positions = np.unique(
                    np.linspace(0, len(group) - 1, sample_size, dtype=int)
                )
                destination.append(group.iloc[positions])
    empty_left = left.iloc[0:0]
    empty_right = right.iloc[0:0]
    return (
        pd.concat(balanced_left, ignore_index=True) if balanced_left else empty_left,
        pd.concat(balanced_right, ignore_index=True) if balanced_right else empty_right,
    )


def _distribution_audit(
    synthetic: pd.DataFrame,
    reference: pd.DataFrame,
    sensor_columns: Sequence[str],
    *,
    synthetic_temporal: pd.DataFrame,
    reference_temporal: pd.DataFrame,
) -> dict[str, Any]:
    if (
        synthetic.empty
        or reference.empty
        or synthetic_temporal.empty
        or reference_temporal.empty
    ):
        return {"status": "skipped_missing_samples"}
    reference, synthetic = _calendar_balanced_pair(reference, synthetic)
    sensor_metrics: dict[str, Any] = {}
    for sensor in sensor_columns:
        reference_sorted = reference_temporal.sort_values(["substation_id", "simulated_at"])
        synthetic_sorted = synthetic_temporal.sort_values(["substation_id", "simulated_at"])
        reference_group_keys = ["substation_id"]
        synthetic_group_keys = ["substation_id"]
        if "_temporal_segment" in reference_sorted:
            reference_group_keys.append("_temporal_segment")
        if "_temporal_segment" in synthetic_sorted:
            synthetic_group_keys.append("_temporal_segment")
        ref = pd.to_numeric(reference[sensor], errors="coerce")
        syn = pd.to_numeric(synthetic[sensor], errors="coerce")
        ref_delta = reference_sorted.groupby(reference_group_keys)[sensor].diff()
        syn_delta = synthetic_sorted.groupby(synthetic_group_keys)[sensor].diff()
        reference_autocorrelations = reference_sorted.groupby(reference_group_keys)[sensor].apply(
            lambda values: pd.to_numeric(values, errors="coerce").autocorr(lag=1)
        )
        synthetic_autocorrelations = synthetic_sorted.groupby(synthetic_group_keys)[sensor].apply(
            lambda values: pd.to_numeric(values, errors="coerce").autocorr(lag=1)
        )
        ref_autocorr = reference_autocorrelations.mean()
        syn_autocorr = synthetic_autocorrelations.mean()
        sensor_metrics[sensor] = {
            "psi": _psi(ref, syn),
            "ks_d": _ks_statistic(ref, syn),
            "delta_ks_d": _ks_statistic(ref_delta, syn_delta),
            "lag1_autocorr_reference": float(ref_autocorr) if pd.notna(ref_autocorr) else None,
            "lag1_autocorr_synthetic": float(syn_autocorr) if pd.notna(syn_autocorr) else None,
            "lag1_autocorr_abs_delta": float(abs(ref_autocorr - syn_autocorr))
            if pd.notna(ref_autocorr) and pd.notna(syn_autocorr)
            else None,
        }
    ref_corr = reference[list(sensor_columns)].apply(pd.to_numeric, errors="coerce").corr()
    syn_corr = synthetic[list(sensor_columns)].apply(pd.to_numeric, errors="coerce").corr()
    correlation_delta = (ref_corr - syn_corr).abs()
    values = correlation_delta.to_numpy(dtype="float64")
    max_correlation_delta = float(np.nanmax(values)) if np.isfinite(values).any() else None
    passed = all(
        (
            metric["psi"] < 0.20
            and metric["ks_d"] <= 0.15
            and metric["delta_ks_d"] <= 0.15
            and (
                metric["lag1_autocorr_abs_delta"] is None
                or metric["lag1_autocorr_abs_delta"] <= 0.15
            )
        )
        for metric in sensor_metrics.values()
        if np.isfinite(metric["psi"]) and np.isfinite(metric["ks_d"])
    ) and (max_correlation_delta is None or max_correlation_delta <= 0.15)
    return {
        "status": "passed" if passed else "failed",
        "thresholds": {
            "psi_lt": 0.20,
            "ks_d_lte": 0.15,
            "delta_ks_d_lte": 0.15,
            "lag1_autocorr_abs_delta_lte": 0.15,
            "correlation_abs_delta_lte": 0.15,
        },
        "sensors": sensor_metrics,
        "max_sensor_correlation_abs_delta": max_correlation_delta,
    }


def _raw_window_aggregates_for_validation(
    frame: pd.DataFrame,
    sensor_columns: Sequence[str],
) -> pd.DataFrame:
    work = frame[["substation_id", "sequence", *sensor_columns]].copy()
    work["_window"] = pd.to_numeric(work["sequence"], errors="raise").astype("int64") // WINDOW_TICKS
    for sensor in sensor_columns:
        work[sensor] = pd.to_numeric(work[sensor], errors="coerce")
    grouped = work.groupby(["substation_id", "_window"], sort=False)
    result = grouped["sequence"].max().rename("sequence_end").reset_index()
    for sensor in sensor_columns:
        values = grouped[sensor]
        statistics = pd.DataFrame(
            {
                f"{sensor}__mean": values.mean(),
                f"{sensor}__min": values.min(),
                f"{sensor}__max": values.max(),
                f"{sensor}__std": values.std(ddof=1),
                f"{sensor}__first": values.first(),
                f"{sensor}__last": values.last(),
                f"{sensor}__missing_count": values.apply(lambda item: float(item.isna().sum())),
                f"{sensor}__missing_rate": values.apply(lambda item: float(item.isna().mean())),
            }
        )
        statistics[f"{sensor}__delta"] = (
            statistics[f"{sensor}__last"] - statistics[f"{sensor}__first"]
        )
        result = result.merge(
            statistics.reset_index(), on=["substation_id", "_window"], how="left"
        )
    return result.drop(columns="_window")


def validate_replay_dataset(
    output_root: Path,
    *,
    project_root: Path | None = None,
    run_inference: bool = False,
) -> dict[str, Any]:
    manifest_path = output_root / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(output_root / manifest["model_sensor_registry"])
    sensors = load_sensor_manifest(output_root / manifest["sensor_manifest"], registry)
    sensor_columns = sensors["source_column"].astype(str).tolist()
    raw_required = set(RAW_METADATA_COLUMNS + sensor_columns + RAW_TRAILING_COLUMNS)
    window_required = set(WINDOW_METADATA_COLUMNS)
    errors: list[str] = []
    scenario_validation = manifest.get("scenario_runtime_validation") or {}
    minimum_eligible = int(
        manifest.get("minimum_eligible_fault_scenarios")
        or scenario_validation.get("minimum_eligible_count")
        or 1
    )
    if (
        scenario_validation.get("status") == "completed"
        and int(scenario_validation.get("candidate_count") or 0) > 0
        and int(scenario_validation.get("eligible_count") or 0) < minimum_eligible
    ):
        errors.append(
            "fault scenarios produced fewer model-approved seek points than required: "
            f"{int(scenario_validation.get('eligible_count') or 0)} < {minimum_eligible}"
        )
    raw_rows = 0
    window_rows = 0
    first_replay_raw_parts: list[pd.DataFrame] = []
    synthetic_samples: list[pd.DataFrame] = []
    synthetic_temporal_samples: list[pd.DataFrame] = []
    physical_violations = 0
    intentional_missing_values = 0
    unexpected_missing_values = 0
    replay_start = _timestamp(manifest["replay_start"])
    first_window_end = replay_start + WINDOW_INTERVAL
    raw_aggregate_parts: list[pd.DataFrame] = []
    previous_raw_end: pd.Timestamp | None = None
    previous_sequence: int | None = None
    previous_cumulative_values: dict[tuple[int, str], float] = {}
    for shard in manifest["raw_shards"]:
        path = output_root / shard["path"]
        if _sha256(path) != shard["sha256"]:
            errors.append(f"raw checksum mismatch: {shard['path']}")
        frame = pd.read_csv(path, low_memory=False)
        raw_rows += len(frame)
        if not raw_required.issubset(frame.columns):
            errors.append(f"raw columns missing: {shard['path']}")
        timestamps = pd.to_datetime(frame["simulated_at"], utc=True).dt.tz_convert("Asia/Seoul")
        actual_start = timestamps.min()
        actual_end = timestamps.max() + SOURCE_INTERVAL
        if _timestamp(shard["start"]) != actual_start or _timestamp(shard["end"]) != actual_end:
            errors.append(f"raw shard manifest range mismatch: {shard['path']}")
        if previous_raw_end is not None and actual_start != previous_raw_end:
            errors.append(f"raw shard ranges are not contiguous before: {shard['path']}")
        previous_raw_end = actual_end
        counts = frame.groupby(["sequence", timestamps]).size()
        if not counts.eq(int(manifest["expected_substations"])).all():
            errors.append(f"raw tick does not contain every substation: {shard['path']}")
        raw_aggregate_parts.append(_raw_window_aggregates_for_validation(frame, sensor_columns))
        unique_timestamps = pd.Series(timestamps.unique()).sort_values()
        if len(unique_timestamps) > 1 and not unique_timestamps.diff().dropna().eq(SOURCE_INTERVAL).all():
            errors.append(f"raw timestamps are not a continuous 10-minute grid: {shard['path']}")
        unique_sequences = np.sort(pd.to_numeric(frame["sequence"], errors="raise").unique())
        if len(unique_sequences) > 1 and not np.all(np.diff(unique_sequences) == 1):
            errors.append(f"raw sequence is not continuous: {shard['path']}")
        if previous_sequence is not None and int(unique_sequences[0]) != previous_sequence + 1:
            errors.append(f"raw sequence breaks at shard boundary: {shard['path']}")
        previous_sequence = int(unique_sequences[-1])
        first_mask = timestamps.ge(replay_start) & timestamps.lt(first_window_end)
        if first_mask.any():
            first_replay_raw_parts.append(frame.loc[first_mask].copy())
        normal = frame.loc[frame["quality_flag"].astype(str).eq("synthetic")].copy()
        if not normal.empty:
            stratified: list[pd.DataFrame] = []
            for _, group in normal.groupby("substation_id", sort=False):
                sample_count = min(
                    len(group), max(int(round(len(group) / 144)), 1)
                )
                positions = np.unique(
                    np.linspace(0, len(group) - 1, sample_count, dtype=int)
                )
                stratified.append(group.iloc[positions])
                ordered_group = group.sort_values("sequence")
                run_id = pd.to_numeric(ordered_group["sequence"], errors="coerce").diff().ne(1).cumsum()
                runs = [run for _, run in ordered_group.groupby(run_id, sort=False)]
                longest_run = max(runs, key=len).head(128).copy()
                longest_run["_temporal_segment"] = (
                    f"synthetic:{shard['path']}:{int(group['substation_id'].iloc[0])}"
                )
                synthetic_temporal_samples.append(longest_run)
            synthetic_samples.append(pd.concat(stratified, ignore_index=True))
        intentional_mask = frame["quality_flag"].astype(str).isin(
            {"synthetic_missing", "synthetic_communication_gap"}
        )
        intentional_missing_values += int(frame.loc[intentional_mask, sensor_columns].isna().sum().sum())
        unexpected_missing_values += int(
            frame.loc[~intentional_mask, sensor_columns].isna().sum().sum()
        )
        if {"p_net_supply_temperature", "p_net_return_temperature"}.issubset(sensor_columns):
            valid = frame[["p_net_supply_temperature", "p_net_return_temperature"]].notna().all(axis=1)
            physical_violations += int(
                (
                    frame.loc[valid, "p_net_supply_temperature"]
                    < frame.loc[valid, "p_net_return_temperature"] + 1.0 - 1e-8
                ).sum()
            )
        for sensor in sensor_columns:
            sensor_type = str(sensors.loc[sensors["source_column"].eq(sensor), "sensor_type"].iloc[0])
            if sensor_type in {"flow", "heat_power", "cumulative_energy", "cumulative_volume"}:
                physical_violations += int((pd.to_numeric(frame[sensor], errors="coerce") < 0).sum())
            if sensor_type.startswith("cumulative_"):
                ordered = frame.sort_values(["substation_id", "sequence"])
                decreases = ordered.groupby("substation_id")[sensor].diff()
                physical_violations += int((pd.to_numeric(decreases, errors="coerce") < -1e-9).sum())
                for station, station_values in ordered.groupby("substation_id", sort=False)[sensor]:
                    numeric_values = pd.to_numeric(station_values, errors="coerce").dropna()
                    if numeric_values.empty:
                        continue
                    key = (int(station), sensor)
                    if key in previous_cumulative_values and float(numeric_values.iloc[0]) < previous_cumulative_values[key] - 1e-9:
                        physical_violations += 1
                    previous_cumulative_values[key] = float(numeric_values.iloc[-1])
    raw_aggregate_lookup = pd.concat(raw_aggregate_parts, ignore_index=True).set_index(
        ["substation_id", "sequence_end"]
    )
    feature_union = load_model_feature_union(project_root) if project_root is not None else []
    first_visible_batch: pd.DataFrame | None = None
    normal_window_samples: list[pd.DataFrame] = []
    minimum_static_coverage = 1.0
    aggregate_mismatch_count = 0
    aggregate_checked_rows = 0
    previous_window_shard_end: pd.Timestamp | None = None
    for shard in manifest["window_shards"]:
        path = output_root / shard["path"]
        if _sha256(path) != shard["sha256"]:
            errors.append(f"window checksum mismatch: {shard['path']}")
        frame = pd.read_csv(path, low_memory=False)
        window_rows += len(frame)
        window_event_times = pd.to_datetime(frame["window_end"], utc=True).dt.tz_convert(
            "Asia/Seoul"
        )
        actual_shard_start = window_event_times.min()
        actual_shard_end = window_event_times.max() + WINDOW_INTERVAL
        if (
            _timestamp(shard["start"]) != actual_shard_start
            or _timestamp(shard["end"]) != actual_shard_end
        ):
            errors.append(f"window shard manifest range mismatch: {shard['path']}")
        if previous_window_shard_end is not None and actual_shard_start != previous_window_shard_end:
            errors.append(f"window shard ranges are not contiguous before: {shard['path']}")
        previous_window_shard_end = actual_shard_end
        if not window_required.issubset(frame.columns):
            errors.append(f"window columns missing: {shard['path']}")
        if feature_union and not set(feature_union).issubset(frame.columns):
            errors.append(f"model feature union is incomplete: {shard['path']}")
        if feature_union:
            minimum_static_coverage = min(
                minimum_static_coverage,
                len(set(feature_union) & set(frame.columns)) / len(feature_union),
            )
        if not pd.to_numeric(frame["expected_count"], errors="coerce").eq(WINDOW_TICKS).all():
            errors.append(f"window expected_count is not 36: {shard['path']}")
        if not pd.to_numeric(frame["sequence_end"], errors="coerce").mod(WINDOW_TICKS).eq(WINDOW_TICKS - 1).all():
            errors.append(f"window sequence boundary is not the 36th tick: {shard['path']}")
        keys = pd.MultiIndex.from_frame(
            frame[["substation_id", "sequence_end"]].astype("int64")
        )
        expected_aggregates = raw_aggregate_lookup.reindex(keys).reset_index(drop=True)
        aggregate_checked_rows += len(frame)
        if expected_aggregates.isna().all(axis=1).any():
            aggregate_mismatch_count += int(expected_aggregates.isna().all(axis=1).sum())
        for sensor in sensor_columns:
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
            ):
                column = f"{sensor}__{statistic}"
                actual = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")
                expected = pd.to_numeric(
                    expected_aggregates[column], errors="coerce"
                ).to_numpy(dtype="float64")
                aggregate_mismatch_count += int(
                    (~np.isclose(actual, expected, rtol=1e-12, atol=1e-12, equal_nan=True)).sum()
                )
        replay = frame.loc[frame["phase"].eq("replay")]
        if first_visible_batch is None and not replay.empty:
            first_end = replay["window_end"].min()
            first_visible_batch = replay.loc[replay["window_end"].eq(first_end)].copy()
        normal_replay = replay.loc[replay["scenario_id"].fillna("").astype(str).eq("")].copy()
        if not normal_replay.empty:
            normal_replay["_hour"] = pd.to_datetime(
                normal_replay["window_start"], utc=True
            ).dt.tz_convert("Asia/Seoul").dt.hour
            normal_window_samples.append(
                normal_replay.groupby(["_hour", "substation_id"], group_keys=False).head(1)
            )
    if raw_rows != int(manifest["total_raw_rows"]):
        errors.append(f"raw row count {raw_rows} != {manifest['total_raw_rows']}")
    if window_rows != int(manifest["total_window_rows"]):
        errors.append(f"window row count {window_rows} != {manifest['total_window_rows']}")
    if physical_violations:
        errors.append(f"physical constraints were violated {physical_violations} times")
    if unexpected_missing_values:
        errors.append(
            f"sensor values have {unexpected_missing_values} unintended missing cells outside quality scenarios"
        )
    if minimum_static_coverage < 1.0:
        errors.append(f"model feature union coverage is {minimum_static_coverage:.3f}, expected 1.0")
    if aggregate_mismatch_count:
        errors.append(
            f"raw/window aggregate parity failed for {aggregate_mismatch_count} cells"
        )

    timing_audit: dict[str, Any] = {
        "first_replay_raw": None,
        "first_replay_window_start": None,
        "first_replay_window_end": None,
        "raw_window_aggregate_parity": False,
    }
    first_raw = pd.concat(first_replay_raw_parts, ignore_index=True) if first_replay_raw_parts else pd.DataFrame()
    if not first_raw.empty:
        first_timestamp = _timestamp(first_raw["simulated_at"].min())
        timing_audit["first_replay_raw"] = _iso(first_timestamp)
        if first_timestamp != replay_start:
            errors.append(f"first replay raw timestamp {first_timestamp} != {replay_start}")
    if first_visible_batch is None:
        errors.append("no visible replay window was found")
    else:
        first_start = _timestamp(first_visible_batch["window_start"].min())
        first_end = _timestamp(first_visible_batch["window_end"].min())
        timing_audit["first_replay_window_start"] = _iso(first_start)
        timing_audit["first_replay_window_end"] = _iso(first_end)
        if first_start != replay_start or first_end != first_window_end:
            errors.append("first replay window is not [replay_start, replay_start + 6h)")
        if len(first_visible_batch) != int(manifest["expected_substations"]):
            errors.append("first replay window batch does not contain every substation")

    timing_audit["raw_window_aggregate_parity"] = aggregate_mismatch_count == 0
    timing_audit["aggregate_rows_checked"] = aggregate_checked_rows

    distribution_audit: dict[str, Any]
    if int(manifest["total_ticks"]) < 30 * 144:
        distribution_audit = {
            "status": "skipped_short_sample",
            "minimum_simulated_days": 30,
        }
    else:
        synthetic_sample = pd.concat(synthetic_samples, ignore_index=True)
        synthetic_temporal = pd.concat(synthetic_temporal_samples, ignore_index=True)
        reference, reference_temporal = _sample_source_raw(
            Path(manifest["source_raw_root"]),
            [int(value) for value in manifest["substation_ids"]],
            sensor_columns,
            sensor_donor_map=pd.read_csv(output_root / manifest["sensor_donor_map"]),
        )
        distribution_audit = _distribution_audit(
            synthetic_sample,
            reference,
            sensor_columns,
            synthetic_temporal=synthetic_temporal,
            reference_temporal=reference_temporal,
        )
        if distribution_audit["status"] == "failed":
            errors.append("PSI/KS/autocorrelation/sensor-correlation distribution audit failed")

    inference_summary: dict[str, Any] | None = None
    if run_inference:
        if project_root is None or first_visible_batch is None:
            errors.append("inference validation requires project_root and a replay window batch")
        else:
            from heatgrid_ops.priority.inference import PriorityInferenceRuntime

            inference_frame = (
                pd.concat(normal_window_samples, ignore_index=True)
                if normal_window_samples
                else first_visible_batch.copy()
            )
            if len(inference_frame) > 512:
                positions = np.unique(
                    np.linspace(0, len(inference_frame) - 1, 512, dtype=int)
                )
                inference_frame = inference_frame.iloc[positions]
            if inference_frame.empty:
                inference_frame = first_visible_batch
            features = [column for column in feature_union if column in inference_frame]
            rows = [
                {
                    "manufacturer_id": str(row["manufacturer_id"]),
                    "substation_id": int(row["substation_id"]),
                    "configuration_type": str(row["configuration_type"]),
                    "feature_values": {name: float(row[name]) for name in features},
                }
                for row in inference_frame.to_dict(orient="records")
            ]
            results = PriorityInferenceRuntime(model_root=project_root / "models").infer_batch(rows)
            coverage_keys = ("anomaly", "risk", "leadtime", "m1_specialist")
            inference_summary = {
                "batch_size": len(results),
                "usable_count": sum(bool(result["usable"]) for result in results),
                "minimum_coverage": {
                    key: min(float(result["feature_coverage"][key]) for result in results)
                    for key in coverage_keys
                },
            }
            generated_high_ratio = sum(
                str(result["priority_level"]) in {"high", "urgent", "critical"}
                for result in results
            ) / max(len(results), 1)
            baseline_path = project_root / "output/priority_scores.csv"
            baseline_high_ratio: float | None = None
            if baseline_path.exists():
                baseline = pd.read_csv(baseline_path, usecols=["label", "priority_level"])
                baseline = baseline.loc[baseline["label"].astype(str).eq("normal")]
                if not baseline.empty:
                    baseline_high_ratio = float(
                        baseline["priority_level"].astype(str).isin({"high", "urgent", "critical"}).mean()
                    )
            inference_summary["normal_high_or_urgent_ratio"] = generated_high_ratio
            inference_summary["reference_normal_high_or_urgent_ratio"] = baseline_high_ratio
            inference_summary["normal_high_or_urgent_delta"] = (
                generated_high_ratio - baseline_high_ratio if baseline_high_ratio is not None else None
            )
            if baseline_high_ratio is not None and generated_high_ratio - baseline_high_ratio > 0.05:
                errors.append("normal synthetic high/urgent ratio increased by more than 5 percentage points")
            if inference_summary["usable_count"] != len(results):
                errors.append("one or more generated window rows failed runtime usability")
    result = {
        "valid": not errors,
        "errors": errors,
        "raw_rows": raw_rows,
        "window_rows": window_rows,
        "timing_and_parity": timing_audit,
        "physical_constraint_violations": physical_violations,
        "intentional_quality_scenario_missing_values": intentional_missing_values,
        "unexpected_missing_values": unexpected_missing_values,
        "static_model_feature_coverage": minimum_static_coverage,
        "distribution": distribution_audit,
        "inference": inference_summary,
    }
    report_path = output_root / manifest.get("validation_report", "validation_report.json")
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise ValueError("dataset validation failed: " + "; ".join(errors))
    return result


def parse_station_spec(value: str) -> tuple[int, ...]:
    stations: list[int] = []
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            first, last = token.split("-", 1)
            stations.extend(range(int(first), int(last) + 1))
        else:
            stations.append(int(token))
    if not stations:
        raise ValueError("station specification is empty")
    if len(stations) != len(set(stations)):
        raise ValueError("station specification contains duplicates")
    return tuple(stations)
