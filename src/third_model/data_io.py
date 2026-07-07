from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import config
from .common import write_json


def _parse_substation_id(path: Path) -> int | None:
    match = re.search(r"substation_(\d+)\.csv$", path.name)
    if not match:
        return None
    return int(match.group(1))


def _read_raw_sample(path: Path, rows: int = 200) -> pd.DataFrame:
    return pd.read_csv(path, sep=";", nrows=rows, low_memory=False)


def build_raw_inventory() -> pd.DataFrame:
    """Inspect raw PreDist files without modifying source data."""
    config.ensure_dirs()
    rows: list[dict[str, object]] = []
    schema_rows: list[dict[str, object]] = []
    if not config.SOURCE_RAW_ROOT.exists():
        if config.RAW_INVENTORY_PATH.exists() and config.RAW_SCHEMA_PATH.exists():
            inventory = pd.read_csv(config.RAW_INVENTORY_PATH)
            if "path" in inventory.columns:
                inventory["path"] = inventory["path"].fillna("").map(
                    lambda value: config.path_label(Path(str(value))) if str(value) else ""
                )
                inventory.to_csv(config.RAW_INVENTORY_PATH, index=False, encoding="utf-8-sig")
            write_json(
                config.INTERIM_DIR / "raw_inventory_metadata.json",
                {
                    "source": config.path_label(config.SOURCE_RAW_ROOT, "THIRD_MODEL_SOURCE_BEST_ROOT"),
                    "source_available": False,
                    "inventory_path": config.path_label(config.RAW_INVENTORY_PATH),
                    "schema_path": config.path_label(config.RAW_SCHEMA_PATH),
                    "note": "External raw source is unavailable. Packaged inventory files are reused for reproducible handoff execution.",
                },
            )
            return inventory
        raise FileNotFoundError(
            f"Raw source folder not found and packaged inventory is missing: {config.path_label(config.SOURCE_RAW_ROOT)}"
        )

    for manufacturer_dir in sorted(config.SOURCE_RAW_ROOT.glob("manufacturer *")):
        if not manufacturer_dir.is_dir():
            continue
        manufacturer = manufacturer_dir.name
        if manufacturer != config.M1_MANUFACTURER:
            continue
        for metadata_file in ["disturbances.csv", "faults.csv", "normal_events.csv", "configuration_types.csv"]:
            path = manufacturer_dir / metadata_file
            rows.append(
                {
                    "manufacturer": manufacturer,
                    "file_type": metadata_file,
                    "path": config.path_label(path),
                    "exists": path.exists(),
                    "substation_id": None,
                    "row_count_sampled": None,
                    "column_count_sampled": None,
                }
            )
        operational_dir = manufacturer_dir / "operational_data"
        for path in sorted(operational_dir.glob("substation_*.csv")):
            sample = _read_raw_sample(path)
            rows.append(
                {
                    "manufacturer": manufacturer,
                    "file_type": "operational_data",
                    "path": config.path_label(path),
                    "exists": True,
                    "substation_id": _parse_substation_id(path),
                    "row_count_sampled": int(len(sample)),
                    "column_count_sampled": int(len(sample.columns)),
                }
            )
            for column in sample.columns:
                schema_rows.append(
                    {
                        "manufacturer": manufacturer,
                        "substation_id": _parse_substation_id(path),
                        "column_name": column,
                        "sample_non_null_count": int(sample[column].notna().sum()),
                    }
                )

    inventory = pd.DataFrame(rows)
    schema = pd.DataFrame(schema_rows)
    inventory.to_csv(config.RAW_INVENTORY_PATH, index=False, encoding="utf-8-sig")
    schema.to_csv(config.RAW_SCHEMA_PATH, index=False, encoding="utf-8-sig")
    write_json(
        config.INTERIM_DIR / "raw_inventory_metadata.json",
        {
            "source": config.path_label(config.SOURCE_RAW_ROOT, "THIRD_MODEL_SOURCE_BEST_ROOT"),
            "inventory_path": config.path_label(config.RAW_INVENTORY_PATH),
            "schema_path": config.path_label(config.RAW_SCHEMA_PATH),
            "operational_file_count": int((inventory["file_type"] == "operational_data").sum()),
        },
    )
    return inventory


def import_canonical_windows() -> pd.DataFrame:
    """Bring the current best raw-derived window table into this project as M1-only.

    The M1 filter is intentionally applied before feature selection and
    imputation so every downstream model learns the manufacturer-1 distribution
    rather than a mixed M1/M2 distribution.
    """
    config.ensure_dirs()
    if not config.SOURCE_TRAINABLE_WINDOWS_PATH.exists():
        packaged_ready = (
            config.TRAINABLE_WINDOWS_PATH.exists()
            and config.FEATURE_COLUMNS_PATH.exists()
            and config.IMPUTATION_VALUES_PATH.exists()
        )
        if packaged_ready:
            windows = pd.read_csv(config.TRAINABLE_WINDOWS_PATH)
            write_json(
                config.PROCESSED_DIR / "window_import_metadata.json",
                {
                    "source": config.path_label(config.SOURCE_TRAINABLE_WINDOWS_PATH, "THIRD_MODEL_SOURCE_BEST_ROOT"),
                    "source_available": False,
                    "scope": config.PROJECT_SCOPE,
                    "manufacturer_filter": config.M1_MANUFACTURER,
                    "row_count": int(len(windows)),
                    "column_count": int(len(windows.columns)),
                    "note": "External canonical windows are unavailable. Packaged M1 canonical windows, feature columns, and imputation values are reused.",
                },
            )
            return windows
        raise FileNotFoundError(
            "Missing canonical windows and packaged processed files are incomplete: "
            + config.path_label(config.SOURCE_TRAINABLE_WINDOWS_PATH)
        )
    source_windows = pd.read_csv(config.SOURCE_TRAINABLE_WINDOWS_PATH)
    windows = source_windows.loc[source_windows["manufacturer"].astype(str).eq(config.M1_MANUFACTURER)].copy()
    if windows.empty:
        raise ValueError(f"No rows found for {config.M1_MANUFACTURER} in {config.SOURCE_TRAINABLE_WINDOWS_PATH}")

    source_features = pd.read_csv(config.SOURCE_FEATURE_COLUMNS_PATH)
    source_imputation = pd.read_csv(config.SOURCE_IMPUTATION_VALUES_PATH)
    feature_column = "column_name" if "column_name" in source_features.columns else source_features.columns[0]
    if "selected_for_baseline" in source_features.columns:
        selected_mask = source_features["selected_for_baseline"].fillna(False).astype(bool)
        candidates = source_features.loc[selected_mask, feature_column].astype(str).tolist()
    else:
        candidates = source_imputation["column_name"].astype(str).tolist()
    candidates = [column for column in candidates if column in windows.columns]

    split_column = "split_regime_based" if "split_regime_based" in windows.columns else config.ANOMALY_SPLIT_COLUMN
    train_mask = windows[split_column].eq("train") if split_column in windows.columns else pd.Series(True, index=windows.index)
    numeric = windows[candidates].apply(pd.to_numeric, errors="coerce")
    missing = numeric.loc[train_mask].isna().mean()
    nunique = numeric.loc[train_mask].nunique(dropna=True)
    kept = [
        column
        for column in candidates
        if missing.get(column, 1.0) < 0.85 and nunique.get(column, 0) > 1
    ]
    feature_table = source_features.loc[source_features[feature_column].astype(str).isin(kept)].copy()
    if feature_table.empty:
        feature_table = pd.DataFrame({"column_name": kept})
    feature_table["m1_missing_rate_train"] = [float(missing.get(column, 0.0)) for column in feature_table[feature_column].astype(str)]
    feature_table["m1_unique_count_train"] = [int(nunique.get(column, 0)) for column in feature_table[feature_column].astype(str)]
    feature_table["m1_selected_for_baseline"] = True

    imputation_values = numeric.loc[train_mask, kept].median(numeric_only=True).fillna(0.0)
    imputation = pd.DataFrame(
        {
            "column_name": kept,
            "imputation_strategy": "m1_train_median",
            "imputation_value": [float(imputation_values.get(column, 0.0)) for column in kept],
            "selection_split_column": split_column,
            "selection_split_value": "train",
        }
    )

    windows.to_csv(config.TRAINABLE_WINDOWS_PATH, index=False, encoding="utf-8-sig")
    feature_table.to_csv(config.FEATURE_COLUMNS_PATH, index=False, encoding="utf-8-sig")
    imputation.to_csv(config.IMPUTATION_VALUES_PATH, index=False, encoding="utf-8-sig")
    write_json(
        config.PROCESSED_DIR / "window_import_metadata.json",
        {
            "source": config.path_label(config.SOURCE_TRAINABLE_WINDOWS_PATH, "THIRD_MODEL_SOURCE_BEST_ROOT"),
            "scope": config.PROJECT_SCOPE,
            "manufacturer_filter": config.M1_MANUFACTURER,
            "source_row_count": int(len(source_windows)),
            "row_count": int(len(windows)),
            "column_count": int(len(windows.columns)),
            "feature_count": int(len(kept)),
            "label_counts": windows["label"].value_counts(dropna=False).to_dict() if "label" in windows.columns else {},
            "split_counts": windows[config.ANOMALY_SPLIT_COLUMN].value_counts(dropna=False).to_dict()
            if config.ANOMALY_SPLIT_COLUMN in windows.columns
            else {},
            "fault_event_count": int(windows.loc[windows["label"].eq("pre_fault"), "fault_event_id"].nunique())
            if "fault_event_id" in windows.columns and "label" in windows.columns
            else 0,
            "note": "M1-only canonical windows. Feature columns and imputation values are recomputed from M1 train rows.",
        },
    )
    return windows
