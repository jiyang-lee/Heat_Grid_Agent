from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .common import copy_if_exists, write_json


def _clean_experiment_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    parts = [
        part
        for part in value.split("|")
        if not any(marker in part for marker in config.EXCLUDED_EXPERIMENT_MARKERS)
    ]
    return "|".join(parts)


def _sanitize_score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    blocked = [
        column
        for column in frame.columns
        if column.startswith(config.EXCLUDED_EXPERIMENT_PREFIXES)
        or column == "hybrid_anomaly_confidence"
    ]
    sanitized = frame.drop(columns=blocked, errors="ignore").copy()
    for column in sanitized.select_dtypes(include=["object"]).columns:
        sanitized[column] = sanitized[column].map(_clean_experiment_text)
    return sanitized


def _copy_m1_score(source: object, target: object) -> bool:
    source_path = pd.io.common.stringify_path(source)
    target_path = pd.io.common.stringify_path(target)
    if Path(source_path).resolve() == Path(target_path).resolve():
        return Path(target_path).exists()
    try:
        frame = pd.read_csv(source_path)
    except FileNotFoundError:
        return False
    if "manufacturer" in frame.columns:
        frame = frame.loc[frame["manufacturer"].astype(str).eq(config.M1_MANUFACTURER)].copy()
    frame = _sanitize_score_frame(frame)
    pd.DataFrame(frame).to_csv(target_path, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return True


def _resolve_score_source(primary: object, packaged_source: object) -> object:
    primary_path = pd.io.common.stringify_path(primary)
    if Path(primary_path).exists():
        return primary
    return packaged_source


def _use_external_current_best_source() -> bool:
    source_mode = os.environ.get("THIRD_MODEL_CURRENT_BEST_SOURCE_MODE", "local").strip().lower()
    retrain_mode = os.environ.get("THIRD_MODEL_CURRENT_BEST_RETRAIN_MODE", "").strip().lower()
    return source_mode == "external" or retrain_mode == "external"


def _artifact_sources(external_sources: list[Path], local_target: Path, packaged_sources: list[Path]) -> list[Path]:
    if _use_external_current_best_source():
        return [*external_sources, local_target, *packaged_sources]
    return [local_target, *packaged_sources]


def _normalize_copied_metadata(path: Path) -> None:
    if path.suffix.lower() != ".json" or not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    path.write_text(text, encoding="utf-8", newline="\n")


def _materialize_artifact(name: str, sources: list[Path], target: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.exists():
            continue
        same_path = source.resolve() == target.resolve()
        if not same_path:
            copy_if_exists(source, target)
            _normalize_copied_metadata(target)
        return {
            "name": name,
            "status": "already_present" if same_path else "copied",
            "source": config.path_label(source),
            "target": config.path_label(target),
            "exists": target.exists(),
        }
    return {
        "name": name,
        "status": "packaged_existing" if target.exists() else "missing",
        "source": "",
        "target": config.path_label(target),
        "exists": target.exists(),
    }


def materialize_current_best_model_artifacts() -> dict[str, object]:
    """Materialize current-best model artifacts for package-local execution.

    Local/package artifacts are preferred by default. A discovered source
    project is used only when THIRD_MODEL_CURRENT_BEST_SOURCE_MODE=external or
    THIRD_MODEL_CURRENT_BEST_RETRAIN_MODE=external is set.
    """
    config.ensure_dirs()
    specs = [
        (
            "risk_model_best",
            _artifact_sources([config.SOURCE_RISK_MODEL_PATH], config.RISK_MODEL_PATH, []),
            config.RISK_MODEL_PATH,
        ),
        (
            "risk_model_best_metadata",
            _artifact_sources([config.SOURCE_RISK_METADATA_PATH], config.RISK_METADATA_PATH, [config.PACKAGED_RISK_METADATA_PATH]),
            config.RISK_METADATA_PATH,
        ),
        (
            "leadtime_model_best",
            _artifact_sources([config.SOURCE_LEADTIME_MODEL_PATH], config.LEADTIME_MODEL_PATH, []),
            config.LEADTIME_MODEL_PATH,
        ),
        (
            "leadtime_model_best_metadata",
            _artifact_sources([config.SOURCE_LEADTIME_METADATA_PATH], config.LEADTIME_METADATA_PATH, [config.PACKAGED_LEADTIME_METADATA_PATH]),
            config.LEADTIME_METADATA_PATH,
        ),
        (
            "priority_engine_best_metadata",
            _artifact_sources([config.SOURCE_PRIORITY_METADATA_PATH], config.PRIORITY_METADATA_PATH, [config.PACKAGED_PRIORITY_METADATA_PATH]),
            config.PRIORITY_METADATA_PATH,
        ),
    ]
    artifacts = [_materialize_artifact(name, sources, target) for name, sources, target in specs]
    payload = {
        "source_best_root": config.path_label(config.SOURCE_BEST_ROOT, "THIRD_MODEL_SOURCE_BEST_ROOT"),
        "source_best_available": config.SOURCE_BEST_ROOT.exists(),
        "source_mode": "external" if _use_external_current_best_source() else "local",
        "artifacts": artifacts,
        "note": "Anomaly and M1 specialist artifacts are regenerated by their own pipeline steps. Current-best local/package artifacts are preferred unless external source mode is explicitly enabled.",
    }
    write_json(config.MODEL_ARTIFACTS_METADATA_PATH, payload)
    missing = [row["name"] for row in artifacts if not row["exists"]]
    if missing:
        raise FileNotFoundError("Missing model artifacts: " + ", ".join(missing))
    return payload


def materialize_best_scores() -> dict[str, str]:
    """Bring current best risk/leadtime/priority scores into 3rd_model.

    This keeps the current project's best predictive body intact while removing
    optional experiment columns that are outside the active M1 handoff contract.
    """
    config.ensure_dirs()
    if _use_external_current_best_source():
        sources = {
            "risk_scores": _resolve_score_source(config.SOURCE_RISK_SCORES_PATH, config.PACKAGED_SOURCE_RISK_SCORES_PATH),
            "leadtime_scores": _resolve_score_source(
                config.SOURCE_LEADTIME_SCORES_PATH,
                config.PACKAGED_SOURCE_LEADTIME_SCORES_PATH,
            ),
            "priority_scores": _resolve_score_source(
                config.SOURCE_PRIORITY_SCORES_PATH,
                config.PACKAGED_SOURCE_PRIORITY_SCORES_PATH,
            ),
        }
    else:
        sources = {
            "risk_scores": _resolve_score_source(config.RISK_SCORES_PATH, config.PACKAGED_SOURCE_RISK_SCORES_PATH),
            "leadtime_scores": _resolve_score_source(config.LEADTIME_SCORES_PATH, config.PACKAGED_SOURCE_LEADTIME_SCORES_PATH),
            "priority_scores": _resolve_score_source(config.PRIORITY_SCORES_PATH, config.PACKAGED_SOURCE_PRIORITY_SCORES_PATH),
        }
    copied = {
        "risk_scores": _copy_m1_score(sources["risk_scores"], config.RISK_SCORES_PATH),
        "leadtime_scores": _copy_m1_score(sources["leadtime_scores"], config.LEADTIME_SCORES_PATH),
        "priority_scores": _copy_m1_score(sources["priority_scores"], config.PRIORITY_SCORES_PATH),
    }
    missing = [name for name, ok in copied.items() if not ok]
    if missing:
        raise FileNotFoundError(
            "Missing best score outputs: "
            + ", ".join(missing)
            + ". Run the current best pipeline first, or provide score files under the source best output folder "
            + "or artifacts/current_best/source_score_outputs."
        )
    write_json(
        config.OUTPUT_DIR / "best_bridge_metadata.json",
        {
            "source": config.path_label(config.SOURCE_BEST_ROOT, "THIRD_MODEL_SOURCE_BEST_ROOT"),
            "source_best_available": config.SOURCE_BEST_ROOT.exists(),
            "source_mode": "external" if _use_external_current_best_source() else "local",
            "score_sources": {name: config.path_label(path) for name, path in sources.items()},
            "scope": config.PROJECT_SCOPE,
            "manufacturer_filter": config.M1_MANUFACTURER,
            "copied": copied,
            "role": "M1-only subset of current best risk/leadtime/priority output; used as baseline body for M1 specialist comparison",
        },
    )
    return {key: str(value) for key, value in copied.items()}


def _select_priority_columns(priority: pd.DataFrame) -> pd.DataFrame:
    selected = _sanitize_score_frame(priority)
    if "priority_level" not in selected.columns:
        if "priority_score" in selected.columns:
            selected["priority_level"] = pd.cut(
                pd.to_numeric(selected["priority_score"], errors="coerce").fillna(0.0),
                bins=[-np.inf, 35, 55, 75, np.inf],
                labels=["low", "medium", "high", "urgent"],
            ).astype(str)
        else:
            selected["priority_level"] = "low"
    return selected


def build_merged_model_scores() -> pd.DataFrame:
    priority = _select_priority_columns(pd.read_csv(config.PRIORITY_SCORES_PATH))
    anomaly = pd.read_csv(config.ANOMALY_SCORES_PATH)
    anomaly_columns = [
        *config.KEY_COLUMNS,
        "iforest_score_ratio",
        "mahalanobis_score_ratio",
        "anomaly_consensus_count",
        "anomaly_ensemble_score",
        "anomaly_policy_score",
        "anomaly_criticality",
        "anomaly_event_label",
        "strong_anomaly_label",
    ]
    merged = priority.merge(
        anomaly[anomaly_columns].drop_duplicates(config.KEY_COLUMNS),
        on=config.KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        suffixes=("", "_3rd_anomaly"),
    )
    for column in anomaly_columns:
        duplicate = f"{column}_3rd_anomaly"
        if duplicate in merged.columns:
            if column not in merged.columns:
                merged[column] = merged[duplicate]
            else:
                merged[column] = merged[duplicate].combine_first(merged[column])
                merged = merged.drop(columns=[duplicate])
    merged.to_csv(config.MERGED_SCORES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return merged
