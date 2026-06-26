from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import confusion_matrix, mean_absolute_error


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report" / "priority_model_comparison"

RAW_SCORES_PATH = REPORT_DIR / "raw_inference_scores.csv"
WINDOW_LABELS_PATH = ROOT / "data" / "processed" / "ml_features" / "trainable_windows.csv"
TEAM_MODEL_PATH = (
    ROOT
    / "lgbm_priority_model"
    / "heatgrid_priority_model_2026-06-26"
    / "model_handoff"
    / "heatgrid_priority_model_2026-06-26"
    / "priority"
    / "lightgbm_priority_model.joblib"
)
TEAM_METADATA_PATH = (
    ROOT
    / "lgbm_priority_model"
    / "heatgrid_priority_model_2026-06-26"
    / "model_handoff"
    / "heatgrid_priority_model_2026-06-26"
    / "priority"
    / "priority_model_metadata.json"
)

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
TEAM_FEATURES = [
    "anomaly_score",
    "risk_probability",
    "risk_score",
    "leadtime_prob_0-24h",
    "leadtime_prob_1-3d",
    "leadtime_prob_3-7d",
    "predicted_lead_time_confidence",
]


def true_bucket(row: pd.Series) -> str:
    if row["label"] == "normal":
        return "normal"
    hours = float(row["estimated_lead_time_hours"])
    if hours <= 24:
        return "0-24h"
    if hours <= 72:
        return "1-3d"
    return "3-7d"


def target_score(bucket: str) -> int:
    return {"normal": 0, "3-7d": 33, "1-3d": 66, "0-24h": 100}[bucket]


def lgbm_level(score: float) -> str:
    if score >= 83.0:
        return "urgent"
    if score >= 49.5:
        return "high"
    if score >= 16.5:
        return "medium"
    return "low"


def ndcg_at_k(relevance: np.ndarray, scores: np.ndarray, k: int) -> float:
    if len(relevance) == 0 or np.max(relevance) <= 0:
        return np.nan
    k = min(k, len(relevance))
    order = np.argsort(scores)[::-1][:k]
    ideal = np.argsort(relevance)[::-1][:k]
    discounts = 1.0 / np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(relevance[order] * discounts))
    idcg = float(np.sum(relevance[ideal] * discounts))
    return dcg / idcg if idcg > 0 else np.nan


def rank_metrics(frame: pd.DataFrame, score_col: str) -> dict:
    y_positive = frame["is_pre_fault"].to_numpy(dtype=bool)
    relevance = (frame["target_score"].astype(float) / 100.0).to_numpy()
    scores = frame[score_col].astype(float).to_numpy()
    positives = int(y_positive.sum())
    out = {"pre_fault_count": positives}
    for k in [10, 20, 50, 100, positives]:
        if k <= 0 or k > len(frame):
            continue
        label = "R" if k == positives else str(k)
        order = np.argsort(scores)[::-1][:k]
        hits = int(y_positive[order].sum())
        out[f"precision@{label}"] = hits / k
        out[f"recall@{label}"] = hits / positives if positives else np.nan
        out[f"ndcg@{label}"] = ndcg_at_k(relevance, scores, k)
    return out


def action_metrics(frame: pd.DataFrame, score_col: str, high_threshold: float) -> dict:
    y_true = frame["is_within_3d"].to_numpy(dtype=bool)
    y_pred = frame[score_col].astype(float).ge(high_threshold).to_numpy()
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[False, True]).ravel()
    precision = tp / (tp + fp) if tp + fp else np.nan
    recall = tp / (tp + fn) if tp + fn else np.nan
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else np.nan
    specificity = tn / (tn + fp) if tn + fp else np.nan
    return {
        "action_threshold": high_threshold,
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "action_precision": precision,
        "action_recall": recall,
        "action_f1": f1,
        "action_specificity": specificity,
        "action_rate": float(y_pred.mean()),
    }


def metrics_for(frame: pd.DataFrame, split: str, model_key: str, score_col: str, action_threshold: float) -> dict:
    y = frame["target_score"].astype(float)
    pred = frame[score_col].astype(float)
    spearman = spearmanr(y, pred).statistic if y.nunique() > 1 and pred.nunique() > 1 else np.nan
    return {
        "split": split,
        "model_key": model_key,
        "n": int(len(frame)),
        "mae": mean_absolute_error(y, pred),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "spearman": float(spearman),
        **rank_metrics(frame, score_col),
        **action_metrics(frame, score_col, action_threshold),
    }


def load_data() -> pd.DataFrame:
    raw = pd.read_csv(RAW_SCORES_PATH)
    model = joblib.load(TEAM_MODEL_PATH)
    raw["team_lgbm_priority_score"] = np.clip(model.predict(raw[TEAM_FEATURES].astype(float)), 0, 100)
    raw["team_lgbm_priority_level"] = raw["team_lgbm_priority_score"].map(lgbm_level)

    label_cols = KEY_COLUMNS + [
        "label",
        "estimated_lead_time_hours",
        "split_time_based",
        "split_substation_based",
        "split_regime_based",
        "use_for_supervised_training",
    ]
    labels = pd.read_csv(WINDOW_LABELS_PATH, usecols=label_cols)
    labels = labels.drop_duplicates(KEY_COLUMNS)

    scored = raw.merge(labels, on=KEY_COLUMNS, how="left", validate="one_to_one")
    scored["has_label"] = scored["label"].notna()
    labeled = scored[scored["has_label"]].copy()
    labeled["true_bucket"] = labeled.apply(true_bucket, axis=1)
    labeled["target_score"] = labeled["true_bucket"].map(target_score).astype(float)
    labeled["is_pre_fault"] = labeled["target_score"] > 0
    labeled["is_within_3d"] = labeled["target_score"] >= 66
    labeled["raw_rule_priority_score"] = pd.to_numeric(labeled["priority_score"], errors="coerce").clip(0, 100)
    labeled["raw_rule_priority_level"] = labeled["priority_level"]
    return scored, labeled


def markdown_table(df: pd.DataFrame, float_digits: int = 4) -> str:
    if df.empty:
        return "_empty_"

    def fmt(value: object) -> str:
        if pd.isna(value):
            text = ""
        elif isinstance(value, float):
            text = f"{value:.{float_digits}f}"
        else:
            text = str(value)
        return text.replace("|", "\\|")

    cols = list(df.columns)
    rows = [[fmt(row[col]) for col in cols] for _, row in df.iterrows()]
    widths = [max(len(str(col)), *(len(row[i]) for row in rows)) for i, col in enumerate(cols)]
    header = "| " + " | ".join(str(col).ljust(widths[i]) for i, col in enumerate(cols)) + " |"
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(cols))) + " |"
    body = ["| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(cols))) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def write_report(scored: pd.DataFrame, labeled: pd.DataFrame, metrics_df: pd.DataFrame) -> None:
    with TEAM_METADATA_PATH.open("r", encoding="utf-8") as f:
        team_meta = json.load(f)

    labeled_counts = labeled["true_bucket"].value_counts().reindex(["normal", "3-7d", "1-3d", "0-24h"]).fillna(0).astype(int)
    split_counts = labeled["split_time_based"].value_counts().reindex(["train", "validation", "holdout"]).fillna(0).astype(int)
    focus = metrics_df[
        metrics_df["split"].isin(["all_labeled", "split_time_holdout", "team_mod3_holdout"])
    ][
        [
            "split",
            "model_key",
            "n",
            "mae",
            "rmse",
            "spearman",
            "precision@10",
            "recall@10",
            "ndcg@10",
            "precision@R",
            "recall@R",
            "ndcg@R",
            "precision@100",
            "recall@100",
            "ndcg@100",
            "action_precision",
            "action_recall",
            "action_f1",
            "action_specificity",
            "action_rate",
            "fp",
            "fn",
        ]
    ]

    holdout = metrics_df[metrics_df["split"].eq("split_time_holdout")].set_index("model_key")
    rule = holdout.loc["raw_rule"]
    lgbm = holdout.loc["team_lgbm"]

    lines = [
        "# Raw 기반 LGBM Priority Regression vs Rule-base 실험",
        "",
        "## 목적",
        "",
        "팀원 `priority_with_readme`의 LGBM priority regression을 실제 raw operational data에서 출발한 inference 결과에 붙여, 현재 rule-based priority engine과 비교했다.",
        "",
        "실험 흐름:",
        "",
        "```text",
        "data/raw_data/predist_v2",
        "-> inference_handoff raw windowing",
        "-> anomaly/risk/leadtime upstream score 생성",
        "-> rule-based priority score",
        "-> 팀원 LGBM priority head 적용",
        "-> trainable_windows label과 key join 후 평가",
        "```",
        "",
        "## 사용한 파일",
        "",
        "- raw scoring output: `report/priority_model_comparison/raw_inference_scores.csv`",
        "- team LGBM model: `lgbm_priority_model/.../priority/lightgbm_priority_model.joblib`",
        "- labels for evaluation: `data/processed/ml_features/trainable_windows.csv`",
        "",
        "## 데이터 매칭",
        "",
        f"- raw inference 전체 rows: `{len(scored)}`",
        f"- label join 가능 rows: `{len(labeled)}`",
        f"- label join rate: `{len(labeled) / len(scored):.4%}`",
        f"- split_time_based 분포: train `{split_counts['train']}`, validation `{split_counts['validation']}`, holdout `{split_counts['holdout']}`",
        f"- target bucket 분포: normal `{labeled_counts['normal']}`, 3-7d `{labeled_counts['3-7d']}`, 1-3d `{labeled_counts['1-3d']}`, 0-24h `{labeled_counts['0-24h']}`",
        "",
        "raw inference는 전체 운영 기간의 모든 6시간 window를 만들지만, 성능 평가는 라벨이 있는 window에 대해서만 가능하다.",
        "",
        "## 팀원 모델 구조",
        "",
        f"- model_version: `{team_meta.get('model_version')}`",
        f"- model_type: `{team_meta.get('model_type')}`",
        f"- training_basis metadata: `{team_meta.get('training_basis')}`",
        "",
        "입력 feature:",
        "",
        "```text",
        "\n".join(TEAM_FEATURES),
        "```",
        "",
        "팀원 LGBM은 raw sensor를 직접 보지 않고, raw에서 upstream 모델을 거쳐 나온 7개 score/probability feature만 사용한다.",
        "",
        "## 비교 결과",
        "",
        markdown_table(focus, float_digits=4),
        "",
        "## 핵심 판정",
        "",
        f"- split_time_based holdout 기준 rule MAE `{rule['mae']:.4f}`, LGBM MAE `{lgbm['mae']:.4f}`",
        f"- split_time_based holdout 기준 rule NDCG@R `{rule['ndcg@R']:.4f}`, LGBM NDCG@R `{lgbm['ndcg@R']:.4f}`",
        f"- split_time_based holdout 기준 rule high/urgent recall `{rule['action_recall']:.4f}`, LGBM high/urgent recall `{lgbm['action_recall']:.4f}`",
        f"- split_time_based holdout 기준 rule high/urgent F1 `{rule['action_f1']:.4f}`, LGBM high/urgent F1 `{lgbm['action_f1']:.4f}`",
        "",
        "현재 raw 기반 inference 결과에 팀원 LGBM head를 붙여도, 공식 운영 holdout 기준에서는 rule-base가 더 안정적이다.",
        "",
        "## 해석",
        "",
        "1. 팀원 LGBM은 raw 전체를 직접 학습한 모델이 아니다. raw에서 만들어진 anomaly/risk/leadtime score 7개를 다시 섞는 priority head다.",
        "2. rule-base도 같은 upstream score를 쓰지만, risk level, leadtime bucket, history adjustment를 명시적으로 반영한다.",
        "3. raw 전체 window에서는 rule-base가 high/urgent를 더 많이 만들고, LGBM은 더 보수적으로 높은 점수를 준다.",
        "4. 라벨이 있는 holdout 평가에서는 LGBM의 보수성이 recall 손실로 나타난다.",
        "5. 따라서 현재 raw inference chain 기준에서도 LGBM priority regression을 rule-base 대신 운영 공식 모델로 교체할 근거는 부족하다.",
        "",
        "## 최종 결론",
        "",
        "```text",
        "현재 raw 기반 실험 기준:",
        "rule-base > team LGBM priority regression",
        "",
        "운영 권장:",
        "rule-base priority_engine_v2_threshold48 유지",
        "team LGBM은 shadow score 또는 추가 재학습 후보로 유지",
        "```",
        "",
        "LGBM이 rule-base를 이기려면 priority head가 7개 upstream score만 쓰는 구조를 넘어, raw/window sensor feature, history feature, rule component score까지 포함한 재학습이 필요하다.",
        "",
    ]
    (REPORT_DIR / "raw_priority_lgbm_vs_rule_report.md").write_text("\n".join(lines), encoding="utf-8-sig")


def main() -> None:
    scored, labeled = load_data()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    slim_cols = KEY_COLUMNS + [
        "source_file",
        "configuration_type",
        "anomaly_score",
        "risk_score",
        "risk_probability",
        "risk_level_calibrated",
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "leadtime_prob_0-24h",
        "leadtime_prob_1-3d",
        "leadtime_prob_3-7d",
        "priority_score",
        "priority_level",
        "team_lgbm_priority_score",
        "team_lgbm_priority_level",
        "label",
        "estimated_lead_time_hours",
        "split_time_based",
        "true_bucket",
        "target_score",
    ]
    labeled[slim_cols].to_csv(REPORT_DIR / "raw_priority_lgbm_vs_rule_labeled_rows.csv", index=False, encoding="utf-8-sig")

    metric_rows = []
    eval_sets = {
        "all_labeled": labeled,
        "split_time_train": labeled[labeled["split_time_based"].eq("train")],
        "split_time_validation": labeled[labeled["split_time_based"].eq("validation")],
        "split_time_holdout": labeled[labeled["split_time_based"].eq("holdout")],
        "team_mod3_holdout": labeled[labeled["substation_id"].astype(int).mod(3).eq(0)],
    }
    for split, frame in eval_sets.items():
        if frame.empty:
            continue
        metric_rows.append(metrics_for(frame, split, "raw_rule", "raw_rule_priority_score", 48.0))
        metric_rows.append(metrics_for(frame, split, "team_lgbm", "team_lgbm_priority_score", 49.5))
    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(REPORT_DIR / "raw_priority_lgbm_vs_rule_metrics.csv", index=False, encoding="utf-8-sig")
    write_report(scored, labeled, metrics_df)

    print(REPORT_DIR / "raw_priority_lgbm_vs_rule_report.md")
    print(REPORT_DIR / "raw_priority_lgbm_vs_rule_metrics.csv")
    print(REPORT_DIR / "raw_priority_lgbm_vs_rule_labeled_rows.csv")


if __name__ == "__main__":
    main()
