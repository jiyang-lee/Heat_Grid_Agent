"""Build full supervised PreDist preprocessing output for priority training.

This uses all audited supervised candidate windows rather than the small
300-row fixture. Raw rows are read from the ZIP and converted in memory; the
committed artifact is the supervised labels, preprocessed windows, and manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.io import paths
from agent.preprocessing import build_preprocessed_windows
from agent.preprocessing.audit_predist_labels import audit_predist_label_distribution
from agent.preprocessing.sample_predist_zip import build_ratio_matched_predist_sample


DEFAULT_ZIP_PATH = Path("C:/Users/Admin/Downloads/predist_dataset.zip")


def run(
    zip_path: str | Path = DEFAULT_ZIP_PATH,
    *,
    output_dir: str | Path = paths.PREDIST_FULL_SUPERVISED_DIR,
) -> dict[str, object]:
    """Write full supervised labels, preprocessed windows, and a manifest."""

    zip_path = Path(zip_path)
    out_dir = paths.ensure_dir(Path(output_dir))
    labels_path = out_dir / "supervised_window_labels.csv"
    preprocessed_path = out_dir / "preprocessed_windows.csv"
    manifest_path = out_dir / "manifest.json"
    audit = audit_predist_label_distribution(zip_path)
    raw = build_ratio_matched_predist_sample(
        zip_path,
        target_windows=audit.supervised_windows,
    )
    result = build_preprocessed_windows(
        raw["substations"],
        raw["sensor_readings"],
        raw["fault_events"],
        raw["maintenance_events"],
    )

    labels = raw["supervised_window_labels"]
    labels.to_csv(labels_path, index=False, encoding="utf-8")
    result.to_csv(preprocessed_path, index=False, encoding="utf-8")

    label_counts = labels["label"].value_counts().to_dict()
    bucket_counts = labels[labels["label"].eq("pre_fault")]["lead_time_bucket"].value_counts().to_dict()
    manifest = {
        "source_zip": str(zip_path),
        "audit": audit.to_dict(),
        "raw_rows_read": {
            "substations": int(len(raw["substations"])),
            "sensor_readings": int(len(raw["sensor_readings"])),
            "fault_events": int(len(raw["fault_events"])),
            "maintenance_events": int(len(raw["maintenance_events"])),
        },
        "labels": {
            "rows": int(len(labels)),
            "counts": {str(k): int(v) for k, v in label_counts.items()},
            "lead_bucket_counts": {str(k): int(v) for k, v in bucket_counts.items()},
        },
        "preprocessed": {
            "rows": int(len(result)),
            "columns": int(len(result.columns)),
            "path": str(preprocessed_path.relative_to(paths.REPO_ROOT)).replace("\\", "/"),
        },
        "labels_path": str(labels_path.relative_to(paths.REPO_ROOT)).replace("\\", "/"),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "[build_full_predist_supervised] wrote "
        f"labels={len(labels)} preprocessed={result.shape} raw_rows={manifest['raw_rows_read']}"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build full supervised PreDist preprocessing artifacts.")
    parser.add_argument("zip_path", nargs="?", type=Path, default=DEFAULT_ZIP_PATH)
    parser.add_argument("--output-dir", type=Path, default=paths.PREDIST_FULL_SUPERVISED_DIR)
    args = parser.parse_args()
    run(args.zip_path, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
