from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import precision_recall_fscore_support


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
PRIORITY_DIR = DATA_DIR / "ml_priority"
RISK_DIR = DATA_DIR / "ml_risk"
REPORT_DIR = ROOT / "report" / "experiment_comparison"

PRIORITY_PATH = PRIORITY_DIR / "priority_engine_scores_tuned.csv"
RISK_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"

OUTPUT_METRICS_PATH = REPORT_DIR / "priority_urgency_aux_experiment_metrics.csv"
OUTPUT_DISTRIBUTION_PATH = REPORT_DIR / "priority_urgency_aux_experiment_distribution.csv"
OUTPUT_DETAIL_PATH = REPORT_DIR / "priority_urgency_aux_experiment_detail.json"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
RISK_SPLIT_COLUMN = "split_event_regime_based"
LEVEL_THRESHOLDS = {"urgent": 70.0, "high": 52.0, "medium": 34.0}
VARIANTS = [
    {"variant": "official_priority_v2", "weight": 0.0, "gate": "none"},
    {"variant": "urgency_prob_0_24h_x3", "weight": 3.0, "gate": "none"},
    {"variant": "urgency_prob_0_24h_x5", "weight": 5.0, "gate": "none"},
    {"variant": "urgency_prob_0_24h_x8", "weight": 8.0, "gate": "none"},
    {"variant": "risk_gated_urgency_x5", "weight": 5.0, "gate": "risk_high_or_critical"},
    {"variant": "risk_gated_urgency_x8", "weight": 8.0, "gate": "risk_high_or_critical"},
    {"variant": "short_bucket_bonus", "weight": 0.0, "gate": "short_bucket_bonus"},
]


def priority_level(score: float) -> str:
    if score >= LEVEL_THRESHOLDS["urgent"]:
        return "urgent"
    if score >= LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def candidate_boost(df: pd.DataFrame, variant: dict) -> pd.Series:
    urgency_prob = pd.to_numeric(df["leadtime_prob_0-24h"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    gate = variant["gate"]
    if gate == "none":
        return urgency_prob * float(variant["weight"])
    if gate == "risk_high_or_critical":
        risk_gate = df["risk_level_calibrated"].isin(["high", "critical"]).astype(float)
        return urgency_prob * float(variant["weight"]) * risk_gate
    if gate == "short_bucket_bonus":
        short_bucket = df["predicted_lead_time_bucket"].eq("0-24h")
        mid_bucket = df["predicted_lead_time_bucket"].eq("1-3d")
        return short_bucket.astype(float) * 5.0 + mid_bucket.astype(float) * 2.0
    raise ValueError(f"Unknown urgency gate: {gate}")


def top_n_coverage(df: pd.DataFrame, score_column: str, n: int) -> float:
    if len(df) == 0:
        return float("nan")
    positives = int(df["target"].sum())
    if positives == 0:
        return float("nan")
    top = df.sort_values(score_column, ascending=False).head(n)
    return float(top["target"].sum() / positives)


def evaluate(df: pd.DataFrame, variant: str, score_column: str, level_column: str) -> dict:
    holdout = df[df[RISK_SPLIT_COLUMN].eq("holdout")].copy()
    y_true = holdout["target"].astype(int)
    y_pred = holdout[level_column].isin(["urgent", "high"]).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    return {
        "variant": variant,
        "rows": int(len(holdout)),
        "positives": int(y_true.sum()),
        "precision_high_or_urgent": float(precision),
        "recall_high_or_urgent": float(recall),
        "f1_high_or_urgent": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "predicted_positive_rate": float(y_pred.mean()) if len(y_pred) else float("nan"),
        "top10_prefault_coverage": top_n_coverage(holdout, score_column, 10),
        "top20_prefault_coverage": top_n_coverage(holdout, score_column, 20),
        "top50_prefault_coverage": top_n_coverage(holdout, score_column, 50),
        "mean_priority_score": float(holdout[score_column].mean()),
        "p95_priority_score": float(holdout[score_column].quantile(0.95)),
    }


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    priority_df = pd.read_csv(PRIORITY_PATH)
    risk_df = pd.read_csv(RISK_PATH)
    risk_cols = KEY_COLUMNS + ["label", RISK_SPLIT_COLUMN, "fault_event_id"]
    eval_df = priority_df.merge(
        risk_df[risk_cols],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    eval_df["target"] = eval_df["label"].eq("pre_fault").astype(int)

    metrics: list[dict] = []
    distribution_rows: list[dict] = []
    for variant in VARIANTS:
        name = variant["variant"]
        score_col = f"{name}__priority_score"
        level_col = f"{name}__priority_level"
        if name == "official_priority_v2":
            eval_df[score_col] = pd.to_numeric(eval_df["priority_score"], errors="coerce").fillna(0.0)
            eval_df[level_col] = eval_df["priority_level"]
            eval_df[f"{name}__urgency_boost"] = 0.0
        else:
            boost = candidate_boost(eval_df, variant)
            eval_df[f"{name}__urgency_boost"] = boost.round(4)
            eval_df[score_col] = (pd.to_numeric(eval_df["priority_score"], errors="coerce").fillna(0.0) + boost).clip(0.0, 100.0).round(4)
            eval_df[level_col] = eval_df[score_col].map(priority_level)

        metrics.append(evaluate(eval_df, name, score_col, level_col))
        for split_name, split_df in eval_df.groupby(RISK_SPLIT_COLUMN, dropna=False):
            counts = split_df[level_col].value_counts().to_dict()
            distribution_rows.append(
                {
                    "variant": name,
                    "split": split_name,
                    "rows": int(len(split_df)),
                    "urgent": int(counts.get("urgent", 0)),
                    "high": int(counts.get("high", 0)),
                    "medium": int(counts.get("medium", 0)),
                    "low": int(counts.get("low", 0)),
                }
            )

    metrics_df = pd.DataFrame(metrics).sort_values(["f1_high_or_urgent", "top20_prefault_coverage"], ascending=[False, False])
    distribution_df = pd.DataFrame(distribution_rows).sort_values(["variant", "split"])

    detail = {
        "experiment": "priority urgency auxiliary score using promoted leadtime probabilities",
        "priority_path": str(PRIORITY_PATH),
        "risk_path": str(RISK_PATH),
        "variants": VARIANTS,
        "level_thresholds": LEVEL_THRESHOLDS,
        "notes": [
            "This does not overwrite priority_engine_scores_tuned.csv.",
            "The experiment checks whether 0-24h leadtime probability helps ranking urgent dispatch candidates.",
            "The target remains pre_fault because actual dispatch outcome labels are not available.",
        ],
    }

    metrics_df.to_csv(OUTPUT_METRICS_PATH, index=False, encoding="utf-8-sig")
    distribution_df.to_csv(OUTPUT_DISTRIBUTION_PATH, index=False, encoding="utf-8-sig")
    OUTPUT_DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")

    print(OUTPUT_METRICS_PATH)
    print(OUTPUT_DISTRIBUTION_PATH)
    print(OUTPUT_DETAIL_PATH)
    print()
    print(metrics_df.to_string(index=False))
    print()
    holdout_dist = distribution_df[distribution_df["split"].eq("holdout")]
    print(holdout_dist.to_string(index=False))


if __name__ == "__main__":
    main()
