from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
PRIORITY_DIR = DATA_DIR / "ml_priority"
RISK_DIR = DATA_DIR / "ml_risk"
REPORT_DIR = ROOT / "report" / "experiment_comparison"

PRIORITY_PATH = PRIORITY_DIR / "priority_engine_scores_tuned.csv"
RISK_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"

OUTPUT_SWEEP_PATH = REPORT_DIR / "priority_threshold_sweep_metrics.csv"
OUTPUT_SUMMARY_PATH = REPORT_DIR / "priority_threshold_sweep_summary.csv"
OUTPUT_DETAIL_PATH = REPORT_DIR / "priority_threshold_sweep_detail.json"
OUTPUT_MD_PATH = REPORT_DIR / "07_priority_threshold_sweep_summary.md"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
SPLIT_COLUMN = "split_event_regime_based"
CURRENT_HIGH_THRESHOLD = 52.0
THRESHOLDS = np.round(np.arange(20.0, 72.5, 0.5), 2)
FPR_LIMITS = [0.0, 0.005, 0.01, 0.02, 0.05]


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def evaluate_threshold(df: pd.DataFrame, variant: str, score_column: str, threshold: float) -> dict:
    y_true = df["target"].astype(int)
    y_pred = (df[score_column] >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    return {
        "variant": variant,
        "threshold": float(threshold),
        "rows": int(len(df)),
        "positives": int(y_true.sum()),
        "predicted_positive": int(y_pred.sum()),
        "predicted_positive_rate": float(y_pred.mean()) if len(y_pred) else float("nan"),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "false_positive_count": int(((y_pred == 1) & y_true.eq(0)).sum()),
        "true_positive_count": int(((y_pred == 1) & y_true.eq(1)).sum()),
    }


def build_eval_df() -> pd.DataFrame:
    priority_df = pd.read_csv(PRIORITY_PATH)
    risk_df = pd.read_csv(RISK_PATH)
    risk_columns = KEY_COLUMNS + ["label", SPLIT_COLUMN, "fault_event_id"]
    df = priority_df.merge(
        risk_df[risk_columns],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    df = df[df[SPLIT_COLUMN].eq("holdout")].copy()
    df["target"] = df["label"].eq("pre_fault").astype(int)
    df["official_priority_score"] = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0.0)

    urgency_prob = pd.to_numeric(df["leadtime_prob_0-24h"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    risk_gate = df["risk_level_calibrated"].isin(["high", "critical"]).astype(float)
    df["risk_gated_urgency_x8_score"] = (df["official_priority_score"] + urgency_prob * 8.0 * risk_gate).clip(0.0, 100.0)
    df["ungated_urgency_x8_score"] = (df["official_priority_score"] + urgency_prob * 8.0).clip(0.0, 100.0)
    return df


def summarize_variant(sweep_df: pd.DataFrame, variant: str) -> list[dict]:
    rows: list[dict] = []
    variant_df = sweep_df[sweep_df["variant"].eq(variant)].copy()
    for fpr_limit in FPR_LIMITS:
        allowed = variant_df[variant_df["false_positive_rate"] <= fpr_limit].copy()
        if allowed.empty:
            rows.append(
                {
                    "variant": variant,
                    "fpr_limit": fpr_limit,
                    "min_threshold": float("nan"),
                    "best_threshold_by_f1": float("nan"),
                    "best_f1": float("nan"),
                    "recall_at_best_f1": float("nan"),
                    "precision_at_best_f1": float("nan"),
                    "false_positive_rate_at_best_f1": float("nan"),
                    "predicted_positive_at_best_f1": float("nan"),
                }
            )
            continue

        min_threshold = float(allowed["threshold"].min())
        best = allowed.sort_values(["f1", "recall", "threshold"], ascending=[False, False, False]).iloc[0]
        rows.append(
            {
                "variant": variant,
                "fpr_limit": fpr_limit,
                "min_threshold": min_threshold,
                "best_threshold_by_f1": float(best["threshold"]),
                "best_f1": float(best["f1"]),
                "recall_at_best_f1": float(best["recall"]),
                "precision_at_best_f1": float(best["precision"]),
                "false_positive_rate_at_best_f1": float(best["false_positive_rate"]),
                "predicted_positive_at_best_f1": int(best["predicted_positive"]),
            }
        )
    return rows


def make_markdown(summary_df: pd.DataFrame, sweep_df: pd.DataFrame) -> str:
    lines = [
        "# 07 Priority Threshold Sweep Summary",
        "",
        "## 목적",
        "",
        "Priority Engine에서 high/urgent 판정 threshold를 현재 52점에서 낮췄을 때, holdout 오탐률(FPR)이 언제 증가하는지 확인했다.",
        "",
        "## 핵심 결과",
        "",
    ]
    for variant in summary_df["variant"].unique():
        zero = summary_df[(summary_df["variant"].eq(variant)) & (summary_df["fpr_limit"].eq(0.0))].iloc[0]
        one = summary_df[(summary_df["variant"].eq(variant)) & (summary_df["fpr_limit"].eq(0.01))].iloc[0]
        lines.extend(
            [
                f"### {variant}",
                "",
                f"- FPR 0.0000 유지 가능한 최저 threshold: `{zero['min_threshold']:.1f}`",
                f"- FPR 0.0000 조건에서 F1 최고 threshold: `{zero['best_threshold_by_f1']:.1f}`",
                f"- 해당 F1/Recall/Precision: `{zero['best_f1']:.4f}` / `{zero['recall_at_best_f1']:.4f}` / `{zero['precision_at_best_f1']:.4f}`",
                f"- FPR 0.01 이하 허용 시 최저 threshold: `{one['min_threshold']:.1f}`",
                "",
            ]
        )

    current = sweep_df[sweep_df["threshold"].eq(CURRENT_HIGH_THRESHOLD)].copy()
    if not current.empty:
        lines.extend(["## 현재 threshold 52 기준", ""])
        for _, row in current.iterrows():
            lines.append(
                f"- `{row['variant']}`: F1 `{row['f1']:.4f}`, Recall `{row['recall']:.4f}`, "
                f"Precision `{row['precision']:.4f}`, FPR `{row['false_positive_rate']:.4f}`, "
                f"TP `{int(row['true_positive_count'])}`, FP `{int(row['false_positive_count'])}`"
            )
        lines.append("")

    lines.extend(
        [
            "## 해석",
            "",
            "- FPR 0.0000을 엄격히 유지하려면 threshold를 무작정 낮출 수 없다.",
            "- threshold를 낮추면 recall은 증가하지만, 특정 지점부터 정상/비위험 구간도 high/urgent로 올라와 FPR이 증가한다.",
            "- 실무 적용 후보는 FPR 0.0000 유지 threshold와 FPR 0.01 이하 threshold를 나눠서 검토하는 것이 적절하다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    eval_df = build_eval_df()
    variants = {
        "official_priority_v2": "official_priority_score",
        "risk_gated_urgency_x8": "risk_gated_urgency_x8_score",
        "ungated_urgency_x8": "ungated_urgency_x8_score",
    }

    sweep_rows: list[dict] = []
    for variant, score_column in variants.items():
        for threshold in THRESHOLDS:
            sweep_rows.append(evaluate_threshold(eval_df, variant, score_column, float(threshold)))

    sweep_df = pd.DataFrame(sweep_rows)
    summary_rows: list[dict] = []
    for variant in variants:
        summary_rows.extend(summarize_variant(sweep_df, variant))
    summary_df = pd.DataFrame(summary_rows)

    detail = {
        "experiment": "priority high/urgent threshold sweep",
        "priority_path": str(PRIORITY_PATH),
        "risk_path": str(RISK_PATH),
        "split": "holdout",
        "current_high_threshold": CURRENT_HIGH_THRESHOLD,
        "threshold_min": float(THRESHOLDS.min()),
        "threshold_max": float(THRESHOLDS.max()),
        "threshold_step": 0.5,
        "variants": variants,
        "fpr_limits": FPR_LIMITS,
        "notes": [
            "Positive prediction means priority score >= threshold, equivalent to high/urgent dispatch candidate.",
            "Target is pre_fault because actual dispatch outcome labels are unavailable.",
            "risk_gated_urgency_x8 adds 8 * leadtime_prob_0-24h only when calibrated risk level is high or critical.",
        ],
    }

    sweep_df.to_csv(OUTPUT_SWEEP_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(OUTPUT_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    OUTPUT_DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD_PATH.write_text(make_markdown(summary_df, sweep_df), encoding="utf-8-sig")

    print(OUTPUT_SWEEP_PATH)
    print(OUTPUT_SUMMARY_PATH)
    print(OUTPUT_DETAIL_PATH)
    print(OUTPUT_MD_PATH)
    print()
    print(summary_df.to_string(index=False))
    print()
    print(sweep_df[sweep_df["threshold"].isin([52.0, 50.0, 48.0, 46.0, 44.0, 42.0, 40.0])].to_string(index=False))


if __name__ == "__main__":
    main()
