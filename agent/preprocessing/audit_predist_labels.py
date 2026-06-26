"""Audit supervised label ratios from the full PreDist ZIP without extraction."""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from agent.io import paths
from agent.preprocessing.contracts import WINDOW_SIZE

DEFAULT_HORIZON_HOURS = 168
MANUFACTURERS = ("manufacturer 1", "manufacturer 2")
LEAD_BUCKETS = ("0-24h", "1-3d", "3-7d")


@dataclass(frozen=True)
class PredistLabelAudit:
    """Compact audit result for normal/pre_fault supervised windows."""

    total_fault_events: int
    efd_possible_fault_events: int
    normal_events: int
    operational_files_read: int
    normal_windows: int
    pre_fault_windows: int
    overlap_windows: int
    lead_bucket_counts: dict[str, int]
    horizon_hours: int
    window_size: str

    @property
    def supervised_windows(self) -> int:
        return self.normal_windows + self.pre_fault_windows

    @property
    def normal_ratio(self) -> float:
        return self.normal_windows / self.supervised_windows if self.supervised_windows else 0.0

    @property
    def pre_fault_ratio(self) -> float:
        return self.pre_fault_windows / self.supervised_windows if self.supervised_windows else 0.0

    def to_dict(self) -> dict[str, object]:
        pre_fault = max(1, self.pre_fault_windows)
        return {
            "source": "full_predist_zip",
            "window_size": self.window_size,
            "horizon_hours": self.horizon_hours,
            "event_counts": {
                "fault_events": self.total_fault_events,
                "efd_possible_fault_events": self.efd_possible_fault_events,
                "normal_events": self.normal_events,
            },
            "window_counts": {
                "normal": self.normal_windows,
                "pre_fault": self.pre_fault_windows,
                "normal_pre_fault_total": self.supervised_windows,
                "normal_fault_overlap": self.overlap_windows,
            },
            "ratios": {
                "normal": self.normal_ratio,
                "pre_fault": self.pre_fault_ratio,
            },
            "lead_bucket_counts": self.lead_bucket_counts,
            "lead_bucket_ratios": {
                bucket: self.lead_bucket_counts.get(bucket, 0) / pre_fault
                for bucket in LEAD_BUCKETS
            },
            "operational_files_read": self.operational_files_read,
            "notes": [
                "This audit counts supervised candidate windows, not all raw operational rows.",
                "pre_fault windows use efd_possible=True fault events and a 7 day lookback horizon.",
                "normal windows come from normal_events.csv ranges and exclude no additional unlabeled raw windows.",
            ],
        }


def audit_predist_label_distribution(
    zip_path: str | Path,
    *,
    horizon_hours: int = DEFAULT_HORIZON_HOURS,
    window_size: str = WINDOW_SIZE,
) -> PredistLabelAudit:
    """Return normal/pre_fault and lead bucket counts from a PreDist ZIP."""

    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        normal_events = _read_normal_events(archive)
        fault_events = _read_fault_events(archive)
        efd_fault_events = fault_events[fault_events["efd_possible"]]
        keys = pd.concat(
            [
                normal_events[["manufacturer", "substation_id"]],
                efd_fault_events[["manufacturer", "substation_id"]],
            ],
            ignore_index=True,
        ).drop_duplicates()

        normal_windows: set[tuple[str, int, int]] = set()
        fault_windows: dict[tuple[str, int, int], tuple[float, str]] = {}
        operational_files_read = 0
        for row in keys.itertuples(index=False):
            manufacturer = str(row.manufacturer)
            substation_id = int(row.substation_id)
            member = f"{manufacturer}/operational_data/substation_{substation_id}.csv"
            if member not in archive.namelist():
                continue

            operational_files_read += 1
            windows = _read_operational_windows(archive, member, window_size)
            if windows.empty:
                continue

            _collect_normal_windows(
                normal_windows,
                windows,
                normal_events,
                manufacturer,
                substation_id,
                window_size,
            )
            _collect_fault_windows(
                fault_windows,
                windows,
                efd_fault_events,
                manufacturer,
                substation_id,
                horizon_hours,
                window_size,
            )

        overlap = normal_windows & set(fault_windows)
        exclusive_normal = normal_windows - set(fault_windows)
        lead_counts = {bucket: 0 for bucket in LEAD_BUCKETS}
        for _, bucket in fault_windows.values():
            lead_counts[bucket] += 1

        return PredistLabelAudit(
            total_fault_events=len(fault_events),
            efd_possible_fault_events=len(efd_fault_events),
            normal_events=len(normal_events),
            operational_files_read=operational_files_read,
            normal_windows=len(exclusive_normal),
            pre_fault_windows=len(fault_windows),
            overlap_windows=len(overlap),
            lead_bucket_counts=lead_counts,
            horizon_hours=horizon_hours,
            window_size=window_size,
        )


def write_label_audit_outputs(
    audit: PredistLabelAudit,
    output_dir: str | Path = paths.PREDIST_LABEL_AUDIT_DIR,
) -> dict[str, Path]:
    """Write JSON, CSV, and Markdown audit outputs."""

    out_dir = paths.ensure_dir(Path(output_dir))
    data = audit.to_dict()

    json_path = out_dir / "label_distribution.json"
    csv_path = out_dir / "label_distribution.csv"
    md_path = out_dir / "label_distribution.md"

    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _audit_rows(data).to_csv(csv_path, index=False)
    md_path.write_text(_audit_markdown(data), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "md": md_path}


def _read_csv(archive: zipfile.ZipFile, member: str, **kwargs) -> pd.DataFrame:
    with archive.open(member) as handle:
        return pd.read_csv(handle, sep=";", encoding="utf-8-sig", low_memory=False, **kwargs)


def _read_normal_events(archive: zipfile.ZipFile) -> pd.DataFrame:
    frames = []
    for manufacturer in MANUFACTURERS:
        frame = _read_csv(archive, f"{manufacturer}/normal_events.csv")
        frame = frame.rename(
            columns={
                "substation ID": "substation_id",
                "Event start": "event_start",
                "Event end": "event_end",
            }
        )
        frame["manufacturer"] = manufacturer
        frame["substation_id"] = pd.to_numeric(frame["substation_id"], errors="coerce").astype("Int64")
        frame["event_start"] = pd.to_datetime(frame["event_start"], errors="coerce", utc=True)
        frame["event_end"] = pd.to_datetime(frame["event_end"], errors="coerce", utc=True)
        frames.append(frame[["manufacturer", "substation_id", "event_start", "event_end"]])
    return pd.concat(frames, ignore_index=True).dropna()


def _read_fault_events(archive: zipfile.ZipFile) -> pd.DataFrame:
    frames = []
    for manufacturer in MANUFACTURERS:
        frame = _read_csv(archive, f"{manufacturer}/faults.csv")
        frame = frame.rename(
            columns={
                "substation ID": "substation_id",
                "Report date": "report_date",
                "efd_possible": "efd_possible",
            }
        )
        frame["manufacturer"] = manufacturer
        frame["substation_id"] = pd.to_numeric(frame["substation_id"], errors="coerce").astype("Int64")
        frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce", utc=True)
        frame["efd_possible"] = frame["efd_possible"].astype(str).str.lower().eq("true")
        frames.append(frame[["manufacturer", "substation_id", "report_date", "efd_possible"]])
    return pd.concat(frames, ignore_index=True).dropna(subset=["substation_id", "report_date"])


def _read_operational_windows(
    archive: zipfile.ZipFile,
    member: str,
    window_size: str,
) -> pd.Series:
    frame = _read_csv(archive, member, usecols=["timestamp"])
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True).dropna()
    if timestamps.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")
    return timestamps.dt.floor(window_size).drop_duplicates().sort_values().reset_index(drop=True)


def _collect_normal_windows(
    result: set[tuple[str, int, int]],
    windows: pd.Series,
    events: pd.DataFrame,
    manufacturer: str,
    substation_id: int,
    window_size: str,
) -> None:
    subset = events[
        events["manufacturer"].eq(manufacturer)
        & events["substation_id"].eq(substation_id)
    ]
    for event in subset.itertuples(index=False):
        mask = (
            (windows >= event.event_start.floor(window_size))
            & (windows < event.event_end.ceil(window_size))
        )
        for window_start in windows[mask]:
            result.add((manufacturer, substation_id, int(window_start.value)))


def _collect_fault_windows(
    result: dict[tuple[str, int, int], tuple[float, str]],
    windows: pd.Series,
    events: pd.DataFrame,
    manufacturer: str,
    substation_id: int,
    horizon_hours: int,
    window_size: str,
) -> None:
    subset = events[
        events["manufacturer"].eq(manufacturer)
        & events["substation_id"].eq(substation_id)
    ]
    for event in subset.itertuples(index=False):
        start = event.report_date - pd.Timedelta(hours=horizon_hours)
        candidates = windows[(windows >= start.floor(window_size)) & (windows < event.report_date)]
        for window_start in candidates:
            lead_hours = (event.report_date - window_start).total_seconds() / 3600.0
            bucket = _lead_bucket(lead_hours)
            if bucket is None:
                continue
            key = (manufacturer, substation_id, int(window_start.value))
            previous = result.get(key)
            if previous is None or lead_hours < previous[0]:
                result[key] = (lead_hours, bucket)


def _lead_bucket(lead_hours: float) -> str | None:
    if 0 < lead_hours <= 24:
        return "0-24h"
    if 24 < lead_hours <= 72:
        return "1-3d"
    if 72 < lead_hours <= 168:
        return "3-7d"
    return None


def _audit_rows(data: dict[str, object]) -> pd.DataFrame:
    rows = [
        {"metric": "fault_events", "value": data["event_counts"]["fault_events"]},
        {"metric": "efd_possible_fault_events", "value": data["event_counts"]["efd_possible_fault_events"]},
        {"metric": "normal_events", "value": data["event_counts"]["normal_events"]},
        {"metric": "normal_windows", "value": data["window_counts"]["normal"]},
        {"metric": "pre_fault_windows", "value": data["window_counts"]["pre_fault"]},
        {"metric": "normal_ratio", "value": data["ratios"]["normal"]},
        {"metric": "pre_fault_ratio", "value": data["ratios"]["pre_fault"]},
    ]
    rows.extend(
        {"metric": f"lead_bucket_{bucket}", "value": count}
        for bucket, count in data["lead_bucket_counts"].items()
    )
    return pd.DataFrame(rows)


def _audit_markdown(data: dict[str, object]) -> str:
    normal = data["window_counts"]["normal"]
    pre_fault = data["window_counts"]["pre_fault"]
    total = data["window_counts"]["normal_pre_fault_total"]
    bucket_lines = "\n".join(
        f"| `{bucket}` | {data['lead_bucket_counts'][bucket]} | {data['lead_bucket_ratios'][bucket]:.4f} |"
        for bucket in LEAD_BUCKETS
    )
    return "\n".join(
        [
            "# PreDist supervised label ratio audit",
            "",
            "## 기준",
            "",
            f"- window_size: `{data['window_size']}`",
            f"- horizon_hours: `{data['horizon_hours']}`",
            "- fault: `efd_possible=True` and report date 이전 7일 윈도우",
            "- normal: `normal_events.csv` event range 안의 윈도우",
            "- unlabeled operational row/window는 supervised 비율에서 제외",
            "",
            "## 이벤트 행 수",
            "",
            "| 구분 | 건수 |",
            "|---|---:|",
            f"| fault_events | {data['event_counts']['fault_events']} |",
            f"| efd_possible_fault_events | {data['event_counts']['efd_possible_fault_events']} |",
            f"| normal_events | {data['event_counts']['normal_events']} |",
            "",
            "## 6시간 윈도우 비율",
            "",
            "| label | windows | ratio |",
            "|---|---:|---:|",
            f"| normal | {normal} | {data['ratios']['normal']:.4f} |",
            f"| pre_fault | {pre_fault} | {data['ratios']['pre_fault']:.4f} |",
            f"| total | {total} | 1.0000 |",
            "",
            "## pre_fault lead bucket",
            "",
            "| bucket | windows | ratio_in_pre_fault |",
            "|---|---:|---:|",
            bucket_lines,
            "",
            "## 해석",
            "",
            "- full PreDist supervised 후보 윈도우는 1:1이 아니다.",
            "- fixture는 이 관측 비율을 따라야 하며 임의로 normal/pre_fault를 1:1로 맞추지 않는다.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit PreDist normal/pre_fault supervised label ratios.")
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=paths.PREDIST_LABEL_AUDIT_DIR)
    args = parser.parse_args()

    audit = audit_predist_label_distribution(args.zip_path)
    outputs = write_label_audit_outputs(audit, args.output_dir)
    print(
        "predist label audit: "
        f"normal={audit.normal_windows} pre_fault={audit.pre_fault_windows} "
        f"buckets={audit.lead_bucket_counts} outputs={outputs}"
    )


if __name__ == "__main__":
    main()
