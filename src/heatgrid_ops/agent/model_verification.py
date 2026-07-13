from __future__ import annotations

from collections.abc import Iterator
from math import isfinite

from heatgrid_ops.agent.models import JsonObject, JsonValue, ModelVerificationResult
from heatgrid_ops.agent.run_models import ModelInferenceSnapshot


def verify_models(
    snapshot: ModelInferenceSnapshot,
    feature_values: dict[str, float],
    source_input: JsonObject,
    *,
    tolerance: float,
    attempt: int = 1,
) -> ModelVerificationResult:
    if snapshot.error is not None:
        return ModelVerificationResult(
            status="error",
            attempt=attempt,
            feature_count=len(feature_values),
            reasons=[snapshot.error],
        )
    inference = snapshot.payload
    coverage_values = [
        value
        for value in (
            _optional_float(item)
            for item in _mapping(inference.get("feature_coverage")).values()
        )
        if value is not None
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
    _check_delta(checks, reasons, "risk", risk_delta, tolerance)
    _check_equal(checks, reasons, "anomaly", anomaly_label, stored_anomaly)
    _check_equal(checks, reasons, "leadtime", leadtime_bucket, stored_leadtime)
    _check_delta(
        checks,
        reasons,
        "priority",
        priority_delta,
        max(1.0, tolerance * 100.0),
    )
    if not snapshot.usable:
        reasons.append(
            _optional_text(inference.get("inference_error"))
            or "model input is incomplete"
        )

    return ModelVerificationResult(
        status=_verification_status(snapshot.usable, checks),
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


def _verification_status(usable: bool, checks: dict[str, bool]) -> str:
    if usable and len(checks) >= 3:
        return "verified"
    if usable:
        return "partial"
    return "unavailable"


def _check_delta(
    checks: dict[str, bool],
    reasons: list[str],
    name: str,
    delta: float | None,
    tolerance: float,
) -> None:
    if delta is None:
        return
    checks[name] = delta <= tolerance
    if not checks[name]:
        reasons.append(f"stored and active {name} scores exceed tolerance")


def _check_equal(
    checks: dict[str, bool],
    reasons: list[str],
    name: str,
    active: JsonValue,
    stored: JsonValue,
) -> None:
    if active is None or stored is None:
        return
    checks[name] = active == stored
    if not checks[name]:
        reasons.append(f"stored and active {name} labels disagree")


def _stored_float(
    source_input: JsonObject,
    names: tuple[str, ...],
) -> float | None:
    return next(
        (
            converted
            for value in _stored_values(source_input, names)
            if (converted := _optional_float(value)) is not None
        ),
        None,
    )


def _stored_text(
    source_input: JsonObject,
    names: tuple[str, ...],
) -> str | None:
    return next(
        (
            converted
            for value in _stored_values(source_input, names)
            if (converted := _optional_text(value)) is not None
        ),
        None,
    )


def _stored_bool(
    source_input: JsonObject,
    names: tuple[str, ...],
) -> bool | None:
    return next(
        (
            converted
            for value in _stored_values(source_input, names)
            if (converted := _optional_bool(value)) is not None
        ),
        None,
    )


def _stored_values(
    source_input: JsonObject,
    names: tuple[str, ...],
) -> Iterator[JsonValue]:
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
                mapping = _mapping(item)
                if mapping.get("score_name") == name:
                    yield mapping.get("score_value")
    summaries = _mapping(source_input.get("raw_context")).get("sensor_summaries")
    if isinstance(summaries, list):
        for name in names:
            for item in summaries:
                mapping = _mapping(item)
                if mapping.get("feature_name") == name:
                    yield mapping.get("feature_value")


def _mapping(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _delta(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else abs(left - right)


def _optional_float(value: JsonValue | None) -> float | None:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return numeric if isfinite(numeric) else None


def _optional_text(value: JsonValue | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: JsonValue | None) -> bool | None:
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
