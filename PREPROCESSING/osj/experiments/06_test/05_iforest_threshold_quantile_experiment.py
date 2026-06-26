from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
BASELINE_DIR = DATA_DIR / "ml_baseline"
PRIORITY_DIR = DATA_DIR / "ml_priority"
REPORT_DIR = ROOT / "report" / "experiment_comparison"

ANOMALY_SCORES_PATH = BASELINE_DIR / "anomaly_baseline_scores.csv"
PRIORITY_V2_THRESHOLD48_PATH = PRIORITY_DIR / "priority_engine_scores_v2_threshold48.csv"

OUTPUT_METRICS_PATH = REPORT_DIR / "iforest_threshold_quantile_sweep_metrics.csv"
OUTPUT_HOLDOUT_PATH = REPORT_DIR / "iforest_threshold_quantile_holdout_detail.csv"
OUTPUT_PRIORITY_IMPACT_PATH = REPORT_DIR / "iforest_threshold_quantile_priority_impact.csv"
OUTPUT_DETAIL_PATH = REPORT_DIR / "iforest_threshold_quantile_detail.json"
OUTPUT_MD_PATH = REPORT_DIR / "05_iforest_threshold_quantile_summary.md"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
SCORE_COLUMN = "iforest_anomaly_score"
QUANTILES = [0.85, 0.90, 0.92, 0.94, 0.95, 0.96, 0.975, 0.98, 0.99, 0.995]
SPLIT_COLUMNS = ["split_time_based", "split_substation_based"]
DEFAULT_QUANTILE = 0.99


def safe_roc_auc(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def safe_ap(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def evaluate(df: pd.DataFrame, split_column: str, split: str, quantile: float, threshold: float) -> dict:
    part = df[df[split_column].eq(split)].copy()
    y_true = part["label"].eq("pre_fault").astype(int)
    y_score = part[SCORE_COLUMN].astype(float)
    y_pred = (y_score >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "evaluation_split_column": split_column,
        "split": split,
        "threshold_quantile": quantile,
        "threshold_value": threshold,
        "row_count": int(len(part)),
        "normal_count": int(part["label"].eq("normal").sum()),
        "pre_fault_count": int(part["label"].eq("pre_fault").sum()),
        "predicted_anomaly_count": int(y_pred.sum()),
        "predicted_anomaly_rate": float(y_pred.mean()) if len(y_pred) else float("nan"),
        "roc_auc": safe_roc_auc(y_true, y_score),
        "average_precision": safe_ap(y_true, y_score),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "true_positive_count": int(((y_pred == 1) & y_true.eq(1)).sum()),
        "false_positive_count": int(((y_pred == 1) & y_true.eq(0)).sum()),
        "false_negative_count": int(((y_pred == 0) & y_true.eq(1)).sum()),
        "true_negative_count": int(((y_pred == 0) & y_true.eq(0)).sum()),
    }


def make_holdout_detail(df: pd.DataFrame, split_column: str, quantile: float, threshold: float) -> pd.DataFrame:
    part = df[df[split_column].eq("holdout")].copy()
    part["threshold_quantile"] = quantile
    part["threshold_value"] = threshold
    part["candidate_anomaly_label"] = (part[SCORE_COLUMN].astype(float) >= threshold).astype(int)
    part["target"] = part["label"].eq("pre_fault").astype(int)
    return part[
        KEY_COLUMNS
        + [
            "configuration_type",
            "label",
            "fault_event_id",
            SCORE_COLUMN,
            "threshold_quantile",
            "threshold_value",
            "candidate_anomaly_label",
            "target",
        ]
    ].copy()


def priority_impact(anomaly_df: pd.DataFrame, thresholds: dict[float, float]) -> pd.DataFrame:
    if not PRIORITY_V2_THRESHOLD48_PATH.exists():
        return pd.DataFrame()

    priority_df = pd.read_csv(PRIORITY_V2_THRESHOLD48_PATH)
    merged = priority_df.merge(
        anomaly_df[KEY_COLUMNS + ["label", "split_time_based", SCORE_COLUMN]],
        on=KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
    )
    holdout = merged[merged["split_time_based"].eq("holdout")].copy()
    if holdout.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    current_high = holdout["priority_level"].isin(["high", "urgent"]).astype(int)
    for quantile, threshold in thresholds.items():
        anomaly_label = (holdout[SCORE_COLUMN].astype(float) >= threshold).astype(int)
        rows.append(
            {
                "threshold_quantile": quantile,
                "threshold_value": threshold,
                "holdout_rows_matched_to_priority": int(len(holdout)),
                "candidate_anomaly_count": int(anomaly_label.sum()),
                "candidate_anomaly_rate": float(anomaly_label.mean()),
                "current_priority_high_or_urgent_count": int(current_high.sum()),
                "priority_score_delta_if_only_quantile_changes": 0.0,
                "priority_level_delta_if_only_quantile_changes": 0,
                "note": "priority_engine_v2_threshold48 uses continuous anomaly_score, not anomaly_label; quantile-only change does not alter priority_score.",
            }
        )
    return pd.DataFrame(rows)


def make_markdown(metrics_df: pd.DataFrame, priority_df: pd.DataFrame) -> str:
    holdout = metrics_df[
        metrics_df["evaluation_split_column"].eq("split_time_based") & metrics_df["split"].eq("holdout")
    ].sort_values("threshold_quantile")
    default = holdout[holdout["threshold_quantile"].eq(DEFAULT_QUANTILE)]
    best_f1 = holdout.sort_values(["f1", "false_positive_rate"], ascending=[False, True]).iloc[0]
    zero_fp = holdout[holdout["false_positive_count"].eq(0)]

    lines = [
        "# 05 Isolation Forest Threshold Quantile Experiment",
        "",
        "## 목적",
        "",
        "Isolation Forest의 `threshold_quantile`을 조절했을 때 이상치 라벨, pre_fault 포착률, normal 오탐률이 어떻게 바뀌는지 확인했다.",
        "",
        "## 핵심 결과",
        "",
    ]
    if not default.empty:
        row = default.iloc[0]
        lines.extend(
            [
                "### 현재 공식 기준",
                "",
                f"- 공식 quantile: `{DEFAULT_QUANTILE}`",
                f"- threshold: `{row['threshold_value']:.6f}`",
                f"- holdout F1/Recall/Precision: `{row['f1']:.4f}` / `{row['recall']:.4f}` / `{row['precision']:.4f}`",
                f"- holdout FPR: `{row['false_positive_rate']:.4f}`",
                f"- TP/FP/FN/TN: `{int(row['true_positive_count'])}` / `{int(row['false_positive_count'])}` / `{int(row['false_negative_count'])}` / `{int(row['true_negative_count'])}`",
                "",
            ]
        )
    lines.extend(
        [
            "### F1 기준 최고 후보",
            "",
            f"- quantile: `{best_f1['threshold_quantile']}`",
            f"- threshold: `{best_f1['threshold_value']:.6f}`",
            f"- holdout F1/Recall/Precision: `{best_f1['f1']:.4f}` / `{best_f1['recall']:.4f}` / `{best_f1['precision']:.4f}`",
            f"- holdout FPR: `{best_f1['false_positive_rate']:.4f}`",
            f"- TP/FP/FN/TN: `{int(best_f1['true_positive_count'])}` / `{int(best_f1['false_positive_count'])}` / `{int(best_f1['false_negative_count'])}` / `{int(best_f1['true_negative_count'])}`",
            "",
        ]
    )
    if not zero_fp.empty:
        lowest_zero_fp = zero_fp.sort_values("threshold_quantile").iloc[0]
        lines.extend(
            [
                "### holdout FP 0 유지 가능 하한",
                "",
                f"- quantile: `{lowest_zero_fp['threshold_quantile']}`",
                f"- threshold: `{lowest_zero_fp['threshold_value']:.6f}`",
                f"- holdout F1/Recall: `{lowest_zero_fp['f1']:.4f}` / `{lowest_zero_fp['recall']:.4f}`",
                "",
            ]
        )

    lines.extend(["## Quantile별 holdout 요약", ""])
    for _, row in holdout.iterrows():
        lines.append(
            f"- q `{row['threshold_quantile']}`: F1 `{row['f1']:.4f}`, Recall `{row['recall']:.4f}`, "
            f"Precision `{row['precision']:.4f}`, FPR `{row['false_positive_rate']:.4f}`, "
            f"TP `{int(row['true_positive_count'])}`, FP `{int(row['false_positive_count'])}`"
        )

    lines.extend(
        [
            "",
            "## Priority 영향",
            "",
            "- 현재 `priority_engine_v2_threshold48`은 `anomaly_label`이 아니라 연속값 `anomaly_score`를 사용한다.",
            "- 따라서 threshold quantile만 바꿔도 priority_score와 priority_level은 직접 바뀌지 않는다.",
            "- quantile 변경은 anomaly_label, 이상치 개수, main abnormal 판단 기준, 보고용 이상 감지 민감도에 영향을 준다.",
            "",
        ]
    )
    if not priority_df.empty:
        lines.append(f"- priority 매칭 holdout rows: `{int(priority_df.iloc[0]['holdout_rows_matched_to_priority'])}`")
        lines.append("- quantile-only priority score delta: `0.0`")
        lines.append("")

    lines.extend(
        [
            "## 해석",
            "",
            "- quantile을 낮추면 더 많은 window를 anomaly로 찍어서 recall은 올라가지만 normal 오탐도 증가한다.",
            "- quantile을 높이면 강한 이상만 잡아서 오탐은 줄지만 pre_fault 선행 이상을 놓칠 가능성이 커진다.",
            "- 현재 공식 q=0.99는 매우 보수적이며 holdout FP는 0이지만 recall이 낮다.",
            "- 운영에서 anomaly_label을 직접 경보로 쓸 거면 q=0.98 또는 q=0.99 같은 보수 구간을 검토하고, risk/priority는 연속 anomaly_score를 유지하는 것이 안전하다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(ANOMALY_SCORES_PATH)
    train_normal_scores = df[df["split_time_based"].eq("train") & df["label"].eq("normal")][SCORE_COLUMN].astype(float)
    thresholds = {q: float(train_normal_scores.quantile(q)) for q in QUANTILES}

    metrics_rows: list[dict] = []
    holdout_frames: list[pd.DataFrame] = []
    for split_column in SPLIT_COLUMNS:
        for quantile, threshold in thresholds.items():
            for split in ["train", "validation", "holdout"]:
                metrics_rows.append(evaluate(df, split_column, split, quantile, threshold))
            if split_column == "split_time_based":
                holdout_frames.append(make_holdout_detail(df, split_column, quantile, threshold))

    metrics_df = pd.DataFrame(metrics_rows)
    holdout_df = pd.concat(holdout_frames, ignore_index=True)
    priority_df = priority_impact(df, thresholds)
    detail = {
        "experiment": "Isolation Forest threshold quantile sweep",
        "input_anomaly_scores_path": str(ANOMALY_SCORES_PATH),
        "priority_v2_threshold48_path": str(PRIORITY_V2_THRESHOLD48_PATH),
        "score_column": SCORE_COLUMN,
        "threshold_reference": "split_time_based == train and label == normal",
        "quantiles": QUANTILES,
        "default_quantile": DEFAULT_QUANTILE,
        "notes": [
            "Changing threshold_quantile changes anomaly_label and anomaly_threshold only.",
            "It does not change iforest_anomaly_score/anomaly_score.",
            "priority_engine_v2_threshold48 uses continuous anomaly_score, so quantile-only change has no direct priority score impact.",
        ],
    }

    metrics_df.to_csv(OUTPUT_METRICS_PATH, index=False, encoding="utf-8-sig")
    holdout_df.to_csv(OUTPUT_HOLDOUT_PATH, index=False, encoding="utf-8-sig")
    priority_df.to_csv(OUTPUT_PRIORITY_IMPACT_PATH, index=False, encoding="utf-8-sig")
    OUTPUT_DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    OUTPUT_MD_PATH.write_text(make_markdown(metrics_df, priority_df), encoding="utf-8-sig")

    print(OUTPUT_METRICS_PATH)
    print(OUTPUT_HOLDOUT_PATH)
    print(OUTPUT_PRIORITY_IMPACT_PATH)
    print(OUTPUT_DETAIL_PATH)
    print(OUTPUT_MD_PATH)
    print()
    holdout = metrics_df[
        metrics_df["evaluation_split_column"].eq("split_time_based") & metrics_df["split"].eq("holdout")
    ].sort_values("threshold_quantile")
    print(holdout.to_string(index=False))


if __name__ == "__main__":
    main()
