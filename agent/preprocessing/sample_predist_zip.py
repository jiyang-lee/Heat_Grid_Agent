"""Build a small PreDist ZIP sample for preprocessing contract verification."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from agent.preprocessing import build_preprocessed_windows
from agent.preprocessing.contracts import PREPROCESSING_VERSION

TARGET_SUBSTATIONS = [
    {"manufacturer": "manufacturer 1", "substation_id": 10},
    {"manufacturer": "manufacturer 2", "substation_id": 24},
]


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
    return "\n".join(
        [
            "# PreDist 전처리 샘플 fixture",
            "",
            f"- 원본 ZIP: `{Path(zip_path)}`",
            f"- 샘플 대상: {targets}",
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
    args = parser.parse_args()

    result = run_predist_sample(args.zip_path, args.output_dir)
    print(
        "generated preprocessed_windows sample: "
        f"rows={len(result)}, columns={len(result.columns)}"
    )


if __name__ == "__main__":
    main()
