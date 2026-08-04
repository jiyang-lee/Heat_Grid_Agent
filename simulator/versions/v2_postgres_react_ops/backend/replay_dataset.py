from __future__ import annotations

import csv
import hashlib
import json
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


class ReplayDatasetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    dataset_version: str
    warmup_start: datetime
    replay_start: datetime
    replay_end: datetime
    expected_substations: int
    source_interval: timedelta
    window_ticks: int
    tick_seconds: float
    raw_shards: tuple[dict[str, Any], ...]
    window_shards: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class SensorTick:
    sequence: int
    phase: str
    simulated_at: datetime
    readings: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class WindowBatch:
    window_start: datetime
    window_end: datetime
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ImportedReplayPackage:
    package_sha256: str
    root: Path
    manifest: ReplayManifest
    files: tuple[dict[str, Any], ...]


def load_manifest(root: str | Path) -> ReplayManifest:
    dataset_root = Path(root).expanduser().resolve()
    path = dataset_root / "dataset_manifest.json"
    if not path.is_file():
        raise ReplayDatasetError(f"dataset manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = (
        "dataset_version",
        "warmup_start",
        "replay_start",
        "replay_end",
        "expected_substations",
        "source_interval_minutes",
        "window_ticks",
        "raw_shards",
        "window_shards",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise ReplayDatasetError(f"dataset manifest missing: {missing}")
    manifest = ReplayManifest(
        dataset_version=str(payload["dataset_version"]),
        warmup_start=_parse_time(payload["warmup_start"]),
        replay_start=_parse_time(payload["replay_start"]),
        replay_end=_parse_time(payload["replay_end"]),
        expected_substations=int(payload["expected_substations"]),
        source_interval=timedelta(minutes=int(payload["source_interval_minutes"])),
        window_ticks=int(payload["window_ticks"]),
        tick_seconds=float(payload.get("tick_seconds", 1.0)),
        raw_shards=tuple(_shards(payload["raw_shards"])),
        window_shards=tuple(_shards(payload["window_shards"])),
    )
    if manifest.expected_substations != 31:
        raise ReplayDatasetError("replay dataset must contain exactly 31 substations")
    if manifest.source_interval != timedelta(minutes=10):
        raise ReplayDatasetError("replay dataset source interval must be 10 minutes")
    if manifest.window_ticks != 36:
        raise ReplayDatasetError("replay dataset window must be exactly 36 ticks")
    if manifest.replay_end <= manifest.replay_start:
        raise ReplayDatasetError("replay end must be after replay start")
    return manifest


def import_replay_package(
    package_path: str | Path,
    *,
    destination_root: str | Path,
    max_files: int = 256,
    max_uncompressed_bytes: int = 6 * 1024 * 1024 * 1024,
) -> ImportedReplayPackage:
    source = Path(package_path).expanduser().resolve()
    if not source.is_file():
        raise ReplayDatasetError(f"replay package not found: {source}")
    package_sha256 = _sha256_file(source)
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > max_files:
            raise ReplayDatasetError("replay package has too many files")
        if sum(member.file_size for member in members) > max_uncompressed_bytes:
            raise ReplayDatasetError("replay package expands beyond the configured limit")
        for member in members:
            if _unsafe_member(member):
                raise ReplayDatasetError(f"unsafe replay package member: {member.filename}")
        target_base = Path(destination_root).expanduser().resolve()
        temporary = target_base / ".importing" / package_sha256
        final_root = target_base / "datasets"
        temporary.mkdir(parents=True, exist_ok=True)
        for member in members:
            archive.extract(member, temporary)
    roots = [path for path in temporary.rglob("dataset_manifest.json")]
    if len(roots) != 1:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ReplayDatasetError("replay package must contain exactly one dataset manifest")
    extracted_root = roots[0].parent
    manifest = load_manifest(extracted_root)
    files = _verify_manifest_files(extracted_root, manifest)
    final_dataset_root = final_root / manifest.dataset_version
    final_dataset_root.parent.mkdir(parents=True, exist_ok=True)
    if final_dataset_root.exists():
        if final_dataset_root.resolve() != extracted_root.resolve():
            shutil.rmtree(temporary, ignore_errors=True)
        return ImportedReplayPackage(package_sha256, final_dataset_root, manifest, tuple(files))
    shutil.move(str(extracted_root), str(final_dataset_root))
    shutil.rmtree(temporary, ignore_errors=True)
    return ImportedReplayPackage(package_sha256, final_dataset_root, manifest, tuple(files))


class CsvReplayDataset:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.manifest = load_manifest(self.root)
        self.sensors = _load_sensors(self.root / "sensor_manifest.csv")

    def warmup_ticks(self, target: datetime) -> list[SensorTick]:
        start = max(self.manifest.warmup_start, target - timedelta(days=7))
        return list(self.iter_raw_ticks(start=start, end=target))

    def iter_raw_ticks(
        self, *, start: datetime, end: datetime | None = None
    ) -> Iterator[SensorTick]:
        pending_at: datetime | None = None
        readings: list[dict[str, Any]] = []
        expected_at: datetime | None = None
        for shard in self.manifest.raw_shards:
            if _parse_time(shard["end"]) <= start or (
                end is not None and _parse_time(shard["start"]) >= end
            ):
                continue
            for row in _csv_rows(self.root / shard["path"]):
                simulated_at = _parse_time(row["simulated_at"])
                if simulated_at < start:
                    continue
                if end is not None and simulated_at >= end:
                    if readings:
                        yield _make_tick(pending_at, readings, expected_at, self.manifest)
                    return
                if pending_at is None:
                    pending_at = simulated_at
                if simulated_at != pending_at:
                    tick = _make_tick(pending_at, readings, expected_at, self.manifest)
                    yield tick
                    expected_at = tick.simulated_at + self.manifest.source_interval
                    pending_at, readings = simulated_at, []
                readings.append(_raw_reading(row, self.manifest.dataset_version))
        if readings:
            yield _make_tick(pending_at, readings, expected_at, self.manifest)

    def window_batch(self, window_end: datetime) -> WindowBatch:
        rows: list[dict[str, Any]] = []
        for shard in self.manifest.window_shards:
            if not _parse_time(shard["start"]) <= window_end <= _parse_time(shard["end"]):
                continue
            for row in _csv_rows(self.root / shard["path"]):
                if _parse_time(row["window_end"]) == window_end:
                    rows.append(_window_record(row))
        if len(rows) != self.manifest.expected_substations:
            raise ReplayDatasetError(
                f"window {window_end.isoformat()} has {len(rows)} substations; expected 31"
            )
        start = _parse_time(rows[0]["window_start"])
        return WindowBatch(start, window_end, tuple(rows))


def _verify_manifest_files(root: Path, manifest: ReplayManifest) -> list[dict[str, Any]]:
    payload = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    for kind, shards in (("raw_shard", manifest.raw_shards), ("window_shard", manifest.window_shards)):
        for shard in shards:
            path = root / shard["path"]
            if not path.is_file() or _sha256_file(path) != shard.get("sha256"):
                raise ReplayDatasetError(f"replay shard checksum mismatch: {shard['path']}")
            entries.append({"relative_path": shard["path"], "file_kind": kind, **shard})
    for key, kind in (("sensor_manifest", "sensor_manifest"), ("scenario_manifest", "scenario_manifest"), ("seek_points", "seek_points")):
        relative_path = payload.get(key)
        if not relative_path:
            continue
        path = root / str(relative_path)
        expected_hash = payload.get(f"{key}_sha256")
        if not path.is_file() or (expected_hash and _sha256_file(path) != expected_hash):
            raise ReplayDatasetError(f"replay manifest checksum mismatch: {relative_path}")
        entries.append({"relative_path": str(relative_path), "file_kind": kind, "sha256": _sha256_file(path), "byte_size": path.stat().st_size})
    return entries


def _make_tick(
    simulated_at: datetime | None,
    readings: list[dict[str, Any]],
    expected_at: datetime | None,
    manifest: ReplayManifest,
) -> SensorTick:
    if simulated_at is None or len(readings) != manifest.expected_substations:
        raise ReplayDatasetError("each replay tick must contain 31 substations")
    if expected_at is not None and simulated_at != expected_at:
        raise ReplayDatasetError("replay ticks must be contiguous at 10-minute intervals")
    ids = {int(reading["substation_id"]) for reading in readings}
    if len(ids) != manifest.expected_substations:
        raise ReplayDatasetError("replay tick has duplicate substations")
    return SensorTick(int(readings[0]["sequence"]), str(readings[0]["phase"]), simulated_at, tuple(readings))


def _raw_reading(row: dict[str, str], dataset_version: str) -> dict[str, Any]:
    values = {
        key: None if row.get(key) in {None, ""} else float(row[key])
        for key in (
            "outdoor_temperature",
            "p_net_supply_temperature",
            "p_net_return_temperature",
            "p_net_meter_flow",
        )
    }
    return {
        "dataset_version": dataset_version,
        "sequence": int(row["sequence"]),
        "phase": row["phase"],
        "manufacturer_id": row["manufacturer_id"],
        "substation_id": int(row["substation_id"]),
        "values": values,
        "quality": {key: row.get("quality_flag") or "synthetic" for key in values},
        "scenario_id": row.get("scenario_id") or None,
    }


def _window_record(row: dict[str, str]) -> dict[str, Any]:
    metadata = {
        "dataset_version", "sequence_end", "phase", "manufacturer_id", "manufacturer",
        "substation_id", "window_start", "window_end", "expected_count", "observed_count",
        "feature_set_version", "feature_hash", "configuration_type", "source_file",
        "season_bucket", "label", "fault_event_id", "scenario_id",
    }
    return {
        **{key: row[key] for key in metadata if key in row},
        "feature_values": {key: float(value) for key, value in row.items() if key not in metadata and value not in {"", None}},
    }


def _load_sensors(path: Path) -> tuple[dict[str, Any], ...]:
    rows = tuple(_csv_rows(path))
    enabled = tuple(row for row in rows if row.get("enabled", "True").lower() == "true")
    if len(enabled) != 4:
        raise ReplayDatasetError("replay sensor contract must have exactly four enabled sensors")
    return enabled


def _csv_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _shards(value: object) -> Iterator[dict[str, Any]]:
    if not isinstance(value, list):
        raise ReplayDatasetError("manifest shards must be a list")
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ReplayDatasetError("manifest contains an invalid shard")
        if Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
            raise ReplayDatasetError("manifest contains an unsafe shard path")
        yield item


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ReplayDatasetError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ReplayDatasetError("timestamp must include a timezone")
    return parsed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unsafe_member(member: zipfile.ZipInfo) -> bool:
    path = Path(member.filename)
    mode = member.external_attr >> 16
    return path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode)
