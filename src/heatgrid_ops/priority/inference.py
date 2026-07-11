from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

ANOMALY_WEIGHTS = {"iforest": 0.47, "mahalanobis": 0.53}
LEADTIME_LABELS = ("0-24h", "1-3d", "3-7d")
LEADTIME_MIDPOINT_HOURS = np.array([12.0, 48.0, 120.0], dtype="float64")
DEFAULT_M1_PRIORITY_THRESHOLDS = {
    "specialist": {"high": 75.0, "urgent": 90.0},
    "hybrid": {"high": 82.5, "urgent": 95.0},
}
INFERENCE_CONTRACT_VERSION = "same-run-priority-inference-v2"


class PriorityInferenceError(RuntimeError):
    pass


class PriorityInferenceRuntime:
    """Loads one model bundle and scores a same-time substation batch."""

    def __init__(
        self,
        *,
        model_root: str | Path | None = None,
        deployment_version: str | None = None,
        minimum_feature_coverage: float = 0.75,
    ) -> None:
        self.model_root = _resolve_model_root(model_root)
        self.deployment_version = deployment_version
        self.minimum_feature_coverage = minimum_feature_coverage
        self.metadata = self._load_metadata()
        self.model_version = _bundle_version(
            self.model_root,
            self.metadata,
            deployment_version=deployment_version,
        )

    def infer_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        features = [_numeric_features(row.get("feature_values")) for row in rows]
        anomaly = self._infer_anomaly(features)

        enriched = []
        for source, anomaly_result in zip(features, anomaly, strict=True):
            values = dict(source)
            values.update(anomaly_result["features"])
            enriched.append(values)

        risk = self._infer_risk(rows, enriched)
        for values, risk_result in zip(enriched, risk, strict=True):
            values.update(risk_result["features"])

        leadtime = self._infer_leadtime(enriched)
        m1 = self._infer_m1(rows, enriched, leadtime)

        results: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            current_best = _score_current_best(
                enriched[index],
                risk[index],
                anomaly[index],
                leadtime[index],
                self.metadata["priority"],
            )
            final = _score_hybrid(
                current_best,
                m1[index],
                self.metadata["m1_gate"],
            )
            coverage = {
                "anomaly": anomaly[index]["coverage"],
                "risk": risk[index]["coverage"],
                "leadtime": leadtime[index]["coverage"],
                "m1_specialist": m1[index]["coverage"],
            }
            required_coverages = [coverage["anomaly"], coverage["risk"], coverage["leadtime"]]
            if _is_m1_scope(row):
                required_coverages.append(coverage["m1_specialist"])
            usable = min(required_coverages) >= self.minimum_feature_coverage
            results.append(
                {
                    **final,
                    "risk_score": risk[index]["score"],
                    "risk_probability": risk[index]["probability"],
                    "risk_level": risk[index]["level"],
                    "anomaly_score": anomaly[index]["policy_score"],
                    "anomaly_label": anomaly[index]["label"],
                    "leadtime_bucket": leadtime[index]["bucket"],
                    "leadtime_urgency_score": leadtime[index]["urgency_score"],
                    "leadtime_hours": leadtime[index]["expected_hours"],
                    "feature_coverage": coverage,
                    "usable": usable,
                    "model_version": self.model_version,
                    "model_versions": {
                        "risk": self.metadata["risk"].get("model_version"),
                        "anomaly": self.metadata["anomaly"].get("model_version"),
                        "leadtime": self.metadata["leadtime"].get("model_version"),
                        "priority": self.metadata["priority"].get("engine_version"),
                        "m1_specialist": self.metadata["m1_runtime"].get("package_id"),
                    },
                    "inference_status": "completed" if usable else "insufficient_features",
                    "inference_error": None
                    if usable
                    else f"minimum feature coverage is {self.minimum_feature_coverage:.2f}",
                    "components": {
                        "risk": risk[index],
                        "anomaly": anomaly[index],
                        "leadtime": leadtime[index],
                        "current_best": current_best,
                        "m1_specialist": m1[index],
                    },
                }
            )
        return results

    def _load_metadata(self) -> dict[str, dict[str, Any]]:
        paths = {
            "risk": self.model_root / "risk" / "risk_model_best_metadata.json",
            "anomaly": self.model_root / "anomaly" / "anomaly_metadata.json",
            "leadtime": self.model_root / "leadtime" / "leadtime_model_best_metadata.json",
            "priority": self.model_root / "priority" / "priority_engine_best_metadata.json",
            "m1_gate": self.model_root / "m1_specialist" / "m1_specialist_gate_metadata.json",
            "m1_runtime": self.model_root
            / "m1_specialist"
            / "m1_full_gate_runtime_policy_metadata.json",
        }
        missing = [str(path) for path in paths.values() if not path.exists()]
        if missing:
            raise PriorityInferenceError("model metadata is missing: " + ", ".join(missing))
        return {name: _read_json(path) for name, path in paths.items()}

    def _infer_anomaly(self, rows: list[dict[str, float]]) -> list[dict[str, Any]]:
        metadata = self.metadata["anomaly"]
        columns = [str(item) for item in metadata.get("feature_columns", [])]
        matrix, coverages = _matrix(rows, columns)
        root = self.model_root / "anomaly"
        scaled = _load_model(str(root / "standard_scaler.joblib")).transform(matrix)
        iforest_scores = -_load_model(str(root / "isolation_forest.joblib")).score_samples(scaled)
        mahalanobis_scores = _load_model(str(root / "mahalanobis_ledoitwolf.joblib")).mahalanobis(scaled)
        iforest_threshold = float(metadata["iforest_threshold"])
        mahalanobis_threshold = float(metadata["mahalanobis_threshold"])
        iforest_policy = float(metadata.get("iforest_policy_ratio_threshold", 0.9))
        mahalanobis_policy = float(metadata.get("mahalanobis_policy_ratio_threshold", 1.0))
        results: list[dict[str, Any]] = []
        for index in range(len(rows)):
            iforest_score = float(iforest_scores[index])
            mahalanobis_score = float(mahalanobis_scores[index])
            iforest_ratio = iforest_score / max(iforest_threshold, 1e-12)
            mahalanobis_ratio = mahalanobis_score / max(mahalanobis_threshold, 1e-12)
            consensus = int(iforest_ratio >= iforest_policy) + int(
                mahalanobis_ratio >= mahalanobis_policy
            )
            ensemble = (
                ANOMALY_WEIGHTS["iforest"] * iforest_ratio
                + ANOMALY_WEIGHTS["mahalanobis"] * mahalanobis_ratio
            )
            policy_score = min(iforest_ratio / iforest_policy, mahalanobis_ratio / mahalanobis_policy)
            persisted_criticality = _number(rows[index].get("anomaly_criticality"), 0.0)
            criticality = persisted_criticality if consensus == 2 else 0.0
            event_label = bool(
                consensus == 2
                and criticality >= float(metadata.get("criticality_threshold", 5.0))
            )
            output_features = {
                "iforest_anomaly_score": iforest_score,
                "mahalanobis_score": mahalanobis_score,
                "iforest_score_ratio": iforest_ratio,
                "mahalanobis_score_ratio": mahalanobis_ratio,
                "anomaly_consensus_count": float(consensus),
                "anomaly_ensemble_score": ensemble,
                "anomaly_policy_score": policy_score,
                "anomaly_score": policy_score,
                "strong_anomaly_label": float(iforest_ratio >= 1.0 and mahalanobis_ratio >= 1.0),
                "anomaly_criticality": criticality,
                "anomaly_event_label": float(event_label),
            }
            results.append(
                {
                    "score": ensemble,
                    "policy_score": policy_score,
                    "label": bool(consensus == 2),
                    "event_label": event_label,
                    "consensus_count": consensus,
                    "criticality": criticality,
                    "coverage": coverages[index],
                    "features": output_features,
                }
            )
        return results

    def _infer_risk(
        self,
        source_rows: list[dict[str, Any]],
        rows: list[dict[str, float]],
    ) -> list[dict[str, Any]]:
        metadata = self.metadata["risk"]
        columns = [str(item) for item in metadata.get("model_feature_columns", [])]
        matrix, coverages = _matrix(rows, columns)
        model = _load_model(str(self.model_root / "risk" / "risk_model_best.joblib"))
        probabilities = model.predict_proba(matrix)
        positive_index = _positive_class_index(list(getattr(model, "classes_", [])), probabilities.shape[1])
        results: list[dict[str, Any]] = []
        for index, source_row in enumerate(source_rows):
            probability = float(probabilities[index, positive_index])
            roll4 = _number(rows[index].get("risk_probability_roll4_max"), probability)
            roll8 = _number(rows[index].get("risk_probability_roll8_mean"), probability)
            score = max(probability, 0.9 * roll4, min(1.0, 1.05 * roll8))
            thresholds = _risk_thresholds(metadata, source_row)
            level = _risk_level(score, thresholds)
            results.append(
                {
                    "probability": probability,
                    "score": score,
                    "level": level,
                    "thresholds": thresholds,
                    "coverage": coverages[index],
                    "features": {
                        "risk_probability_raw": probability,
                        "risk_probability": probability,
                        "risk_score": score,
                        "risk_temporal_boost": max(0.0, score - probability),
                        "risk_level_calibrated": level,
                        "risk_high_or_critical": float(level in {"high", "critical"}),
                    },
                }
            )
        return results

    def _infer_leadtime(self, rows: list[dict[str, float]]) -> list[dict[str, Any]]:
        metadata = self.metadata["leadtime"]
        columns = [str(item) for item in metadata.get("model_feature_columns", [])]
        matrix, coverages = _matrix(rows, columns)
        model = _load_model(str(self.model_root / "leadtime" / "leadtime_model_best.joblib"))
        probabilities = model.predict_proba(matrix)
        classes = list(getattr(model, "classes_", range(probabilities.shape[1])))
        full = np.zeros((len(rows), len(LEADTIME_LABELS)), dtype="float64")
        for source_index, model_class in enumerate(classes):
            target_index = _leadtime_class_index(model_class)
            if target_index is not None:
                full[:, target_index] = probabilities[:, source_index]
        results: list[dict[str, Any]] = []
        for index in range(len(rows)):
            predicted_index = int(full[index].argmax())
            expected_hours = float(full[index].dot(LEADTIME_MIDPOINT_HOURS))
            urgency = float(
                np.clip(
                    1.0
                    - (expected_hours - LEADTIME_MIDPOINT_HOURS.min())
                    / (LEADTIME_MIDPOINT_HOURS.max() - LEADTIME_MIDPOINT_HOURS.min()),
                    0.0,
                    1.0,
                )
            )
            results.append(
                {
                    "bucket": LEADTIME_LABELS[predicted_index],
                    "confidence": float(full[index].max()),
                    "probabilities": {
                        label: float(full[index, label_index])
                        for label_index, label in enumerate(LEADTIME_LABELS)
                    },
                    "expected_hours": expected_hours,
                    "urgency_score": urgency,
                    "coverage": coverages[index],
                }
            )
        return results

    def _infer_m1(
        self,
        source_rows: list[dict[str, Any]],
        rows: list[dict[str, float]],
        leadtime: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        runtime = self.metadata["m1_runtime"]
        models = runtime.get("models", {})
        feature_names = list(
            dict.fromkeys(
                str(feature)
                for model_metadata in models.values()
                for feature in model_metadata.get("features", [])
            )
        )
        matrix, coverages = _matrix(rows, feature_names)
        probabilities: dict[str, np.ndarray] = {}
        for model_name, model_metadata in models.items():
            relative = Path(str(model_metadata["model_path"]))
            model_path = self.model_root / relative.relative_to("models")
            model = _compat_model(_load_model(str(model_path)))
            predicted = model.predict_proba(matrix)
            positive_index = _positive_class_index(
                list(getattr(model, "classes_", [])), predicted.shape[1]
            )
            probabilities[model_name] = predicted[:, positive_index]

        thresholds = runtime.get("runtime_policy", {}).get("thresholds", {})
        results: list[dict[str, Any]] = []
        for index, source_row in enumerate(source_rows):
            in_scope = _is_m1_scope(source_row)
            values = {
                name: float(probabilities[name][index]) if in_scope else 0.0
                for name in probabilities
            }
            active = [
                state
                for state, model_name in (
                    ("fault", "fault_gate"),
                    ("task", "task_gate"),
                    ("activity", "activity_gate"),
                )
                if values.get(model_name, 0.0)
                >= float(thresholds.get(model_name, 0.5))
            ]
            primary_state = (
                "out_of_scope"
                if not in_scope
                else "fault"
                if "fault" in active
                else "task"
                if "task" in active
                else "activity"
                if "activity" in active
                else "normal"
            )
            review_reasons: list[str] = []
            if len(active) > 1:
                review_reasons.append("multiple_m1_specialist_gates_positive")
            if any(0.45 <= values.get(name, 0.0) <= 0.55 for name in ("fault_gate", "task_gate", "activity_gate")):
                review_reasons.append("m1_specialist_gate_near_threshold")
            if "activity" in active:
                review_reasons.append("m1_specialist_activity_context")
            if in_scope:
                review_reasons.append("fault_group_requires_runtime_review")
            group_weight = 0.1
            score = 100.0 * (
                0.55 * values.get("fault_pre_event_gate", 0.0)
                + 0.30 * leadtime[index]["urgency_score"]
                + 0.15 * group_weight
            )
            level = _policy_level(
                score,
                _m1_thresholds(self.metadata["m1_gate"], "specialist"),
            )
            results.append(
                {
                    "score": score,
                    "level": level,
                    "fault_probability": values.get("fault_gate"),
                    "task_probability": values.get("task_gate"),
                    "activity_probability": values.get("activity_gate"),
                    "pre_event_probability": values.get("fault_pre_event_gate"),
                    "primary_state": primary_state,
                    "secondary_states": [state for state in active if state != primary_state],
                    "fault_group": "unknown_review",
                    "group_weight": group_weight,
                    "review_required": bool(review_reasons) or not in_scope,
                    "review_reasons": review_reasons
                    if in_scope
                    else ["m1_model_out_of_scope"],
                    "coverage": coverages[index] if in_scope else 1.0,
                }
            )
        return results


def _score_current_best(
    features: dict[str, float],
    risk: dict[str, Any],
    anomaly: dict[str, Any],
    leadtime: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    risk_points = metadata.get("risk_level_points", {})
    leadtime_points = metadata.get("leadtime_bucket_points", {})
    risk_base = _number(risk_points.get(risk["level"]), 0.0)
    risk_probability_component = _clamp(risk["score"] * 18.0, 0.0, 18.0)
    confidence = leadtime["confidence"]
    confidence_multiplier = 1.0 if confidence >= 0.8 else 0.8 if confidence >= 0.6 else 0.6
    leadtime_component = (
        _number(leadtime_points.get(leadtime["bucket"]), 0.0)
        * confidence_multiplier
        * float(metadata.get("leadtime_component_scale", 0.75))
    )
    leadtime_ordinal = (
        _clamp(leadtime["urgency_score"] * 4.0, 0.0, 4.0)
        * float(metadata.get("leadtime_ordinal_component_scale", 0.75))
    )
    anomaly_component = (
        _clamp((anomaly["score"] - 0.8) * 10.0, 0.0, 8.0)
        + (3.0 if anomaly["consensus_count"] >= 2 else 1.0 if anomaly["consensus_count"] >= 1 else 0.0)
        + _clamp(anomaly["criticality"] * 0.6, 0.0, 3.0)
    )
    multi_window = _multi_window_component(features)
    risk_episode = _risk_episode_component(features)
    multi_horizon = _multi_horizon_component(features)
    history_adjustment, history_reason = _history_adjustment(features)
    urgency_bonus, urgency_reason = _urgency_bonus(risk, anomaly, leadtime)
    components = {
        "risk_base": risk_base,
        "risk_probability": risk_probability_component,
        "leadtime_bucket": leadtime_component,
        "leadtime_ordinal": leadtime_ordinal,
        "anomaly": anomaly_component,
        "multi_window_anomaly": multi_window,
        "risk_episode": risk_episode,
        "multi_horizon": multi_horizon,
        "history_adjustment": history_adjustment,
        "urgency_bonus": urgency_bonus,
    }
    score = round(_clamp(sum(components.values()), 0.0, 100.0), 4)
    return {
        "score": score,
        "level": _policy_level(score, metadata.get("priority_level_thresholds", {})),
        "score_components": components,
        "history_adjustment_reason": history_reason,
        "urgency_bonus_reason": urgency_reason,
    }


def _score_hybrid(
    current_best: dict[str, Any],
    specialist: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    score = 0.65 * float(current_best["score"]) + 0.35 * float(specialist["score"])
    level = _policy_level(score, _m1_thresholds(metadata, "hybrid"))
    current_high = current_best["level"] in {"high", "urgent"}
    specialist_high = specialist["level"] in {"high", "urgent"}
    agreement = (
        "both_high"
        if current_high and specialist_high
        else "current_only_high"
        if current_high
        else "m1_specialist_only_high"
        if specialist_high
        else "both_not_high"
    )
    return {
        "priority_score": round(score, 4),
        "priority_level": level,
        "priority_source": "m1_hybrid_current_best_0.65_m1_specialist_0.35",
        "current_best_priority_score": current_best["score"],
        "current_best_priority_level": current_best["level"],
        "m1_specialist_priority_score": round(float(specialist["score"]), 4),
        "m1_specialist_priority_level": specialist["level"],
        "m1_priority_agreement": agreement,
    }


def _multi_window_component(features: dict[str, float]) -> float:
    score = _clamp(_number(features.get("mw_anomaly_context_score"), 0.0) * 0.45, 0.0, 4.5)
    score += _clamp(_number(features.get("mw_anomaly_multi_window_count"), 0.0) * 0.8, 0.0, 3.0)
    for name, points in (
        ("mw_anomaly_short_term_confirmed", 1.5),
        ("mw_anomaly_main_confirmed", 3.0),
        ("mw_anomaly_persistent_confirmed", 2.5),
        ("mw_anomaly_operational_confirmed", 1.0),
    ):
        if _number(features.get(name), 0.0) >= 1.0:
            score += points
    return _clamp(score, 0.0, 12.0)


def _risk_episode_component(features: dict[str, float]) -> float:
    score = _clamp(_number(features.get("risk_recent_high_count_48h"), 0.0) * 1.5, 0.0, 4.5)
    if _number(features.get("risk_repeated_high_48h"), 0.0) >= 1.0:
        score += 5.0
    elif _number(features.get("risk_repeated_watch_48h"), 0.0) >= 1.0:
        score += 2.0
    score += _clamp(_number(features.get("risk_temporal_boost"), 0.0) * 8.0, 0.0, 3.0)
    return _clamp(score, 0.0, 10.0)


def _multi_horizon_component(features: dict[str, float]) -> float:
    score = _clamp(_number(features.get("multi_horizon_persistence_score"), 0.0), 0.0, 12.0)
    for name, threshold in (("risk_high_count_24h", 2.0), ("risk_high_count_3d", 4.0), ("risk_high_count_7d", 8.0)):
        if _number(features.get(name), 0.0) >= threshold:
            score += 2.0
    return _clamp(score, 0.0, 18.0)


def _history_adjustment(features: dict[str, float]) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    for name, week, month, reason in (
        ("days_since_last_task_event", -8.0, -4.0, "recent_task"),
        ("days_since_last_any_event", -5.0, -2.0, "recent_any_event"),
    ):
        value = _optional_number(features.get(name))
        if value is None:
            continue
        if value <= 7:
            score += week
            reasons.append(f"{reason}_within_7d")
        elif value <= 30:
            score += month
            reasons.append(f"{reason}_within_30d")
    return score, "|".join(reasons)


def _urgency_bonus(
    risk: dict[str, Any],
    anomaly: dict[str, Any],
    leadtime: dict[str, Any],
) -> tuple[float, str]:
    if risk["level"] in {"high", "critical"} and leadtime["bucket"] == "0-24h" and anomaly["consensus_count"] >= 2:
        return 8.0, "high_risk_0_24h_strong_anomaly"
    if risk["level"] in {"high", "critical"} and leadtime["bucket"] in {"0-24h", "1-3d"} and anomaly["criticality"] >= 5:
        return 5.0, "high_risk_near_leadtime_criticality"
    return 0.0, ""


def _risk_thresholds(metadata: dict[str, Any], row: dict[str, Any]) -> dict[str, float]:
    thresholds = {
        name: float(value)
        for name, value in metadata.get("base_thresholds", {}).items()
    }
    manufacturer = str(row.get("manufacturer_id") or row.get("manufacturer") or "")
    configuration = str(row.get("configuration_type") or "")
    for override in metadata.get("group_overrides", []):
        if str(override.get("manufacturer")) == manufacturer and str(override.get("configuration_type")) == configuration:
            thresholds.update(
                {
                    name: float(value)
                    for name, value in override.get("applied_thresholds", {}).items()
                }
            )
            break
    return thresholds


def _risk_level(score: float, thresholds: dict[str, float]) -> str:
    if score >= thresholds.get("critical", 1.0):
        return "critical"
    if score >= thresholds.get("high", 1.0):
        return "high"
    if score >= thresholds.get("medium", 1.0):
        return "medium"
    return "low"


def _m1_thresholds(metadata: dict[str, Any], policy: str) -> dict[str, float]:
    configured = metadata.get("priority_thresholds", {}).get(policy)
    return {
        **DEFAULT_M1_PRIORITY_THRESHOLDS[policy],
        **({name: float(value) for name, value in configured.items()} if isinstance(configured, dict) else {}),
    }


def _policy_level(score: float, thresholds: dict[str, Any]) -> str:
    high = float(thresholds.get("high", 48.0))
    urgent = float(thresholds.get("urgent", 70.0))
    medium = float(thresholds.get("medium", max(20.0, high * 0.6)))
    if score >= urgent:
        return "urgent"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def _matrix(
    rows: list[dict[str, float]],
    columns: list[str],
) -> tuple[pd.DataFrame, list[float]]:
    imputation = _imputation_values()
    records: list[dict[str, float]] = []
    coverages: list[float] = []
    for row in rows:
        present = sum(1 for column in columns if _optional_number(row.get(column)) is not None)
        records.append(
            {
                column: _finite_number(row.get(column), imputation.get(column, 0.0))
                for column in columns
            }
        )
        coverages.append(present / max(1, len(columns)))
    return pd.DataFrame(records, columns=columns, dtype="float64"), coverages


def _numeric_features(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for name, item in value.items():
        numeric = _optional_number(item)
        if numeric is not None:
            result[str(name)] = numeric
    return result


def _is_m1_scope(row: dict[str, Any]) -> bool:
    manufacturer = str(row.get("manufacturer_id") or row.get("manufacturer") or "").strip().lower()
    return manufacturer == "manufacturer 1"


def _leadtime_class_index(value: Any) -> int | None:
    if value in LEADTIME_LABELS:
        return LEADTIME_LABELS.index(value)
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if 0 <= index < len(LEADTIME_LABELS) else None


def _positive_class_index(classes: list[Any], width: int) -> int:
    for candidate in (1, True, "1", "pre_fault"):
        if candidate in classes:
            return classes.index(candidate)
    return max(0, width - 1)


def _resolve_model_root(value: str | Path | None) -> Path:
    if value is None:
        return ROOT / "models"
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    nested = candidate / "models"
    return nested if nested.exists() else candidate


def _bundle_version(
    model_root: Path,
    metadata: dict[str, dict[str, Any]],
    *,
    deployment_version: str | None,
) -> str:
    version_parts = [
        INFERENCE_CONTRACT_VERSION,
        str(metadata["risk"].get("model_version", "risk-unknown")),
        str(metadata["anomaly"].get("model_version", "anomaly-unknown")),
        str(metadata["leadtime"].get("model_version", "leadtime-unknown")),
        str(metadata["priority"].get("engine_version", "priority-unknown")),
        str(metadata["m1_runtime"].get("package_id", "m1-unknown")),
    ]
    digest = hashlib.sha256("|".join(version_parts).encode("utf-8")).hexdigest()[:12]
    return f"{deployment_version or 'local-model-bundle'}:{digest}"


@lru_cache(maxsize=32)
def _load_model(path: str):
    model_path = Path(path)
    if not model_path.exists():
        raise PriorityInferenceError(f"model artifact is missing: {model_path}")
    return joblib.load(model_path)


@lru_cache(maxsize=32)
def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _imputation_values() -> dict[str, float]:
    path = ROOT / "data" / "processed" / "imputation_values.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    return {
        str(row.column_name): _finite_number(row.imputation_value, 0.0)
        for row in frame.itertuples(index=False)
    }


def _compat_model(model: Any) -> Any:
    estimators: list[Any] = []
    if hasattr(model, "steps"):
        estimators.extend(step for _, step in model.steps)
    estimators.append(model)
    for estimator in estimators:
        if estimator.__class__.__name__ == "LogisticRegression" and not hasattr(estimator, "multi_class"):
            estimator.multi_class = "auto"
    return model


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _number(value: Any, fallback: float) -> float:
    converted = _optional_number(value)
    return fallback if converted is None else converted


def _optional_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _finite_number(value: Any, fallback: float) -> float:
    converted = _optional_number(value)
    return fallback if converted is None else converted
