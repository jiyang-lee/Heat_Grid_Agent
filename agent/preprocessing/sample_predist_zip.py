"""Build a small PreDist ZIP sample for preprocessing contract verification."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from agent.preprocessing import build_preprocessed_windows
from agent.preprocessing.audit_predist_labels import audit_predist_label_distribution
from agent.preprocessing.contracts import PREPROCESSING_VERSION

TARGET_SUBSTATIONS = [
    {"manufacturer": "manufacturer 1", "substation_id": 10},
    {"manufacturer": "manufacturer 2", "substation_id": 24},
]

RATIO_FIXTURE_SEED = 42
DEFAULT_RATIO_TARGET_WINDOWS = 300
LEAD_BUCKETS = ["0-24h", "1-3d", "3-7d"]


def build_predist_sample(
    zip_path: str | Path,
    rows_per_substation: int = 150,
) -> dict[str, pd.DataFrame]:
    """Return raw 4-table dataframes sampled from the PreDist ZIP."""

    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        sensor_frames = []
        fault_frames = []
        task_frames = []
        substation_rows = []

        for target in TARGET_SUBSTATIONS:
            manufacturer = str(target["manufacturer"])
            substation_id = int(target["substation_id"])
            source_file = f"{manufacturer}/operational_data/substation_{substation_id}.csv"

            faults = _read_fault_events(archive, manufacturer)
            matching_faults = _filter_substation(faults, substation_id)
            target_ts = _first_report_date(matching_faults)

            sensors = _read_operational_rows(archive, source_file, manufacturer, substation_id)
            sample = _sample_near_timestamp(sensors, target_ts, rows_per_substation)
            sensor_frames.append(sample)
            fault_frames.append(matching_faults)

            tasks = _read_task_events(archive, manufacturer)
            task_frames.append(_filter_substation(tasks, substation_id))

            substation_rows.append(
                {
                    "substation_id": substation_id,
                    "manufacturer": manufacturer,
                    "source_file": source_file,
                    "configuration_type": "missing",
                    "has_dhw": pd.NA,
                    "has_buffer_tank": pd.NA,
                }
            )

        return {
            "substations": pd.DataFrame(substation_rows),
            "sensor_readings": _concat(sensor_frames),
            "fault_events": _concat(fault_frames),
            "maintenance_events": _concat(task_frames),
        }


def run_predist_sample(
    zip_path: str | Path,
    output_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Run PreDist ZIP sample through the preprocessing pipeline."""

    raw = build_predist_sample(zip_path)
    result = build_preprocessed_windows(
        raw["substations"],
        raw["sensor_readings"],
        raw["fault_events"],
        raw["maintenance_events"],
    )

    if output_dir is not None:
        _write_fixture(Path(output_dir), zip_path, raw, result)

    return result


def build_ratio_matched_predist_sample(
    zip_path: str | Path,
    *,
    target_windows: int = DEFAULT_RATIO_TARGET_WINDOWS,
    random_state: int = RATIO_FIXTURE_SEED,
) -> dict[str, pd.DataFrame]:
    """Return raw dataframes and labels sampled at the full PreDist supervised ratio."""

    candidates = build_supervised_window_candidates(zip_path)
    audit = audit_predist_label_distribution(zip_path)
    selected = _sample_candidates_by_audit_ratio(candidates, audit.to_dict(), target_windows, random_state)

    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        sensor_frames = []
        fault_frames = []
        task_frames = []
        substation_rows = []

        target_keys = selected[["manufacturer", "substation_id"]].drop_duplicates()
        for target in target_keys.itertuples(index=False):
            manufacturer = str(target.manufacturer)
            substation_id = int(target.substation_id)
            source_file = f"{manufacturer}/operational_data/substation_{substation_id}.csv"
            windows = selected[
                selected["manufacturer"].eq(manufacturer)
                & selected["substation_id"].eq(substation_id)
            ]

            sensors = _read_operational_rows(archive, source_file, manufacturer, substation_id)
            sensor_frames.append(_filter_selected_windows(sensors, windows))

            faults = _read_fault_events(archive, manufacturer)
            fault_frames.append(_filter_substation(faults, substation_id))

            tasks = _read_task_events(archive, manufacturer)
            task_frames.append(_filter_substation(tasks, substation_id))

            substation_rows.append(
                {
                    "substation_id": substation_id,
                    "manufacturer": manufacturer,
                    "source_file": source_file,
                    "configuration_type": "missing",
                    "has_dhw": pd.NA,
                    "has_buffer_tank": pd.NA,
                }
            )

        raw = {
            "substations": pd.DataFrame(substation_rows),
            "sensor_readings": _concat(sensor_frames),
            "fault_events": _concat(fault_frames),
            "maintenance_events": _concat(task_frames),
        }
        labels = selected.sort_values(["manufacturer", "substation_id", "window_start"]).reset_index(drop=True)
        return {**raw, "supervised_window_labels": labels}


def run_ratio_matched_predist_sample(
    zip_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    target_windows: int = DEFAULT_RATIO_TARGET_WINDOWS,
) -> pd.DataFrame:
    """Run the ratio-matched PreDist fixture through the preprocessing pipeline."""

    raw = build_ratio_matched_predist_sample(zip_path, target_windows=target_windows)
    result = build_preprocessed_windows(
        raw["substations"],
        raw["sensor_readings"],
        raw["fault_events"],
        raw["maintenance_events"],
    )

    if output_dir is not None:
        _write_fixture(Path(output_dir), zip_path, raw, result)

    return result


def build_supervised_window_candidates(zip_path: str | Path) -> pd.DataFrame:
    """Build all supervised normal/pre_fault candidate windows used by the fixture sampler."""

    rows: dict[tuple[str, int, int], dict[str, object]] = {}
    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        for manufacturer in ["manufacturer 1", "manufacturer 2"]:
            normal_events = _read_normal_events(archive, manufacturer)
            faults = _read_fault_events(archive, manufacturer)
            efd_faults = faults[faults["efd_possible"].astype(str).str.lower().eq("true")].copy()
            substations = pd.concat(
                [
                    normal_events[["substation_id"]],
                    efd_faults[["substation_id"]],
                ],
                ignore_index=True,
            )["substation_id"].dropna().astype(int).drop_duplicates()

            for substation_id in substations:
                source_file = f"{manufacturer}/operational_data/substation_{substation_id}.csv"
                if source_file not in archive.namelist():
                    continue
                windows = _read_operational_window_starts(archive, source_file)
                if windows.empty:
                    continue
                _add_normal_candidates(rows, windows, normal_events, manufacturer, int(substation_id), source_file)
                _add_fault_candidates(rows, windows, efd_faults, manufacturer, int(substation_id), source_file)

    frame = pd.DataFrame(rows.values())
    if frame.empty:
        return frame
    return frame.sort_values(["label", "lead_time_bucket", "manufacturer", "substation_id", "window_start"]).reset_index(drop=True)


def _read_csv(archive: zipfile.ZipFile, member: str, **kwargs: Any) -> pd.DataFrame:
    with archive.open(member) as handle:
        return pd.read_csv(handle, sep=";", encoding="utf-8-sig", low_memory=False, **kwargs)


def _read_operational_rows(
    archive: zipfile.ZipFile,
    source_file: str,
    manufacturer: str,
    substation_id: int,
) -> pd.DataFrame:
    frame = _read_csv(archive, source_file)
    frame = frame.rename(columns={column: _normalize_column_name(column) for column in frame.columns})
    frame["manufacturer"] = manufacturer
    frame["substation_id"] = substation_id
    frame["source_file"] = source_file
    return frame


def _read_fault_events(archive: zipfile.ZipFile, manufacturer: str) -> pd.DataFrame:
    member = f"{manufacturer}/faults.csv"
    frame = _read_csv(archive, member)
    frame = frame.rename(
        columns={
            "Event ID": "event_id",
            "substation ID": "substation_id",
            "Report date": "report_date",
            "Problem EN": "problem_en",
            "Event description EN": "event_description_en",
            "Possible anomaly start": "possible_anomaly_start",
            "Possible anomaly end": "possible_anomaly_end",
            "Training start": "training_start",
            "Training end": "training_end",
            "Fault label": "fault_label",
            "Monitoring potential": "monitoring_potential",
        }
    )
    frame["manufacturer"] = manufacturer
    frame["substation_id"] = pd.to_numeric(frame["substation_id"], errors="coerce").astype("Int64")
    if "efd_possible" in frame.columns:
        frame["efd_possible"] = _coerce_bool_like(frame["efd_possible"])
    else:
        frame["efd_possible"] = False
    return frame


def _coerce_bool_like(values: pd.Series | None) -> pd.Series:
    if values is None or len(values) == 0:
        return pd.Series([], dtype="boolean")
    numeric = pd.to_numeric(values, errors="coerce")
    numeric_true = numeric.eq(1) | numeric.eq(1.0)
    text = values.astype("string").str.strip().str.lower().fillna("")
    text_true = text.isin({"true", "t", "yes", "y", "on", "1"})
    return (numeric_true | text_true).astype("boolean")


def _read_normal_events(archive: zipfile.ZipFile, manufacturer: str) -> pd.DataFrame:
    member = f"{manufacturer}/normal_events.csv"
    frame = _read_csv(archive, member)
    frame = frame.rename(
        columns={
            "Event ID": "event_id",
            "substation ID": "substation_id",
            "Event start": "event_start",
            "Event end": "event_end",
            "Training start": "training_start",
            "Training end": "training_end",
        }
    )
    frame["manufacturer"] = manufacturer
    frame["substation_id"] = pd.to_numeric(frame["substation_id"], errors="coerce").astype("Int64")
    frame["event_start"] = pd.to_datetime(frame["event_start"], errors="coerce", utc=True)
    frame["event_end"] = pd.to_datetime(frame["event_end"], errors="coerce", utc=True)
    return frame


def _read_task_events(archive: zipfile.ZipFile, manufacturer: str) -> pd.DataFrame:
    member = f"{manufacturer}/disturbances.csv"
    frame = _read_csv(archive, member)
    frame = frame.rename(columns={"substation ID": "substation_id", "Event start": "event_start"})
    frame["manufacturer"] = manufacturer
    frame["substation_id"] = pd.to_numeric(frame["substation_id"], errors="coerce").astype("Int64")
    return frame


def _filter_substation(frame: pd.DataFrame, substation_id: int) -> pd.DataFrame:
    if frame.empty or "substation_id" not in frame.columns:
        return frame.copy()
    return frame[frame["substation_id"] == substation_id].copy().reset_index(drop=True)


def _first_report_date(faults: pd.DataFrame) -> pd.Timestamp | None:
    if faults.empty or "report_date" not in faults.columns:
        return None
    dates = pd.to_datetime(faults["report_date"], errors="coerce", utc=True).dropna()
    if dates.empty:
        return None
    return dates.sort_values().iloc[0]


def _sample_near_timestamp(
    sensors: pd.DataFrame,
    target_ts: pd.Timestamp | None,
    rows_per_substation: int,
) -> pd.DataFrame:
    frame = sensors.copy()
    parsed_ts = pd.to_datetime(frame["ts"], errors="coerce", utc=True)
    if target_ts is None or parsed_ts.dropna().empty:
        return frame.head(rows_per_substation).reset_index(drop=True)

    valid_ts = parsed_ts.dropna()
    if target_ts < valid_ts.min() or target_ts > valid_ts.max():
        return frame.head(rows_per_substation).reset_index(drop=True)

    nearest_index = (parsed_ts - target_ts).abs().idxmin()
    nearest_position = frame.index.get_loc(nearest_index)
    start = max(0, nearest_position - rows_per_substation // 2)
    end = start + rows_per_substation
    if end > len(frame):
        end = len(frame)
        start = max(0, end - rows_per_substation)
    return frame.iloc[start:end].reset_index(drop=True)


def _read_operational_window_starts(archive: zipfile.ZipFile, source_file: str) -> pd.Series:
    frame = _read_csv(archive, source_file, usecols=["timestamp"])
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True).dropna()
    if timestamps.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")
    return timestamps.dt.floor("6h").drop_duplicates().sort_values().reset_index(drop=True)


def _add_normal_candidates(
    rows: dict[tuple[str, int, int], dict[str, object]],
    windows: pd.Series,
    normal_events: pd.DataFrame,
    manufacturer: str,
    substation_id: int,
    source_file: str,
) -> None:
    subset = normal_events[normal_events["substation_id"].eq(substation_id)]
    for event in subset.itertuples(index=False):
        if pd.isna(event.event_start) or pd.isna(event.event_end):
            continue
        candidates = windows[
            (windows >= event.event_start.floor("6h"))
            & (windows < event.event_end.ceil("6h"))
        ]
        for window_start in candidates:
            key = (manufacturer, substation_id, int(window_start.value))
            rows.setdefault(
                key,
                _label_row(
                    manufacturer,
                    substation_id,
                    source_file,
                    window_start,
                    "normal",
                    "",
                    pd.NA,
                    pd.NA,
                ),
            )


def _add_fault_candidates(
    rows: dict[tuple[str, int, int], dict[str, object]],
    windows: pd.Series,
    faults: pd.DataFrame,
    manufacturer: str,
    substation_id: int,
    source_file: str,
) -> None:
    subset = faults[faults["substation_id"].eq(substation_id)].copy()
    subset["report_date"] = pd.to_datetime(subset["report_date"], errors="coerce", utc=True)
    subset = subset.dropna(subset=["report_date"])
    for event in subset.itertuples(index=False):
        start = event.report_date - pd.Timedelta(hours=168)
        candidates = windows[
            (windows >= start.floor("6h"))
            & (windows < event.report_date)
        ]
        for window_start in candidates:
            lead_hours = (event.report_date - window_start).total_seconds() / 3600.0
            bucket = _lead_bucket(lead_hours)
            if bucket is None:
                continue
            key = (manufacturer, substation_id, int(window_start.value))
            current = rows.get(key)
            if current is not None and current["label"] == "pre_fault" and lead_hours >= float(current["estimated_lead_time_hours"]):
                continue
            rows[key] = _label_row(
                manufacturer,
                substation_id,
                source_file,
                window_start,
                "pre_fault",
                bucket,
                lead_hours,
                getattr(event, "event_id", pd.NA),
            )


def _label_row(
    manufacturer: str,
    substation_id: int,
    source_file: str,
    window_start: pd.Timestamp,
    label: str,
    lead_time_bucket: str,
    estimated_lead_time_hours: float | object,
    fault_event_id: object,
) -> dict[str, object]:
    return {
        "manufacturer": manufacturer,
        "substation_id": substation_id,
        "source_file": source_file,
        "window_start": window_start.isoformat(),
        "window_end": (window_start + pd.Timedelta(hours=6)).isoformat(),
        "label": label,
        "lead_time_bucket": lead_time_bucket,
        "estimated_lead_time_hours": estimated_lead_time_hours,
        "fault_event_id": fault_event_id,
    }


def _lead_bucket(lead_hours: float) -> str | None:
    if 0 < lead_hours <= 24:
        return "0-24h"
    if 24 < lead_hours <= 72:
        return "1-3d"
    if 72 < lead_hours <= 168:
        return "3-7d"
    return None


def _sample_candidates_by_audit_ratio(
    candidates: pd.DataFrame,
    audit: dict[str, object],
    target_windows: int,
    random_state: int,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    candidates = candidates.drop_duplicates(
        subset=["manufacturer", "substation_id", "window_start"],
        keep="first",
    ).reset_index(drop=True)

    normal_total = int(audit["window_counts"]["normal"])
    pre_fault_total = int(audit["window_counts"]["pre_fault"])
    supervised_total = normal_total + pre_fault_total
    normal_target = round(target_windows * normal_total / supervised_total)
    pre_fault_target = target_windows - normal_target

    parts = [
        _sample_group(
            candidates[candidates["label"].eq("normal")],
            normal_target,
            random_state,
        )
    ]

    bucket_counts = audit["lead_bucket_counts"]
    remaining = pre_fault_target
    for index, bucket in enumerate(LEAD_BUCKETS):
        if index == len(LEAD_BUCKETS) - 1:
            bucket_target = remaining
        else:
            bucket_target = round(pre_fault_target * int(bucket_counts[bucket]) / pre_fault_total)
            remaining -= bucket_target
        parts.append(
            _sample_group(
                candidates[
                    candidates["label"].eq("pre_fault")
                    & candidates["lead_time_bucket"].eq(bucket)
                ],
                bucket_target,
                random_state + index + 1,
            )
        )

    return pd.concat(parts, ignore_index=True).sort_values(
        ["manufacturer", "substation_id", "window_start"]
    ).reset_index(drop=True)


def _sample_group(frame: pd.DataFrame, target: int, random_state: int) -> pd.DataFrame:
    if target <= 0:
        return frame.head(0).copy()
    replace = len(frame) < target
    return frame.sample(n=target, replace=replace, random_state=random_state).copy()


def _filter_selected_windows(sensors: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    frame = sensors.copy()
    frame["_ts"] = pd.to_datetime(frame["ts"], errors="coerce", utc=True)
    selected = []
    for window in windows.itertuples(index=False):
        start = pd.Timestamp(window.window_start)
        end = pd.Timestamp(window.window_end)
        selected.append(frame[(frame["_ts"] >= start) & (frame["_ts"] < end)])
    if not selected:
        return frame.head(0).drop(columns=["_ts"])
    result = pd.concat(selected, ignore_index=True)
    return result.drop(columns=["_ts"])


def _normalize_column_name(column: str) -> str:
    if column == "timestamp":
        return "ts"
    name = column.strip().lower().replace(".", "_").replace("-", "")
    return re.sub(r"_+", "_", re.sub(r"\s+", "_", name)).strip("_")


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def _write_fixture(
    output_path: Path,
    zip_path: str | Path,
    raw: dict[str, pd.DataFrame],
    result: pd.DataFrame,
) -> None:
    raw_path = output_path / "raw"
    result_path = output_path / "output"
    raw_path.mkdir(parents=True, exist_ok=True)
    result_path.mkdir(parents=True, exist_ok=True)

    raw["substations"].to_csv(raw_path / "substations.csv", index=False)
    raw["sensor_readings"].to_csv(raw_path / "sensor_readings.csv", index=False)
    raw["fault_events"].to_csv(raw_path / "fault_events.csv", index=False)
    raw["maintenance_events"].to_csv(raw_path / "maintenance_events.csv", index=False)
    result.to_csv(result_path / "preprocessed_windows_sample.csv", index=False)
    if "supervised_window_labels" in raw:
        raw["supervised_window_labels"].to_csv(result_path / "supervised_window_labels.csv", index=False)
    (output_path / "README.md").write_text(
        _fixture_readme(zip_path, raw, result),
        encoding="utf-8",
    )


def _fixture_readme(
    zip_path: str | Path,
    raw: dict[str, pd.DataFrame],
    result: pd.DataFrame,
) -> str:
    targets = ", ".join(
        f"{target['manufacturer']} substation_{target['substation_id']}"
        for target in TARGET_SUBSTATIONS
    )
    label_lines = []
    if "supervised_window_labels" in raw:
        labels = raw["supervised_window_labels"]
        label_counts = labels["label"].value_counts().to_dict()
        bucket_counts = labels[labels["label"].eq("pre_fault")]["lead_time_bucket"].value_counts().to_dict()
        label_lines = [
            "- 샘플링 기준: full PreDist supervised 후보 비율 감사값",
            f"- supervised_window_labels 행 수: {len(labels)}",
            f"- label 분포: normal={label_counts.get('normal', 0)}, pre_fault={label_counts.get('pre_fault', 0)}",
            (
                "- pre_fault bucket 분포: "
                f"0-24h={bucket_counts.get('0-24h', 0)}, "
                f"1-3d={bucket_counts.get('1-3d', 0)}, "
                f"3-7d={bucket_counts.get('3-7d', 0)}"
            ),
            "- 라벨 파일은 `output/supervised_window_labels.csv`에 별도로 둔다.",
        ]
    else:
        label_lines = [f"- 샘플 대상: {targets}"]
    return "\n".join(
        [
            "# PreDist 전처리 샘플 fixture",
            "",
            f"- 원본 ZIP: `{Path(zip_path)}`",
            *label_lines,
            f"- sensor_readings 행 수: {len(raw['sensor_readings'])}",
            f"- fault_events 행 수: {len(raw['fault_events'])}",
            f"- maintenance_events 행 수: {len(raw['maintenance_events'])}",
            f"- preprocessed_windows 행 수: {len(result)}",
            f"- preprocessed_windows 컬럼 수: {len(result.columns)}",
            f"- preprocessing_version: `{PREPROCESSING_VERSION}`",
            "- `raw/` 아래 4개 CSV만으로 원본 ZIP 없이 전처리 재현이 가능하다.",
            "- 전처리 결과는 `output/preprocessed_windows_sample.csv`에 저장한다.",
            "- `configuration_types.csv`가 없어 `configuration_type=\"missing\"` fallback을 사용한다.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a small PreDist preprocessing sample.")
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--ratio-matched", action="store_true")
    parser.add_argument("--target-windows", type=int, default=DEFAULT_RATIO_TARGET_WINDOWS)
    args = parser.parse_args()

    if args.ratio_matched:
        result = run_ratio_matched_predist_sample(
            args.zip_path,
            args.output_dir,
            target_windows=args.target_windows,
        )
    else:
        result = run_predist_sample(args.zip_path, args.output_dir)
    print(
        "generated preprocessed_windows sample: "
        f"rows={len(result)}, columns={len(result.columns)}"
    )


if __name__ == "__main__":
    main()
