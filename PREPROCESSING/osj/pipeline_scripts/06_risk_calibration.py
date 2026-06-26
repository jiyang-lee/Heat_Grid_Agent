from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score


ROOT = Path(__file__).resolve().parents[3]
RISK_DIR = ROOT / "data" / "processed" / "ml_risk"
MODEL_DIR = RISK_DIR / "models"

RISK_SCORES_PATH = RISK_DIR / "lgbm_risk_scores.csv"
RISK_METRICS_PATH = RISK_DIR / "lgbm_risk_metrics.csv"
RISK_METADATA_PATH = MODEL_DIR / "risk_model_metadata.json"

CALIBRATED_SCORES_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"
CALIBRATED_METRICS_PATH = RISK_DIR / "lgbm_risk_metrics_calibrated.csv"
GROUP_OVERRIDE_PATH = RISK_DIR / "lgbm_group_threshold_overrides.csv"
CALIBRATION_METADATA_PATH = MODEL_DIR / "risk_model_group_calibration.json"

PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
BASE_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
GROUP_OVERRIDES = {
    ("manufacturer 2", "SH"): {"high": 0.78},
}


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = (y_true == 0)
    negative_count = int(negatives.sum())
    if negative_count == 0:
        return 0.0
    fp = int(((y_pred == 1) & negatives).sum())
    return fp / negative_count


def applied_thresholds(row: pd.Series) -> tuple[float, float, float]:
    medium = BASE_THRESHOLDS["medium"]
    high = BASE_THRESHOLDS["high"]
    critical = BASE_THRESHOLDS["critical"]
    override = GROUP_OVERRIDES.get((row["manufacturer"], row["configuration_type"]))
    if override:
        high = override.get("high", high)
        medium = min(medium, high)
        critical = max(critical, high)
    return medium, high, critical


def risk_level_from_thresholds(score: float, medium: float, high: float, critical: float) -> str:
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def score_group(frame: pd.DataFrame) -> dict:
    y_true = (frame["label"] == "pre_fault").astype(int)
    y_pred = frame["risk_level_calibrated"].isin(["high", "critical"]).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    return {
        "row_count": int(len(frame)),
        "normal_count": int((y_true == 0).sum()),
        "pre_fault_count": int((y_true == 1).sum()),
        "roc_auc": float(roc_auc_score(y_true, frame["risk_probability"])),
        "average_precision": float(average_precision_score(y_true, frame["risk_probability"])),
        "precision_high_or_critical": float(precision),
        "recall_high_or_critical": float(recall),
        "f1_high_or_critical": float(f1),
        "false_positive_rate_high_or_critical": float(false_positive_rate(y_true, y_pred)),
    }


def main() -> None:
    scores_df = pd.read_csv(RISK_SCORES_PATH)
    _ = pd.read_csv(RISK_METRICS_PATH)
    base_metadata = json.loads(RISK_METADATA_PATH.read_text(encoding="utf-8"))

    thresholds = scores_df.apply(applied_thresholds, axis=1, result_type="expand")
    thresholds.columns = [
        "risk_threshold_medium_applied",
        "risk_threshold_high_applied",
        "risk_threshold_critical_applied",
    ]
    calibrated_df = pd.concat([scores_df.copy(), thresholds], axis=1)
    calibrated_df["risk_level_calibrated"] = calibrated_df.apply(
        lambda row: risk_level_from_thresholds(
            row["risk_probability"],
            row["risk_threshold_medium_applied"],
            row["risk_threshold_high_applied"],
            row["risk_threshold_critical_applied"],
        ),
        axis=1,
    )
    calibrated_df["group_threshold_override_applied"] = calibrated_df.apply(
        lambda row: int((row["manufacturer"], row["configuration_type"]) in GROUP_OVERRIDES),
        axis=1,
    )

    metric_rows: list[dict] = []
    for split_value, frame in calibrated_df.groupby(PRIMARY_SPLIT_COLUMN):
        metrics = score_group(frame)
        metric_rows.append(
            {
                "group_name": PRIMARY_SPLIT_COLUMN,
                "group_value": split_value,
                **metrics,
            }
        )

    group_mask = (
        calibrated_df["manufacturer"].eq("manufacturer 2")
        & calibrated_df["configuration_type"].eq("SH")
    )
    for split_value, frame in calibrated_df.loc[group_mask].groupby(PRIMARY_SPLIT_COLUMN):
        metrics = score_group(frame)
        metric_rows.append(
            {
                "group_name": "manufacturer_2_sh",
                "group_value": split_value,
                **metrics,
            }
        )

    metrics_df = pd.DataFrame(metric_rows)

    override_rows = []
    for (manufacturer, configuration_type), override in GROUP_OVERRIDES.items():
        override_rows.append(
            {
                "manufacturer": manufacturer,
                "configuration_type": configuration_type,
                "medium_threshold": BASE_THRESHOLDS["medium"],
                "high_threshold": override.get("high", BASE_THRESHOLDS["high"]),
                "critical_threshold": max(BASE_THRESHOLDS["critical"], override.get("high", BASE_THRESHOLDS["high"])),
                "basis": "validation-selected group override",
            }
        )
    override_df = pd.DataFrame(override_rows)

    calibrated_df.to_csv(CALIBRATED_SCORES_PATH, index=False, encoding="utf-8-sig")
    metrics_df.to_csv(CALIBRATED_METRICS_PATH, index=False, encoding="utf-8-sig")
    override_df.to_csv(GROUP_OVERRIDE_PATH, index=False, encoding="utf-8-sig")

    calibration_metadata = {
        "base_model_version": base_metadata.get("model_version"),
        "base_thresholds": BASE_THRESHOLDS,
        "primary_split_column": PRIMARY_SPLIT_COLUMN,
        "group_overrides": [
            {
                "manufacturer": manufacturer,
                "configuration_type": configuration_type,
                "applied_thresholds": {
                    "medium": BASE_THRESHOLDS["medium"],
                    "high": override.get("high", BASE_THRESHOLDS["high"]),
                    "critical": max(BASE_THRESHOLDS["critical"], override.get("high", BASE_THRESHOLDS["high"])),
                },
                "basis": "validation-selected group override",
            }
            for (manufacturer, configuration_type), override in GROUP_OVERRIDES.items()
        ],
        "output_scores_path": str(CALIBRATED_SCORES_PATH),
        "output_metrics_path": str(CALIBRATED_METRICS_PATH),
        "output_override_path": str(GROUP_OVERRIDE_PATH),
    }
    CALIBRATION_METADATA_PATH.write_text(
        json.dumps(calibration_metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(CALIBRATED_SCORES_PATH)
    print(CALIBRATED_METRICS_PATH)
    print(GROUP_OVERRIDE_PATH)
    print(CALIBRATION_METADATA_PATH)
    print()
    print(metrics_df.to_string(index=False))


if __name__ == "__main__":
    main()
