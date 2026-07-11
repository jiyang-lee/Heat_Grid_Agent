from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from heatgrid_ops.priority.inference import (
    PriorityInferenceError,
    PriorityInferenceRuntime,
)
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
    try:
        runtime = PriorityInferenceRuntime(
            model_root=_model_root(active_artifact_uri),
            deployment_version=_deployment_version(active_artifact_uri),
        )
        inference = runtime.infer_batch(
            [
                {
                    **_source_identity(source_input),
                    "feature_values": feature_values,
                }
            ]
        )[0]
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        PriorityInferenceError,
    ) as exc:
        return ModelVerificationResult(
            status="error",
            attempt=attempt,
            feature_count=len(feature_values),
            reasons=[str(exc)],
        )

    coverage_values = [
        float(value)
        for value in inference.get("feature_coverage", {}).values()
    ]
    coverage = min(coverage_values) if coverage_values else 0.0
    risk_score = _optional_float(inference.get("risk_score"))
    stored_risk = _stored_float(source_input, ("risk_score", "risk_probability"))
    risk_delta = _delta(risk_score, stored_risk)
    anomaly_label = _optional_bool(inference.get("anomaly_label"))
    stored_anomaly = _stored_bool(
        source_input,
        ("anomaly_label", "anomaly_event_label"),
    )
    leadtime_bucket = _optional_text(inference.get("leadtime_bucket"))
    stored_leadtime = _stored_text(
        source_input,
        ("leadtime_bucket", "predicted_lead_time_bucket"),
    )
    priority_score = _optional_float(inference.get("priority_score"))
    stored_priority = _stored_float(source_input, ("priority_score",))
    priority_delta = _delta(priority_score, stored_priority)

    checks: dict[str, bool] = {}
    reasons: list[str] = []
    if risk_delta is not None:
        checks["risk"] = risk_delta <= tolerance
        if not checks["risk"]:
            reasons.append("stored and active risk scores exceed tolerance")
    if anomaly_label is not None and stored_anomaly is not None:
        checks["anomaly"] = anomaly_label == stored_anomaly
        if not checks["anomaly"]:
            reasons.append("stored and active anomaly labels disagree")
    if leadtime_bucket is not None and stored_leadtime is not None:
        checks["leadtime"] = leadtime_bucket == stored_leadtime
        if not checks["leadtime"]:
            reasons.append("stored and active lead-time buckets disagree")
    if priority_delta is not None:
        priority_tolerance = max(1.0, tolerance * 100.0)
        checks["priority"] = priority_delta <= priority_tolerance
        if not checks["priority"]:
            reasons.append("stored and active priority scores exceed tolerance")
    if not inference.get("usable"):
        reasons.append(
            str(inference.get("inference_error") or "model input is incomplete")
        )

    if inference.get("usable") and len(checks) >= 3:
        status = "verified"
    elif inference.get("usable"):
        status = "partial"
    else:
        status = "unavailable"

    return ModelVerificationResult(
        status=status,
        attempt=attempt,
        feature_count=len(feature_values),
        feature_coverage=round(coverage, 4),
        risk_score=risk_score,
        stored_risk_score=stored_risk,
        risk_score_delta=None if risk_delta is None else round(risk_delta, 6),
        anomaly_score=_optional_float(inference.get("anomaly_score")),
        anomaly_label=anomaly_label,
        leadtime_bucket=leadtime_bucket,
        stored_leadtime_bucket=stored_leadtime,
        priority_score=priority_score,
        stored_priority_score=stored_priority,
        priority_score_delta=None
        if priority_delta is None
        else round(priority_delta, 6),
        priority_level=_optional_text(inference.get("priority_level")),
        m1_specialist_priority_score=_optional_float(
            inference.get("m1_specialist_priority_score")
        ),
        component_agreement=checks,
        agreement=all(checks.values()) if checks else None,
        active_model_version=_optional_text(inference.get("model_version")),
        reasons=reasons,
    )


def _source_identity(source_input: dict[str, JsonValue]) -> dict[str, Any]:
    evaluation_context = _mapping(source_input.get("evaluation_context"))
    evaluation_result = _mapping(evaluation_context.get("result"))
    raw_context = _mapping(source_input.get("raw_context"))
    window = _mapping(raw_context.get("window"))
    substation = _mapping(raw_context.get("substation"))
    return {
        "manufacturer_id": evaluation_result.get("manufacturer_id")
        or window.get("manufacturer_id")
        or window.get("manufacturer"),
        "substation_id": evaluation_result.get("substation_id")
        or window.get("substation_id")
        or substation.get("substation_id"),
        "configuration_type": substation.get("configuration_type")
        or window.get("configuration_type"),
    }


def _stored_float(
    source_input: dict[str, JsonValue],
    names: tuple[str, ...],
) -> float | None:
    for value in _stored_values(source_input, names):
        converted = _optional_float(value)
        if converted is not None:
            return converted
    return None


def _stored_text(
    source_input: dict[str, JsonValue],
    names: tuple[str, ...],
) -> str | None:
    for value in _stored_values(source_input, names):
        converted = _optional_text(value)
        if converted is not None:
            return converted
    return None


def _stored_bool(
    source_input: dict[str, JsonValue],
    names: tuple[str, ...],
) -> bool | None:
    for value in _stored_values(source_input, names):
        converted = _optional_bool(value)
        if converted is not None:
            return converted
    return None


def _stored_values(
    source_input: dict[str, JsonValue],
    names: tuple[str, ...],
):
    evaluation_context = _mapping(source_input.get("evaluation_context"))
    containers = [_mapping(evaluation_context.get("result"))]
    priority_context = _mapping(source_input.get("priority_context"))
    containers.extend(
        _mapping(priority_context.get(name))
        for name in ("priority", "card", "model_signals", "explanation")
    )
    for name in names:
        for container in containers:
            if name in container:
                yield container[name]
    outputs = priority_context.get("model_outputs")
    if isinstance(outputs, list):
        for name in names:
            for item in outputs:
                if isinstance(item, dict) and item.get("score_name") == name:
                    yield item.get("score_value")
    raw_context = _mapping(source_input.get("raw_context"))
    summaries = raw_context.get("sensor_summaries")
    if isinstance(summaries, list):
        for name in names:
            for item in summaries:
                if isinstance(item, dict) and item.get("feature_name") == name:
                    yield item.get("feature_value")


def _model_root(active_artifact_uri: str | None) -> Path:
    if active_artifact_uri:
        candidate = Path(active_artifact_uri)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        nested = candidate / "models"
        return nested if nested.exists() else candidate
    return ROOT / "models"


def _deployment_version(active_artifact_uri: str | None) -> str:
    if not active_artifact_uri:
        return "active-local-model"
    return f"active-deployment-{Path(active_artifact_uri).name}"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _delta(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else abs(left - right)


def _optional_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None
