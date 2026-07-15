from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


class ReplayDatasetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SensorDefinition:
    sensor_key: str
    source_column: str
    label_ko: str
    unit: str
    display_order: int
    sensor_type: str
    model_feature_prefix: str
    nullable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "sensor_key": self.sensor_key,
            "source_column": self.source_column,
            "label_ko": self.label_ko,
            "unit": self.unit,
            "display_order": self.display_order,
            "sensor_type": self.sensor_type,
            "model_feature_prefix": self.model_feature_prefix,
            "nullable": self.nullable,
        }


@dataclass(frozen=True, slots=True)
class ReplayPreset:
    scenario_id: str
    label: str
    seek_at: datetime
    event_at: datetime
    substation_id: int
    fleet_high_count: int
    fleet_medium_count: int
    fleet_low_count: int
    fleet_max_priority_score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "seek_at": self.seek_at.isoformat(),
            "event_at": self.event_at.isoformat(),
            "substation_id": self.substation_id,
            "fleet_high_count": self.fleet_high_count,
            "fleet_medium_count": self.fleet_medium_count,
            "fleet_low_count": self.fleet_low_count,
            "fleet_max_priority_score": self.fleet_max_priority_score,
        }


@dataclass(frozen=True, slots=True)
class ReplayShard:
    path: Path
    start: datetime | None = None
    end: datetime | None = None

    def overlaps(self, start: datetime, end: datetime | None) -> bool:
        if self.end is not None and self.end <= start:
            return False
        return end is None or self.start is None or self.start < end


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    dataset_version: str
    warmup_start: datetime
    replay_start: datetime
    replay_end: datetime
    expected_substations: int
    source_interval_minutes: int
    window_ticks: int
    tick_seconds: float
    raw_shards: tuple[ReplayShard, ...]
    window_shards: tuple[ReplayShard, ...]

    @property
    def source_interval(self) -> timedelta:
        return timedelta(minutes=self.source_interval_minutes)

    @property
    def window_duration(self) -> timedelta:
        return self.source_interval * self.window_ticks


@dataclass(frozen=True, slots=True)
class SensorReading:
    dataset_version: str
    sequence: int
    phase: str
    simulated_at: datetime
    manufacturer_id: str
    substation_id: int
    values: dict[str, float | None]
    quality: dict[str, str]
    is_synthetic: bool
    scenario_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "sequence": self.sequence,
            "phase": self.phase,
            "simulated_at": self.simulated_at.isoformat(),
            "manufacturer_id": self.manufacturer_id,
            "substation_id": self.substation_id,
            "values": self.values,
            "quality": self.quality,
            "is_synthetic": self.is_synthetic,
            "scenario_id": self.scenario_id,
        }


@dataclass(frozen=True, slots=True)
class SensorTick:
    sequence: int
    phase: str
    simulated_at: datetime
    readings: tuple[SensorReading, ...]


@dataclass(frozen=True, slots=True)
class WindowRecord:
    dataset_version: str
    sequence_end: int
    manufacturer_id: str
    substation_id: int
    window_start: datetime
    window_end: datetime
    expected_count: int
    observed_count: int
    feature_set_version: str
    feature_hash: str
    feature_values: dict[str, float]
    context: dict[str, Any]
    source_file: str

    def inference_input(self) -> dict[str, Any]:
        return {
            **self.context,
            "manufacturer_id": self.manufacturer_id,
            "substation_id": self.substation_id,
            "source_window_start": self.window_start,
            "source_window_end": self.window_end,
            "feature_set_version": self.feature_set_version,
            "feature_values": self.feature_values,
        }


@dataclass(frozen=True, slots=True)
class WindowBatch:
    window_start: datetime
    window_end: datetime
    records: tuple[WindowRecord, ...]


RAW_METADATA_COLUMNS = {
    "dataset_version",
    "sequence",
    "phase",
    "simulated_at",
    "manufacturer_id",
    "substation_id",
    "quality_flag",
    "is_synthetic",
    "scenario_id",
}
WINDOW_METADATA_COLUMNS = {
    "dataset_version",
    "sequence_end",
    "phase",
    "manufacturer_id",
    "manufacturer",
    "substation_id",
    "window_start",
    "window_end",
    "expected_count",
    "observed_count",
    "feature_set_version",
    "feature_hash",
    "configuration_type",
    "source_file",
    "season_bucket",
    "label",
    "fault_event_id",
    "scenario_id",
}


class CsvReplayDataset:
    """Streaming reader for generated monthly raw and window CSV shards."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        manifest_path = self.root / "dataset_manifest.json"
        if not manifest_path.is_file():
            manifest_path = self.root / "replay_manifest.json"
        if not manifest_path.is_file():
            raise ReplayDatasetError(
                f"dataset manifest not found under replay root: {self.root}"
            )
        payload = _read_json(manifest_path)
        sensor_path = self.root / str(payload.get("sensor_manifest") or "sensor_manifest.csv")
        self.sensors = _read_sensors(sensor_path)
        self.manifest = _read_manifest(self.root, payload)
        preset_path = self.root / str(payload.get("seek_points") or "seek_points.csv")
        self.presets = _read_presets(preset_path)
        self._validated_window_shards: set[Path] = set()
        self._validate_shards()

    def warmup_ticks(self, target: datetime) -> list[SensorTick]:
        normalized = _aware(target)
        start = max(self.manifest.warmup_start, normalized - timedelta(days=7))
        return list(self.iter_raw_ticks(start=start, end=normalized))

    def iter_raw_ticks(
        self,
        *,
        start: datetime,
        end: datetime | None = None,
    ) -> Iterator[SensorTick]:
        start = _aware(start)
        end = None if end is None else _aware(end)
        pending_at: datetime | None = None
        pending: list[SensorReading] = []
        previous_at: datetime | None = None
        for shard in self.manifest.raw_shards:
            if not shard.overlaps(start, end):
                continue
            for raw in _iter_csv(shard.path):
                simulated_at = _parse_time(_required(raw, "simulated_at"))
                if simulated_at < start:
                    continue
                if end is not None and simulated_at >= end:
                    if pending:
                        yield self._make_tick(pending_at, pending)
                    return
                reading = self._raw_reading(raw, simulated_at)
                if pending_at is None:
                    pending_at = simulated_at
                if simulated_at != pending_at:
                    tick = self._make_tick(pending_at, pending)
                    _validate_interval(previous_at, tick.simulated_at, self.manifest.source_interval)
                    yield tick
                    previous_at = tick.simulated_at
                    pending_at = simulated_at
                    pending = []
                pending.append(reading)
        if pending:
            tick = self._make_tick(pending_at, pending)
            _validate_interval(previous_at, tick.simulated_at, self.manifest.source_interval)
            yield tick

    def iter_window_batches(self, *, minimum_end: datetime) -> Iterator[WindowBatch]:
        minimum_end = _aware(minimum_end)
        pending_end: datetime | None = None
        pending: list[WindowRecord] = []
        for shard in self.manifest.window_shards:
            if shard.end is not None and shard.end < minimum_end:
                continue
            for raw in _iter_csv(shard.path):
                window_end = _parse_time(_required(raw, "window_end"))
                if window_end < minimum_end:
                    continue
                record = self._window_record(raw, shard.path, window_end)
                if pending_end is None:
                    pending_end = window_end
                if window_end != pending_end:
                    yield self._make_window_batch(pending)
                    pending_end = window_end
                    pending = []
                pending.append(record)
        if pending:
            yield self._make_window_batch(pending)

    def _raw_reading(
        self,
        raw: Mapping[str, str],
        simulated_at: datetime,
    ) -> SensorReading:
        values: dict[str, float | None] = {}
        quality: dict[str, str] = {}
        common_quality = (raw.get("quality_flag") or "synthetic").strip()
        permits_missing = common_quality in {
            "synthetic_missing",
            "synthetic_communication_gap",
        }
        for sensor in self.sensors:
            raw_value = raw.get(sensor.source_column)
            if raw_value is None:
                raw_value = raw.get(sensor.sensor_key)
            value = _optional_float(raw_value)
            if value is None and not sensor.nullable and not permits_missing:
                raise ReplayDatasetError(
                    f"non-nullable sensor {sensor.sensor_key!r} is missing at "
                    f"{simulated_at.isoformat()}"
                )
            values[sensor.sensor_key] = value
            quality[sensor.sensor_key] = (
                raw.get(f"{sensor.source_column}_quality") or common_quality
            ).strip()
        return SensorReading(
            dataset_version=(raw.get("dataset_version") or "").strip(),
            sequence=_int(raw.get("sequence"), "sequence"),
            phase=(raw.get("phase") or "replay").strip().lower(),
            simulated_at=simulated_at,
            manufacturer_id=_required(raw, "manufacturer_id"),
            substation_id=_int(raw.get("substation_id"), "substation_id"),
            values=values,
            quality=quality,
            is_synthetic=_bool(raw.get("is_synthetic"), default=True),
            scenario_id=_optional_text(raw.get("scenario_id")),
        )

    def _make_tick(
        self,
        simulated_at: datetime | None,
        readings: Sequence[SensorReading],
    ) -> SensorTick:
        if simulated_at is None:
            raise ReplayDatasetError("raw tick has no simulated_at")
        ordered = tuple(sorted(readings, key=lambda item: item.substation_id))
        ids = [item.substation_id for item in ordered]
        if len(ordered) != self.manifest.expected_substations:
            raise ReplayDatasetError(
                f"raw tick {simulated_at.isoformat()} has {len(ordered)} substations; "
                f"expected {self.manifest.expected_substations}"
            )
        if len(ids) != len(set(ids)):
            raise ReplayDatasetError(
                f"raw tick {simulated_at.isoformat()} has duplicate substations"
            )
        phases = {item.phase for item in ordered}
        if len(phases) != 1:
            raise ReplayDatasetError(
                f"raw tick {simulated_at.isoformat()} mixes phases: {sorted(phases)}"
            )
        versions = {item.dataset_version for item in ordered}
        sequences = {item.sequence for item in ordered}
        if versions != {self.manifest.dataset_version}:
            raise ReplayDatasetError(
                f"raw tick {simulated_at.isoformat()} dataset_version mismatch: {versions}"
            )
        if len(sequences) != 1:
            raise ReplayDatasetError(
                f"raw tick {simulated_at.isoformat()} mixes sequence values"
            )
        expected_phase = "warmup" if simulated_at < self.manifest.replay_start else "replay"
        if phases != {expected_phase}:
            raise ReplayDatasetError(
                f"raw tick {simulated_at.isoformat()} must have phase={expected_phase}"
            )
        return SensorTick(
            sequence=ordered[0].sequence,
            phase=ordered[0].phase,
            simulated_at=simulated_at,
            readings=ordered,
        )

    def _window_record(
        self,
        raw: Mapping[str, str],
        shard: Path,
        window_end: datetime,
    ) -> WindowRecord:
        validated = getattr(self, "_validated_window_shards", set())
        if shard not in validated:
            feature_names = set(raw) - WINDOW_METADATA_COLUMNS
            missing = [
                sensor.sensor_key
                for sensor in self.sensors
                if not any(
                    name == sensor.source_column
                    or name.startswith(sensor.model_feature_prefix)
                    for name in feature_names
                )
            ]
            if missing:
                raise ReplayDatasetError(
                    "enabled sensors are not connected to window model features: "
                    + ", ".join(missing)
                )
            validated.add(shard)
            self._validated_window_shards = validated
        feature_values: dict[str, float] = {}
        context: dict[str, Any] = {}
        for name, raw_value in raw.items():
            if name in WINDOW_METADATA_COLUMNS:
                if name in {"configuration_type", "season_bucket", "label", "fault_event_id", "scenario_id"}:
                    value = _optional_text(raw_value)
                    if value is not None:
                        context[name] = value
                continue
            value = _optional_float(raw_value)
            if value is not None:
                feature_values[name] = value
        if not feature_values:
            raise ReplayDatasetError(
                f"window row {window_end.isoformat()} has no numeric model features"
            )
        return WindowRecord(
            dataset_version=(raw.get("dataset_version") or self.manifest.dataset_version).strip(),
            sequence_end=_int(raw.get("sequence_end"), "sequence_end"),
            manufacturer_id=(
                raw.get("manufacturer_id") or raw.get("manufacturer") or ""
            ).strip(),
            substation_id=_int(raw.get("substation_id"), "substation_id"),
            window_start=_parse_time(_required(raw, "window_start")),
            window_end=window_end,
            expected_count=_int(
                raw.get("expected_count") or str(self.manifest.window_ticks),
                "expected_count",
            ),
            observed_count=_int(
                raw.get("observed_count") or str(self.manifest.window_ticks),
                "observed_count",
            ),
            feature_set_version=(raw.get("feature_set_version") or "unknown").strip(),
            feature_hash=(raw.get("feature_hash") or "").strip(),
            feature_values=feature_values,
            context=context,
            source_file=str(shard),
        )

    def _make_window_batch(self, records: Sequence[WindowRecord]) -> WindowBatch:
        ordered = tuple(sorted(records, key=lambda item: item.substation_id))
        first = ordered[0]
        if len(ordered) != self.manifest.expected_substations:
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} has {len(ordered)} substations; "
                f"expected {self.manifest.expected_substations}"
            )
        if len({item.substation_id for item in ordered}) != len(ordered):
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} has duplicate substations"
            )
        if any(item.window_start != first.window_start for item in ordered):
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} mixes window_start values"
            )
        if first.window_end - first.window_start != self.manifest.window_duration:
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} must be exactly 6 hours"
            )
        if any(item.dataset_version != self.manifest.dataset_version for item in ordered):
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} dataset_version mismatch"
            )
        if any(item.expected_count != self.manifest.window_ticks for item in ordered):
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} expected_count must be "
                f"{self.manifest.window_ticks}"
            )
        if any(
            item.observed_count < 0 or item.observed_count > item.expected_count
            for item in ordered
        ):
            raise ReplayDatasetError(
                f"window {first.window_end.isoformat()} has invalid observed_count"
            )
        return WindowBatch(first.window_start, first.window_end, ordered)

    def _validate_shards(self) -> None:
        if not self.manifest.raw_shards:
            raise ReplayDatasetError("replay manifest has no raw_shards")
        if not self.manifest.window_shards:
            raise ReplayDatasetError("replay manifest has no window_shards")
        missing = [
            shard.path
            for shard in (*self.manifest.raw_shards, *self.manifest.window_shards)
            if not shard.path.is_file()
        ]
        if missing:
            raise ReplayDatasetError(
                "replay shard files are missing: " + ", ".join(str(path) for path in missing)
            )


def _read_sensors(path: Path) -> tuple[SensorDefinition, ...]:
    if not path.is_file():
        raise ReplayDatasetError(f"sensor manifest not found: {path}")
    sensors: list[SensorDefinition] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if "enabled" in row and not _bool(row.get("enabled"), default=False):
                continue
            sensor = SensorDefinition(
                sensor_key=_required(row, "sensor_key"),
                source_column=_required(row, "source_column"),
                label_ko=_required(row, "label_ko"),
                unit=(row.get("unit") or "").strip(),
                display_order=_int(row.get("display_order"), "display_order"),
                sensor_type=_required(row, "sensor_type"),
                model_feature_prefix=_required(row, "model_feature_prefix"),
                nullable=_bool(row.get("nullable"), default=False),
            )
            sensors.append(sensor)
    sensors.sort(key=lambda item: (item.display_order, item.sensor_key))
    if len(sensors) != 4:
        raise ReplayDatasetError(
            f"sensor_manifest.csv must enable exactly 4 sensors; found {len(sensors)}"
        )
    keys = [item.sensor_key for item in sensors]
    columns = [item.source_column for item in sensors]
    if len(keys) != len(set(keys)) or len(columns) != len(set(columns)):
        raise ReplayDatasetError("enabled sensor keys and source columns must be unique")
    return tuple(sensors)


def _read_manifest(root: Path, payload: Mapping[str, Any]) -> ReplayManifest:
    replay_start = _parse_time(str(payload.get("replay_start") or "2023-01-08T00:00:00+09:00"))
    warmup_start = _parse_time(str(payload.get("warmup_start") or "2023-01-01T00:00:00+09:00"))
    replay_end = _parse_time(str(payload.get("replay_end") or "2026-01-08T00:00:00+09:00"))
    if not warmup_start < replay_start < replay_end:
        raise ReplayDatasetError("manifest time range must satisfy warmup_start < replay_start < replay_end")
    expected_substations = int(payload.get("expected_substations") or 31)
    source_interval_minutes = int(payload.get("source_interval_minutes") or 10)
    window_ticks = int(payload.get("window_ticks") or 36)
    tick_seconds = float(payload.get("tick_seconds") or 1.0)
    if expected_substations <= 0 or source_interval_minutes <= 0 or window_ticks <= 0:
        raise ReplayDatasetError("manifest counts and intervals must be positive")
    if not math.isfinite(tick_seconds) or tick_seconds <= 0:
        raise ReplayDatasetError("tick_seconds must be a positive finite number")
    fixed_warmup_start = datetime(2023, 1, 1, tzinfo=SEOUL)
    fixed_replay_start = datetime(2023, 1, 8, tzinfo=SEOUL)
    fixed_replay_end = datetime(2026, 1, 8, tzinfo=SEOUL)
    fixed = {
        "warmup_start": (warmup_start, fixed_warmup_start),
        "replay_start": (replay_start, fixed_replay_start),
        "replay_end": (replay_end, fixed_replay_end),
        "expected_substations": (expected_substations, 31),
        "source_interval_minutes": (source_interval_minutes, 10),
        "window_ticks": (window_ticks, 36),
    }
    mismatches = [name for name, (actual, expected) in fixed.items() if actual != expected]
    if mismatches:
        raise ReplayDatasetError(
            "dataset manifest violates the fixed replay contract: "
            + ", ".join(mismatches)
        )
    return ReplayManifest(
        dataset_version=str(payload.get("dataset_version") or "predist-replay-v1"),
        warmup_start=warmup_start,
        replay_start=replay_start,
        replay_end=replay_end,
        expected_substations=expected_substations,
        source_interval_minutes=source_interval_minutes,
        window_ticks=window_ticks,
        tick_seconds=tick_seconds,
        raw_shards=_shard_paths(root, payload.get("raw_shards"), fallback="raw"),
        window_shards=_shard_paths(
            root,
            payload.get("window_shards"),
            fallback="windows",
        ),
    )


def _shard_paths(root: Path, value: Any, *, fallback: str) -> tuple[ReplayShard, ...]:
    if not isinstance(value, list):
        return tuple(
            ReplayShard(path=path)
            for path in sorted((root / fallback).glob("*.csv"))
        )
    shards: list[ReplayShard] = []
    for item in value:
        relative = item.get("path") if isinstance(item, dict) else item
        if not isinstance(relative, str) or not relative.strip():
            raise ReplayDatasetError("each shard must be a path string or an object with path")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ReplayDatasetError(f"shard escapes dataset root: {relative}") from exc
        start = None
        end = None
        if isinstance(item, dict):
            if item.get("start"):
                start = _parse_time(str(item["start"]))
            if item.get("end"):
                end = _parse_time(str(item["end"]))
            if start is not None and end is not None and start >= end:
                raise ReplayDatasetError(f"shard start must precede end: {relative}")
        shards.append(ReplayShard(path=candidate, start=start, end=end))
    return tuple(shards)


def _read_presets(path: Path) -> tuple[ReplayPreset, ...]:
    if not path.is_file():
        return ()
    presets = [
        ReplayPreset(
            scenario_id=_required(row, "scenario_id"),
            label=_required(row, "label"),
            seek_at=_parse_time(_required(row, "seek_at")),
            event_at=_parse_time(_required(row, "event_at")),
            substation_id=int(_required(row, "substation_id")),
            fleet_high_count=int(row.get("fleet_high_count") or 0),
            fleet_medium_count=int(row.get("fleet_medium_count") or 0),
            fleet_low_count=int(row.get("fleet_low_count") or 0),
            fleet_max_priority_score=float(row.get("fleet_max_priority_score") or 0.0),
        )
        for row in _iter_csv(path)
    ]
    return tuple(
        sorted(
            presets,
            key=lambda preset: (
                -preset.fleet_high_count,
                -preset.fleet_medium_count,
                preset.event_at,
            ),
        )
    )


def _iter_csv(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ReplayDatasetError(f"expected JSON object: {path}")
    return payload


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayDatasetError(f"invalid ISO timestamp: {value!r}") from exc
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SEOUL)
    return value.astimezone(SEOUL)


def _validate_interval(
    previous_at: datetime | None,
    current_at: datetime,
    expected: timedelta,
) -> None:
    if previous_at is not None and current_at - previous_at != expected:
        raise ReplayDatasetError(
            f"raw ticks are not {int(expected.total_seconds() // 60)} minutes apart: "
            f"{previous_at.isoformat()} -> {current_at.isoformat()}"
        )


def _required(row: Mapping[str, Any], name: str) -> str:
    value = row.get(name)
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        raise ReplayDatasetError(f"required CSV field is empty: {name}")
    return normalized


def _optional_text(value: Any) -> str | None:
    normalized = "" if value is None else str(value).strip()
    return normalized or None


def _optional_float(value: Any) -> float | None:
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered in {"true", "false"}:
        return 1.0 if lowered == "true" else 0.0
    try:
        number = float(normalized)
    except ValueError as exc:
        raise ReplayDatasetError(f"invalid numeric CSV value: {value!r}") from exc
    if not math.isfinite(number):
        return None
    return number


def _int(value: Any, name: str) -> int:
    normalized = "" if value is None else str(value).strip()
    try:
        return int(normalized)
    except ValueError as exc:
        raise ReplayDatasetError(f"invalid integer field {name}: {value!r}") from exc


def _bool(value: Any, *, default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ReplayDatasetError(f"invalid boolean value: {value!r}")
