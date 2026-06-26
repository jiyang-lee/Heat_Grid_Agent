from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from heatgrid_inference.constants import (
    CONFIGURATION_CODE,
    EVENT_CONTEXT_SENTINEL_DAYS,
    KEY_COLUMNS,
    LEADTIME_LABELS,
    MANUFACTURER_CODE,
    TIMEFLOW_SOURCE_COLUMNS,
)


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def coerce_numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "bool":
            result[column] = result[column].astype("int8")
        elif result[column].dtype == "object":
            mapped = result[column].map({"True": 1, "False": 0, "true": 1, "false": 0})
            if mapped.notna().any():
                result[column] = mapped.fillna(result[column])
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


class FeatureContracts:
    def __init__(self, package_root: Path):
        self.package_root = Path(package_root)
        contract_root = self.package_root / "contracts"
        self.imputation = pd.read_csv(contract_root / "imputation_values.csv")
        self.categorical_map = pd.read_csv(contract_root / "categorical_feature_map.csv")
        self.imputation_values = {
            row.column_name: self._parse_imputation_value(row.imputation_value)
            for row in self.imputation.itertuples(index=False)
            if pd.notna(row.imputation_value)
        }

    @staticmethod
    def _parse_imputation_value(value) -> float:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return 1.0
            if lowered == "false":
                return 0.0
            if lowered in {"", "nan", "none"}:
                return 0.0
        return float(value)

    def add_categorical_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        derived_columns: dict[str, pd.Series] = {}
        for row in self.categorical_map.itertuples(index=False):
            source = row.source_column
            category = str(row.category_value)
            derived = row.derived_feature_column
            if source in result.columns:
                values = result[source].fillna("missing").astype(str)
            else:
                values = pd.Series("missing", index=result.index)
            derived_columns[derived] = values.eq(category).astype("int8")
        if derived_columns:
            result = result.drop(columns=[column for column in derived_columns if column in result.columns])
            result = pd.concat([result, pd.DataFrame(derived_columns, index=result.index)], axis=1)
        return result

    def model_matrix(self, frame: pd.DataFrame, feature_columns: list[str], fill_value: float = 0.0) -> pd.DataFrame:
        result = frame.copy()
        for column in feature_columns:
            if column not in result.columns:
                result[column] = self.imputation_values.get(column, fill_value)
        x = coerce_numeric_frame(result[feature_columns])
        fill_map = {column: self.imputation_values.get(column, fill_value) for column in feature_columns}
        return x.fillna(fill_map).fillna(fill_value)


class HeatGridScorer:
    def __init__(self, package_root: str | Path):
        self.package_root = Path(package_root)
        self.contracts = FeatureContracts(self.package_root)

        anomaly_root = self.package_root / "models" / "anomaly"
        risk_root = self.package_root / "models" / "risk"
        leadtime_root = self.package_root / "models" / "leadtime"
        priority_root = self.package_root / "models" / "priority"

        self.scaler = joblib.load(anomaly_root / "standard_scaler.joblib")
        self.isolation_forest = joblib.load(anomaly_root / "isolation_forest.joblib")
        self.risk_model = joblib.load(risk_root / "lightgbm_risk_model.joblib")
        self.leadtime_model = joblib.load(leadtime_root / "lightgbm_leadtime_bucket_model_promoted.joblib")

        self.anomaly_metadata = load_json(anomaly_root / "baseline_model_metadata.json")
        self.risk_metadata = load_json(risk_root / "risk_model_metadata.json")
        self.risk_calibration = load_json(risk_root / "risk_model_group_calibration.json")
        self.leadtime_metadata = load_json(leadtime_root / "leadtime_bucket_model_promoted_metadata.json")
        self.priority_metadata = load_json(priority_root / "priority_engine_tuned_metadata.json")
        self.anomaly_threshold = self._load_anomaly_threshold(anomaly_root / "anomaly_baseline_thresholds.csv")

    def _load_anomaly_threshold(self, path: Path) -> float:
        table = pd.read_csv(path)
        quantile = float(self.anomaly_metadata.get("default_threshold_quantile", 0.99))
        row = table.loc[
            table["model_name"].eq("isolation_forest")
            & np.isclose(table["threshold_quantile"].astype(float), quantile)
        ]
        if row.empty:
            row = table.loc[table["model_name"].eq("isolation_forest")].tail(1)
        return float(row["threshold_value"].iloc[0])

    def _risk_thresholds_for_row(self, row: pd.Series) -> tuple[float, float, float]:
        thresholds = dict(self.risk_calibration["base_thresholds"])
        for override in self.risk_calibration.get("group_overrides", []):
            if (
                row.get("manufacturer") == override.get("manufacturer")
                and row.get("configuration_type") == override.get("configuration_type")
            ):
                thresholds.update(override.get("applied_thresholds", {}))
        return float(thresholds["medium"]), float(thresholds["high"]), float(thresholds["critical"])

    @staticmethod
    def _risk_level(probability: float, medium: float, high: float, critical: float) -> str:
        if probability >= critical:
            return "critical"
        if probability >= high:
            return "high"
        if probability >= medium:
            return "medium"
        return "low"

    def score_anomaly(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = self.contracts.add_categorical_features(frame)
        feature_columns = self.anomaly_metadata["selected_feature_columns"]
        x = self.contracts.model_matrix(result, feature_columns)
        scaled = self.scaler.transform(x.to_numpy())
        anomaly_score = -self.isolation_forest.score_samples(scaled)

        result["iforest_anomaly_score"] = anomaly_score
        result["anomaly_score"] = anomaly_score
        result["iforest_threshold"] = self.anomaly_threshold
        result["anomaly_threshold"] = self.anomaly_threshold
        result["iforest_anomaly_label"] = (result["iforest_anomaly_score"] >= self.anomaly_threshold).astype(int)
        result["anomaly_label"] = result["iforest_anomaly_label"]
        result["main_abnormal_features"] = self._top_scaled_features(scaled, feature_columns)
        return result

    @staticmethod
    def _top_scaled_features(scaled: np.ndarray, feature_columns: list[str], limit: int = 5) -> list[str]:
        rows: list[str] = []
        abs_scaled = np.abs(scaled)
        for row in abs_scaled:
            if row.size == 0:
                rows.append("")
                continue
            indexes = np.argsort(row)[-limit:][::-1]
            rows.append("|".join(feature_columns[index] for index in indexes if np.isfinite(row[index])))
        return rows

    def score_risk(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        for column in [
            "days_since_last_fault_event",
            "days_since_last_task_event",
            "days_since_last_any_event",
        ]:
            if column not in result.columns:
                result[column] = EVENT_CONTEXT_SENTINEL_DAYS
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(EVENT_CONTEXT_SENTINEL_DAYS)
        if "maintenance_related" not in result.columns:
            result["maintenance_related"] = False
        if "disturbance_count" not in result.columns:
            result["disturbance_count"] = 0

        x = self.contracts.model_matrix(result, self.risk_metadata["model_feature_columns"])
        probability = self.risk_model.predict_proba(x)[:, 1]
        result["risk_probability"] = probability
        result["risk_score"] = probability

        thresholds = result.apply(self._risk_thresholds_for_row, axis=1, result_type="expand")
        thresholds.columns = [
            "risk_threshold_medium_applied",
            "risk_threshold_high_applied",
            "risk_threshold_critical_applied",
        ]
        result = pd.concat([result, thresholds], axis=1)
        result["risk_level_calibrated"] = result.apply(
            lambda row: self._risk_level(
                row["risk_probability"],
                row["risk_threshold_medium_applied"],
                row["risk_threshold_high_applied"],
                row["risk_threshold_critical_applied"],
            ),
            axis=1,
        )
        result["risk_level"] = result["risk_level_calibrated"]
        result["model_explanation_features"] = "|".join(self.risk_metadata.get("global_explanation_features", []))
        return result

    def add_leadtime_support_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result["manufacturer_code"] = result["manufacturer"].map(MANUFACTURER_CODE).fillna(-1).astype("int16")
        result["configuration_code"] = (
            result["configuration_type"].fillna("missing").map(CONFIGURATION_CODE).fillna(-1).astype("int16")
        )
        return self.add_timeflow_features(result)

    def add_timeflow_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        working = result.copy()
        working["window_end"] = pd.to_datetime(working["window_end"], errors="coerce")
        working["_original_index"] = working.index
        if "fault_event_id" in working.columns and working["fault_event_id"].notna().any():
            group_columns = ["fault_event_id"]
        else:
            group_columns = ["manufacturer", "substation_id"]
        working = working.sort_values([*group_columns, "window_end", "window_start"]).copy()

        extra = pd.DataFrame(index=working.index)
        grouped = working.groupby(group_columns, dropna=False)
        for column in [column for column in TIMEFLOW_SOURCE_COLUMNS if column in working.columns]:
            numeric = pd.to_numeric(working[column], errors="coerce")
            lag1 = pd.to_numeric(grouped[column].shift(1), errors="coerce")
            lag2 = pd.to_numeric(grouped[column].shift(2), errors="coerce")
            roll3 = pd.to_numeric(
                grouped[column].rolling(3, min_periods=1).mean().reset_index(level=group_columns, drop=True),
                errors="coerce",
            )
            extra[f"{column}__lag1"] = lag1.fillna(numeric).astype("float64")
            extra[f"{column}__delta1"] = (numeric - lag1).fillna(0.0).astype("float64")
            extra[f"{column}__lag2"] = lag2.fillna(numeric).astype("float64")
            extra[f"{column}__roll3_mean"] = roll3.fillna(numeric).astype("float64")

        extra["_original_index"] = working["_original_index"]
        extra = extra.set_index("_original_index").reindex(result.index)
        return pd.concat([result, extra], axis=1).fillna(0.0)

    def score_leadtime(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = self.add_leadtime_support_features(frame)
        x = self.contracts.model_matrix(result, self.leadtime_metadata["model_feature_columns"])
        probabilities = self.leadtime_model.predict_proba(x)
        predicted_index = probabilities.argmax(axis=1)

        result["predicted_lead_time_bucket"] = [LEADTIME_LABELS[index] for index in predicted_index]
        result["predicted_lead_time_confidence"] = probabilities.max(axis=1)
        result["predicted_lead_time_index"] = predicted_index
        for index, label in enumerate(LEADTIME_LABELS):
            result[f"leadtime_prob_{label}"] = probabilities[:, index]
        return result

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _leadtime_confidence_multiplier(confidence: float) -> float:
        if confidence >= 0.8:
            return 1.0
        if confidence >= 0.6:
            return 0.8
        return 0.6

    def _history_adjustment(self, row: pd.Series) -> tuple[float, str]:
        adjustment = 0.0
        reasons: list[str] = []
        task_days = pd.to_numeric(row.get("days_since_last_task_event"), errors="coerce")
        any_days = pd.to_numeric(row.get("days_since_last_any_event"), errors="coerce")
        fault_days = pd.to_numeric(row.get("days_since_last_fault_event"), errors="coerce")
        risk_level = row.get("risk_level_calibrated")

        if pd.notna(task_days):
            if task_days <= 7:
                adjustment -= 8.0
                reasons.append("recent_task_within_7d")
            elif task_days <= 30:
                adjustment -= 4.0
                reasons.append("recent_task_within_30d")
        if pd.notna(any_days):
            if any_days <= 7:
                adjustment -= 5.0
                reasons.append("recent_any_event_within_7d")
            elif any_days <= 30:
                adjustment -= 2.0
                reasons.append("recent_any_event_within_30d")
        if pd.notna(fault_days) and fault_days >= 365 and risk_level in {"high", "critical"}:
            adjustment += 2.0
            reasons.append("long_time_since_last_fault_and_high_risk")
        return adjustment, "|".join(reasons)

    def score_priority(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        risk_level_points = self.priority_metadata["risk_level_points"]
        leadtime_bucket_points = self.priority_metadata["leadtime_bucket_points"]
        level_rules = self.priority_metadata["priority_level_rules"]

        result["risk_base_score"] = result["risk_level_calibrated"].map(risk_level_points).fillna(0.0)
        result["risk_probability_component_score"] = result["risk_probability"].map(
            lambda value: 0.0 if pd.isna(value) else self._clamp(float(value) * 18.0, 0.0, 18.0)
        )
        result["leadtime_bucket_base_score"] = (
            result["predicted_lead_time_bucket"].map(leadtime_bucket_points).fillna(0.0)
        )
        result["leadtime_confidence_multiplier"] = (
            result["predicted_lead_time_confidence"].fillna(0.0).map(self._leadtime_confidence_multiplier)
        )
        result["leadtime_component_score"] = (
            result["leadtime_bucket_base_score"] * result["leadtime_confidence_multiplier"]
        )
        result["anomaly_component_score"] = result["anomaly_score"].map(
            lambda value: 0.0 if pd.isna(value) else self._clamp(float(value) * 6.0, 0.0, 6.0)
        )

        history = result.apply(self._history_adjustment, axis=1)
        result["history_adjustment_score"] = [score for score, _ in history]
        result["history_adjustment_reason"] = [reason for _, reason in history]
        result["priority_score_raw"] = (
            result["risk_base_score"]
            + result["risk_probability_component_score"]
            + result["leadtime_component_score"]
            + result["anomaly_component_score"]
            + result["history_adjustment_score"]
        )
        result["priority_score"] = result["priority_score_raw"].map(
            lambda value: round(self._clamp(float(value), 0.0, 100.0), 4)
        )
        result["priority_level"] = result["priority_score"].map(
            lambda score: "urgent"
            if score >= level_rules["urgent"]
            else "high"
            if score >= level_rules["high"]
            else "medium"
            if score >= level_rules["medium"]
            else "low"
        )
        result["priority_reason"] = result.apply(self._build_priority_reason, axis=1)
        result["engine_version"] = self.priority_metadata["engine_version"]
        return result

    @staticmethod
    def _build_priority_reason(row: pd.Series) -> str:
        parts: list[str] = []
        if row.get("risk_level_calibrated") in {"high", "critical"}:
            parts.append(f"risk={row['risk_level_calibrated']}")
        if row.get("predicted_lead_time_bucket") in {"0-24h", "1-3d"}:
            parts.append(f"leadtime={row['predicted_lead_time_bucket']}")
        if row.get("leadtime_confidence_multiplier", 1.0) < 1.0:
            parts.append("leadtime_confidence_damped")
        if row.get("history_adjustment_score", 0.0) != 0:
            parts.append("history_adjusted")
        if row.get("anomaly_component_score", 0.0) >= 4:
            parts.append("strong_anomaly")
        return "|".join(parts)

    def score_window_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        anomaly = self.score_anomaly(frame)
        risk = self.score_risk(anomaly)
        leadtime = self.score_leadtime(risk)
        priority = self.score_priority(leadtime)
        return self.output_columns(priority)

    @staticmethod
    def output_columns(frame: pd.DataFrame) -> pd.DataFrame:
        columns = [
            *KEY_COLUMNS,
            "source_file",
            "configuration_type",
            "anomaly_score",
            "anomaly_threshold",
            "anomaly_label",
            "main_abnormal_features",
            "risk_score",
            "risk_probability",
            "risk_level_calibrated",
            "risk_threshold_medium_applied",
            "risk_threshold_high_applied",
            "risk_threshold_critical_applied",
            "model_explanation_features",
            "predicted_lead_time_bucket",
            "predicted_lead_time_confidence",
            "leadtime_prob_0-24h",
            "leadtime_prob_1-3d",
            "leadtime_prob_3-7d",
            "days_since_last_fault_event",
            "days_since_last_task_event",
            "days_since_last_any_event",
            "risk_base_score",
            "risk_probability_component_score",
            "leadtime_component_score",
            "anomaly_component_score",
            "history_adjustment_score",
            "history_adjustment_reason",
            "priority_score",
            "priority_level",
            "priority_reason",
            "engine_version",
        ]
        existing = [column for column in columns if column in frame.columns]
        return frame[existing].copy()
