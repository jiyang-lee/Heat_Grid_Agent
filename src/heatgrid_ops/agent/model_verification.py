from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from schemas import JsonValue, ModelVerificationResult

ROOT = Path(__file__).resolve().parents[3]


def verify_models(
    feature_values: dict[str, float],
    source_input: dict[str, JsonValue],
    *,
    tolerance: float,
    attempt: int = 1,
    active_artifact_uri: str | None = None,
) -> ModelVerificationResult:
    model_root = _model_root(active_artifact_uri)
    reasons: list[str] = []
    try:
        risk = _verify_risk(model_root, feature_values)
        anomaly = _verify_anomaly(model_root, feature_values)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return ModelVerificationResult(
            status="error",
            attempt=attempt,
            feature_count=len(feature_values),
            reasons=[str(exc)],
        )

    coverages = [item["coverage"] for item in (risk, anomaly) if item["available"]]
    coverage = min(coverages) if coverages else 0.0
    stored_risk = _stored_score(source_input, ("risk_probability", "risk_score"))
    risk_score = _optional_float(risk.get("score"))
    risk_delta = (
        abs(risk_score - stored_risk)
        if risk_score is not None and stored_risk is not None
        else None
    )
    stored_anomaly = _stored_bool(source_input, "anomaly_event_label")
    anomaly_label = anomaly.get("label")

    checks: list[bool] = []
    if risk_delta is not None:
        checks.append(risk_delta <= tolerance)
        if risk_delta > tolerance:
            reasons.append("저장된 위험도와 현재 활성 위험도 모델의 차이가 허용 범위를 넘었습니다.")
    if stored_anomaly is not None and isinstance(anomaly_label, bool):
        checks.append(stored_anomaly == anomaly_label)
        if stored_anomaly != anomaly_label:
            reasons.append("저장된 이상탐지 판정과 현재 활성 모델 판정이 다릅니다.")
    if coverage < 0.8:
        reasons.append("재검증 입력 특성의 80% 이상을 확보하지 못했습니다.")

    if risk["available"] and anomaly["available"] and coverage >= 0.8:
        status = "verified"
    elif risk["available"] or anomaly["available"]:
        status = "partial"
    else:
        status = "unavailable"
        reasons.append("실행 가능한 모델 아티팩트를 찾지 못했습니다.")

    return ModelVerificationResult(
        status=status,
        attempt=attempt,
        feature_count=len(feature_values),
        feature_coverage=round(float(coverage), 4),
        risk_score=risk_score,
        stored_risk_score=stored_risk,
        risk_score_delta=None if risk_delta is None else round(risk_delta, 6),
        anomaly_score=_optional_float(anomaly.get("score")),
        anomaly_label=anomaly_label if isinstance(anomaly_label, bool) else None,
        agreement=all(checks) if checks else None,
        active_model_version=str(risk.get("version") or anomaly.get("version") or "") or None,
        reasons=reasons,
    )


def _verify_risk(model_root: Path, features: dict[str, float]) -> dict[str, Any]:
    model_path = model_root / "risk" / "risk_model_best.joblib"
    metadata_path = model_root / "risk" / "risk_model_best_metadata.json"
    if not model_path.exists() or not metadata_path.exists():
        return {"available": False, "coverage": 0.0}
    metadata = _read_json(metadata_path)
    columns = [str(item) for item in metadata.get("model_feature_columns", [])]
    matrix, coverage = _matrix(features, columns)
    model = _load_model(str(model_path))
    probabilities = model.predict_proba(matrix)
    classes = list(getattr(model, "classes_", []))
    positive_index = _positive_class_index(classes, probabilities.shape[1])
    return {
        "available": True,
        "coverage": coverage,
        "score": float(probabilities[0, positive_index]),
        "version": metadata.get("model_version"),
    }


def _verify_anomaly(model_root: Path, features: dict[str, float]) -> dict[str, Any]:
    anomaly_root = model_root / "anomaly"
    paths = {
        "scaler": anomaly_root / "standard_scaler.joblib",
        "iforest": anomaly_root / "isolation_forest.joblib",
        "mahalanobis": anomaly_root / "mahalanobis_ledoitwolf.joblib",
        "metadata": anomaly_root / "anomaly_metadata.json",
    }
    if not all(path.exists() for path in paths.values()):
        return {"available": False, "coverage": 0.0}
    metadata = _read_json(paths["metadata"])
    columns = [str(item) for item in metadata.get("feature_columns", [])]
    matrix, coverage = _matrix(features, columns)
    scaled = _load_model(str(paths["scaler"])).transform(matrix)
    iforest_score = float(-_load_model(str(paths["iforest"])).score_samples(scaled)[0])
    mahalanobis_score = float(
        _load_model(str(paths["mahalanobis"])).mahalanobis(scaled)[0]
    )
    iforest_threshold = float(metadata["iforest_threshold"])
    mahalanobis_threshold = float(metadata["mahalanobis_threshold"])
    iforest_ratio = iforest_score / max(iforest_threshold, 1e-12)
    mahalanobis_ratio = mahalanobis_score / max(mahalanobis_threshold, 1e-12)
    iforest_policy = float(metadata.get("iforest_policy_ratio_threshold", 0.9))
    mahalanobis_policy = float(metadata.get("mahalanobis_policy_ratio_threshold", 1.0))
    score = min(iforest_ratio / iforest_policy, mahalanobis_ratio / mahalanobis_policy)
    return {
        "available": True,
        "coverage": coverage,
        "score": float(score),
        "label": bool(iforest_ratio >= iforest_policy and mahalanobis_ratio >= mahalanobis_policy),
        "version": metadata.get("model_version"),
    }


def _matrix(features: dict[str, float], columns: list[str]) -> tuple[pd.DataFrame, float]:
    imputation = _imputation_values()
    present = sum(1 for column in columns if column in features)
    values = {
        column: _finite_float(features.get(column), imputation.get(column, 0.0))
        for column in columns
    }
    coverage = present / max(1, len(columns))
    return pd.DataFrame([values], columns=columns, dtype="float64"), coverage


def _stored_score(source_input: dict[str, JsonValue], names: tuple[str, ...]) -> float | None:
    priority_context = source_input.get("priority_context")
    if not isinstance(priority_context, dict):
        return None
    outputs = priority_context.get("model_outputs")
    if isinstance(outputs, list):
        for name in names:
            for item in outputs:
                if isinstance(item, dict) and item.get("score_name") == name:
                    value = _optional_float(item.get("score_value"))
                    if value is not None:
                        return value
    raw_context = source_input.get("raw_context")
    summaries = raw_context.get("sensor_summaries") if isinstance(raw_context, dict) else None
    if isinstance(summaries, list):
        for name in names:
            for item in summaries:
                if isinstance(item, dict) and item.get("feature_name") == name:
                    value = _optional_float(item.get("feature_value"))
                    if value is not None:
                        return value
    return None


def _stored_bool(source_input: dict[str, JsonValue], name: str) -> bool | None:
    value = _stored_score(source_input, (name,))
    return None if value is None else value >= 0.5


def _model_root(active_artifact_uri: str | None) -> Path:
    if active_artifact_uri:
        candidate = Path(active_artifact_uri)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        nested = candidate / "models"
        return nested if nested.exists() else candidate
    return ROOT / "models"


@lru_cache(maxsize=16)
def _load_model(path: str):
    return joblib.load(path)


@lru_cache(maxsize=8)
def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _imputation_values() -> dict[str, float]:
    path = ROOT / "data" / "processed" / "imputation_values.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    return {
        str(row.column_name): _finite_float(row.imputation_value, 0.0)
        for row in frame.itertuples(index=False)
    }


def _positive_class_index(classes: list[Any], width: int) -> int:
    for candidate in (1, True, "1", "pre_fault"):
        if candidate in classes:
            return classes.index(candidate)
    return max(0, width - 1)


def _finite_float(value: Any, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return numeric if np.isfinite(numeric) else fallback


def _optional_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None
