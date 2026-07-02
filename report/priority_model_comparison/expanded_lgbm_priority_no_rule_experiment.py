from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import confusion_matrix, mean_absolute_error, r2_score


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report" / "priority_model_comparison"
MODEL_DIR = REPORT_DIR / "models"

WINDOWS_PATH = ROOT / "data" / "processed" / "ml_features" / "trainable_windows.csv"
FEATURE_COLUMNS_PATH = ROOT / "data" / "processed" / "ml_features" / "feature_columns.csv"
RAW_LABELED_PATH = REPORT_DIR / "raw_priority_lgbm_vs_rule_labeled_rows.csv"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
TARGET_BUCKETS = ["normal", "3-7d", "1-3d", "0-24h"]
SPLIT_COLUMNS = ["split_time_based", "split_substation_based", "split_regime_based"]
TEAM_LGBM_SCORE_COLUMN = "team_lgbm_priority_score"
RULE_SCORE_COLUMN = "priority_score"
RULE_ACTION_THRESHOLD = 48.0
TEAM_ACTION_THRESHOLD = 49.5

UPSTREAM_NUMERIC_FEATURES = [
    "anomaly_score",
    "risk_score",
    "risk_probability",
    "predicted_lead_time_confidence",
    "leadtime_prob_0-24h",
    "leadtime_prob_1-3d",
    "leadtime_prob_3-7d",
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
]
UPSTREAM_CATEGORICAL_FEATURES = [
    "risk_level_calibrated",
    "predicted_lead_time_bucket",
]
RULE_COMPONENT_COLUMNS = {
    "risk_base_score",
    "risk_probability_component_score",
    "leadtime_bucket_base_score",
    "leadtime_confidence_multiplier",
    "leadtime_component_score",
    "anomaly_component_score",
    "history_adjustment_score",
    "history_adjustment_reason",
    "priority_score",
    "priority_level",
    "priority_reason",
    "engine_version",
}
LEAKAGE_OR_NON_FEATURE_COLUMNS = {
    *KEY_COLUMNS,
    "source_file",
    "main_missing_sensors",
    "main_changed_sensors",
    "season_bucket",
    "label",
    "fault_label",
    "fault_event_id",
    "estimated_lead_time_hours",
    "lead_time_bucket",
    "normal_event_related",
    "maintenance_related",
    "disturbance_count",
    "leakage_blocked_fault_count",
    "window_source_type",
    "use_for_supervised_training",
    "configuration_type",
    "normal_reference_group",
    "normal_reference_outlier",
    "normal_reference_outlier_count",
    "normal_reference_filter_reason",
    "split_time_based",
    "split_substation_based",
    "split_regime_based",
    "target_score",
    "true_bucket",
    "is_pre_fault",
    "is_within_3d",
    "rule_priority_score",
    "rule_priority_level",
    "team_lgbm_score",
    TEAM_LGBM_SCORE_COLUMN,
    "lead_time_bucket_distance",
    "lead_time_target",
    "predicted_lead_time_index",
}


@dataclass(frozen=True)
class Candidate:
    name: str
    params: dict


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
        "r2": r2_score(y, pred) if y.nunique() > 1 else np.nan,
        "spearman": float(spearman),
        **rank_metrics(frame, score_col),
        **action_metrics(frame, score_col, action_threshold),
    }


def best_action_threshold(frame: pd.DataFrame, score_col: str) -> float:
    rows = []
    for threshold in np.round(np.arange(0.0, 100.25, 0.25), 2):
        metric = action_metrics(frame, score_col, float(threshold))
        rows.append(
            {
                "threshold": float(threshold),
                "f1": metric["action_f1"],
                "recall": metric["action_recall"],
                "precision": metric["action_precision"],
                "specificity": metric["action_specificity"],
            }
        )
    thresholds = pd.DataFrame(rows)
    best = thresholds.sort_values(
        ["f1", "recall", "precision", "threshold"],
        ascending=[False, False, False, False],
    ).iloc[0]
    return float(best["threshold"])


def load_dataset() -> pd.DataFrame:
    windows = pd.read_csv(WINDOWS_PATH)
    raw = pd.read_csv(RAW_LABELED_PATH)
    raw_cols = KEY_COLUMNS + [
        "anomaly_score",
        "risk_score",
        "risk_probability",
        "risk_level_calibrated",
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "leadtime_prob_0-24h",
        "leadtime_prob_1-3d",
        "leadtime_prob_3-7d",
        RULE_SCORE_COLUMN,
        "priority_level",
        TEAM_LGBM_SCORE_COLUMN,
    ]
    raw_cols = [column for column in raw_cols if column in raw.columns]
    raw = raw[raw_cols].drop_duplicates(KEY_COLUMNS)

    # Use operational raw-inference upstream outputs if a same-named offline column exists.
    duplicated_output_columns = [column for column in raw_cols if column not in KEY_COLUMNS and column in windows.columns]
    windows = windows.drop(columns=duplicated_output_columns)
    df = windows.merge(raw, on=KEY_COLUMNS, how="inner", validate="one_to_one")

    df["true_bucket"] = df.apply(true_bucket, axis=1)
    df["target_score"] = df["true_bucket"].map(target_score).astype(float)
    df["is_pre_fault"] = df["target_score"] > 0
    df["is_within_3d"] = df["target_score"] >= 66
    df["rule_priority_score"] = pd.to_numeric(df[RULE_SCORE_COLUMN], errors="coerce").clip(0, 100)
    df["team_lgbm_score"] = pd.to_numeric(df[TEAM_LGBM_SCORE_COLUMN], errors="coerce").clip(0, 100)
    return df.copy()


def selected_window_features(df: pd.DataFrame) -> list[str]:
    feature_meta = pd.read_csv(FEATURE_COLUMNS_PATH)
    if "selected_for_baseline" in feature_meta.columns:
        selected = feature_meta[feature_meta["selected_for_baseline"].astype(str).str.lower().eq("true")]
    else:
        selected = feature_meta
    candidates = [column for column in selected["column_name"].tolist() if column in df.columns]
    candidates = [column for column in candidates if column not in LEAKAGE_OR_NON_FEATURE_COLUMNS]
    return [column for column in candidates if pd.api.types.is_numeric_dtype(df[column])]


def build_feature_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    window_features = selected_window_features(df)
    upstream_numeric = [column for column in UPSTREAM_NUMERIC_FEATURES if column in df.columns]
    upstream_categoricals = [column for column in UPSTREAM_CATEGORICAL_FEATURES if column in df.columns]

    numeric_columns = []
    for column in [*window_features, *upstream_numeric]:
        if column not in numeric_columns:
            numeric_columns.append(column)

    base = df[numeric_columns].copy()
    for column in base.columns:
        base[column] = pd.to_numeric(base[column], errors="coerce")

    category_frame = pd.get_dummies(
        df[upstream_categoricals].fillna("missing").astype(str),
        prefix=upstream_categoricals,
        dtype=float,
    )
    features = pd.concat([base, category_frame], axis=1)
    features = features.loc[:, ~features.columns.duplicated()].copy()
    mapping = pd.DataFrame(
        {
            "safe_feature": [f"f_{index:04d}" for index in range(features.shape[1])],
            "original_feature": list(features.columns),
        }
    )
    features.columns = mapping["safe_feature"].tolist()
    return features, mapping


def impute_by_train(features: pd.DataFrame, train_mask: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    medians = features.loc[train_mask].median(numeric_only=True).fillna(0.0)
    return features.fillna(medians).fillna(0.0), medians


def candidate_grid() -> list[Candidate]:
    base = {
        "objective": "regression",
        "n_estimators": 900,
        "learning_rate": 0.03,
        "random_state": 42,
        "n_jobs": 1,
        "verbose": -1,
    }
    variants = [
        {"num_leaves": 7, "max_depth": 3, "min_child_samples": 25, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 1.0, "reg_lambda": 3.0},
        {"num_leaves": 15, "max_depth": 4, "min_child_samples": 20, "subsample": 0.8, "colsample_bytree": 0.85, "reg_alpha": 0.5, "reg_lambda": 2.0},
        {"num_leaves": 15, "max_depth": 5, "min_child_samples": 35, "subsample": 0.9, "colsample_bytree": 0.7, "reg_alpha": 1.0, "reg_lambda": 4.0},
        {"num_leaves": 31, "max_depth": 5, "min_child_samples": 30, "subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 2.0, "reg_lambda": 5.0},
        {"num_leaves": 7, "max_depth": 4, "min_child_samples": 15, "subsample": 0.7, "colsample_bytree": 0.9, "reg_alpha": 0.0, "reg_lambda": 1.5},
        {"num_leaves": 11, "max_depth": 4, "min_child_samples": 45, "subsample": 0.9, "colsample_bytree": 0.9, "reg_alpha": 1.5, "reg_lambda": 6.0},
    ]
    return [Candidate(f"expanded_lgbm_{index:02d}", {**base, **params}) for index, params in enumerate(variants, start=1)]


def validation_selection_score(metrics: dict) -> float:
    return (
        1.3 * metrics.get("action_f1", 0.0)
        + 0.8 * metrics.get("ndcg@R", 0.0)
        + 0.6 * metrics.get("recall@100", 0.0)
        + 0.4 * metrics.get("spearman", 0.0)
        - 0.003 * metrics.get("mae", 0.0)
    )


def train_for_split(
    df: pd.DataFrame,
    features: pd.DataFrame,
    feature_mapping: pd.DataFrame,
    split_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, np.ndarray, pd.Series]:
    train_mask = df[split_column].eq("train")
    validation_mask = df[split_column].eq("validation")
    holdout_mask = df[split_column].eq("holdout")
    features_imputed, medians = impute_by_train(features, train_mask)
    y = df["target_score"].astype(float)

    rows = []
    trained: dict[str, lgb.LGBMRegressor] = {}
    for candidate in candidate_grid():
        model = lgb.LGBMRegressor(**candidate.params)
        model.fit(
            features_imputed.loc[train_mask],
            y.loc[train_mask],
            eval_set=[(features_imputed.loc[validation_mask], y.loc[validation_mask])],
            eval_metric="l2",
            callbacks=[lgb.early_stopping(60, verbose=False), lgb.log_evaluation(0)],
        )
        score_col = f"{candidate.name}_score"
        validation_part = df.loc[validation_mask].copy()
        validation_part[score_col] = np.clip(model.predict(features_imputed.loc[validation_mask]), 0, 100)
        threshold = best_action_threshold(validation_part, score_col)
        metric = metrics_for(validation_part, "validation", candidate.name, score_col, threshold)
        metric["split_strategy"] = split_column
        metric["selected_action_threshold"] = threshold
        metric["best_iteration"] = int(model.best_iteration_ or 0)
        metric["selection_score"] = validation_selection_score(metric)
        rows.append(metric)
        trained[candidate.name] = model

    selection = pd.DataFrame(rows).sort_values(
        ["selection_score", "action_f1", "ndcg@R", "spearman"],
        ascending=[False, False, False, False],
    )
    best_name = str(selection.iloc[0]["model_key"])
    best_threshold = float(selection.iloc[0]["selected_action_threshold"])
    model = trained[best_name]
    prediction = np.clip(model.predict(features_imputed), 0, 100)

    work = df.copy()
    score_col = f"expanded_lgbm_{split_column}_score"
    work[score_col] = prediction
    holdout = work.loc[holdout_mask].copy()
    metric_rows = [
        metrics_for(holdout, f"{split_column}_holdout", "rule_base_raw_inference", "rule_priority_score", RULE_ACTION_THRESHOLD),
        metrics_for(holdout, f"{split_column}_holdout", "team_7feature_lgbm_raw", "team_lgbm_score", TEAM_ACTION_THRESHOLD),
        metrics_for(holdout, f"{split_column}_holdout", "expanded_lgbm_raw_upstream", score_col, best_threshold),
    ]
    metrics_df = pd.DataFrame(metric_rows)

    feature_importance = feature_mapping.copy()
    feature_importance["split_strategy"] = split_column
    feature_importance["importance"] = model.feature_importances_
    feature_importance = feature_importance.sort_values(
        ["split_strategy", "importance"], ascending=[True, False]
    ).reset_index(drop=True)

    model_bundle = {
        "model": model,
        "split_strategy": split_column,
        "selected_model_key": best_name,
        "action_threshold": best_threshold,
        "feature_mapping": feature_mapping,
        "imputation_medians": medians,
        "input_basis": str(RAW_LABELED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "excluded_rule_columns": sorted(RULE_COMPONENT_COLUMNS),
    }
    return selection, metrics_df, feature_importance, model_bundle, prediction, medians


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
    widths = [max(len(str(col)), *(len(row[index]) for row in rows)) for index, col in enumerate(cols)]
    header = "| " + " | ".join(str(col).ljust(widths[index]) for index, col in enumerate(cols)) + " |"
    sep = "| " + " | ".join("-" * widths[index] for index in range(len(cols))) + " |"
    body = ["| " + " | ".join(row[index].ljust(widths[index]) for index in range(len(cols))) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def leadtime_missing_audit(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in [
        "predicted_lead_time_bucket",
        "predicted_lead_time_confidence",
        "leadtime_prob_0-24h",
        "leadtime_prob_1-3d",
        "leadtime_prob_3-7d",
    ]:
        if column not in df.columns:
            continue
        rows.append(
            {
                "column": column,
                "missing_count": int(df[column].isna().sum()),
                "missing_rate": float(df[column].isna().mean()),
            }
        )
    return pd.DataFrame(rows)


def split_event_audit(df: pd.DataFrame) -> pd.DataFrame:
    pre_fault = df[df["label"].eq("pre_fault") & df["fault_event_id"].notna()].copy()
    grouped = (
        pre_fault.groupby("fault_event_id")["split_time_based"]
        .agg(lambda values: ",".join(sorted(set(map(str, values)))))
        .reset_index()
    )
    grouped["split_count"] = grouped["split_time_based"].str.count(",") + 1
    overlap_count = int(grouped["split_count"].gt(1).sum())
    return pd.DataFrame(
        [
            {
                "audit_item": "fault_event_id_cross_split_time_based",
                "count": overlap_count,
                "base": int(len(grouped)),
            }
        ]
    )


def write_report(
    df: pd.DataFrame,
    metrics_df: pd.DataFrame,
    selection_df: pd.DataFrame,
    feature_importance: pd.DataFrame,
    feature_mapping: pd.DataFrame,
) -> None:
    target_distribution = (
        df["true_bucket"]
        .value_counts()
        .reindex(TARGET_BUCKETS)
        .fillna(0)
        .astype(int)
        .rename_axis("bucket")
        .reset_index(name="count")
    )
    missing_audit = leadtime_missing_audit(df)
    event_audit = split_event_audit(df)

    focus_columns = [
        "split",
        "model_key",
        "n",
        "mae",
        "rmse",
        "spearman",
        "precision@R",
        "recall@R",
        "ndcg@R",
        "precision@100",
        "recall@100",
        "ndcg@100",
        "action_threshold",
        "action_precision",
        "action_recall",
        "action_f1",
        "action_specificity",
        "action_rate",
        "fp",
        "fn",
    ]
    focus = metrics_df[focus_columns].copy()

    selected_cols = [
        "split_strategy",
        "model_key",
        "selection_score",
        "selected_action_threshold",
        "mae",
        "spearman",
        "ndcg@R",
        "recall@100",
        "action_precision",
        "action_recall",
        "action_f1",
        "fp",
        "fn",
        "best_iteration",
    ]
    selection_top = selection_df.sort_values(
        ["split_strategy", "selection_score"], ascending=[True, False]
    ).groupby("split_strategy").head(1)[selected_cols]

    top_importance = (
        feature_importance.sort_values(["split_strategy", "importance"], ascending=[True, False])
        .groupby("split_strategy")
        .head(15)[["split_strategy", "original_feature", "importance"]]
    )

    lines = [
        "# Expanded LGBM Priority 실험: 운영 추론 기준 재검토",
        "",
        "## 핵심 결론",
        "",
        "이전 `priority_engine_scores_tuned.csv` 기준 결과는 폐기한다. 해당 파일은 leadtime score가 pre_fault 행에만 생성되고 normal 행에는 결측으로 남아, `predicted_lead_time_bucket_missing`이 사실상 정답 힌트로 동작했다.",
        "",
        "이번 보고서는 실제 inference package 산출물인 `raw_inference_scores.csv`에서 label join된 `raw_priority_lgbm_vs_rule_labeled_rows.csv`를 기준으로 다시 학습/비교했다. 이 기준에서는 normal에도 leadtime 예측값이 존재하므로 결측 누수 효과가 제거된다.",
        "",
        "현재 판정은 `expanded LGBM이 룰베이스를 안정적으로 이겼다`가 아니다. 일부 split과 일부 지표에서 개선 가능성은 보였지만, 운영 baseline은 아직 rule-base가 더 안전하다.",
        "",
        "## 데이터",
        "",
        f"- 입력 기준: `report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv`",
        f"- 학습/비교 rows: `{len(df)}`",
        f"- feature 수: `{len(feature_mapping)}`",
        "- target: normal=0, 3-7d=33, 1-3d=66, 0-24h=100",
        "- 모델 선택: 각 split의 train에서 학습, validation에서 모델/threshold 선택, holdout은 최종 평가에만 사용",
        "",
        "Target 분포:",
        "",
        markdown_table(target_distribution, float_digits=0),
        "",
        "Leadtime 결측 감사:",
        "",
        markdown_table(missing_audit, float_digits=4),
        "",
        "Split 감사:",
        "",
        markdown_table(event_audit, float_digits=0),
        "",
        "## 명시적으로 제외한 입력",
        "",
        "```text",
        "priority_score",
        "priority_level",
        "priority_reason",
        "risk_base_score",
        "risk_probability_component_score",
        "leadtime_component_score",
        "anomaly_component_score",
        "history_adjustment_score",
        "lead_time_bucket_distance",
        "lead_time_target",
        "predicted_lead_time_index",
        "label / fault_event_id / estimated_lead_time_hours 등 정답/식별자 계열",
        "```",
        "",
        "## Validation 선택 결과",
        "",
        markdown_table(selection_top, float_digits=4),
        "",
        "## Holdout 비교",
        "",
        markdown_table(focus, float_digits=4),
        "",
        "## 상위 Feature Importance",
        "",
        markdown_table(top_importance, float_digits=4),
        "",
        "## 해석",
        "",
        "- `split_time_based_holdout`: expanded LGBM은 MAE와 high/urgent F1은 개선했지만, NDCG@R은 rule-base보다 낮다.",
        "- `split_substation_based_holdout`: 새 설비/미등장 설비 관점에서는 rule-base가 F1과 NDCG@R 모두 더 안정적이다.",
        "- `split_regime_based_holdout`: expanded LGBM은 recall/F1은 높지만, MAE와 NDCG@R은 rule-base보다 나쁘다.",
        "",
        "## 최종 판정",
        "",
        "누수 제거 후에는 expanded LGBM이 룰베이스를 압도하지 않는다. 운영 자동화 기준에서는 rule-base를 baseline으로 유지하고, expanded LGBM은 추가 검증 후보로 보는 것이 맞다.",
        "",
        "다음 단계는 priority head를 바로 교체하는 것이 아니라, upstream output을 out-of-fold 방식으로 만들고 fault-event group split까지 포함해 다시 검증하는 것이다.",
        "",
        "## 산출물",
        "",
        "- report: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_report.md`",
        "- metrics: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_metrics.csv`",
        "- validation selection: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_selection.csv`",
        "- feature mapping: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_features.csv`",
        "- feature importance: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_feature_importance.csv`",
        "- predictions: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_predictions.csv`",
        "- model bundle: `report/priority_model_comparison/models/expanded_lgbm_priority_no_rule.joblib`",
        "",
    ]
    (REPORT_DIR / "expanded_lgbm_priority_no_rule_report.md").write_text("\n".join(lines), encoding="utf-8-sig")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = load_dataset()
    features, feature_mapping = build_feature_frame(df)

    all_selection = []
    all_metrics = []
    all_importance = []
    all_medians = []
    model_bundle = {
        "input_basis": str(RAW_LABELED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "feature_mapping": feature_mapping,
        "models": {},
        "thresholds": {},
        "excluded_rule_columns": sorted(RULE_COMPONENT_COLUMNS),
        "note": "Corrected run based on operational raw inference outputs, not offline pre_fault-only leadtime scores.",
    }
    prediction_cols = KEY_COLUMNS + [
        "label",
        "estimated_lead_time_hours",
        "true_bucket",
        "target_score",
        "split_time_based",
        "split_substation_based",
        "split_regime_based",
        "rule_priority_score",
        "team_lgbm_score",
    ]
    predictions = df[prediction_cols].copy()

    for split_column in SPLIT_COLUMNS:
        selection, metrics, importance, bundle, prediction, medians = train_for_split(
            df, features, feature_mapping, split_column
        )
        all_selection.append(selection)
        all_metrics.append(metrics)
        all_importance.append(importance)
        all_medians.append(pd.DataFrame({"split_strategy": split_column, "safe_feature": medians.index, "median": medians.values}))
        model_bundle["models"][split_column] = bundle["model"]
        model_bundle["thresholds"][split_column] = {
            "selected_model_key": bundle["selected_model_key"],
            "action_threshold": bundle["action_threshold"],
        }
        model_bundle["imputation_medians"] = model_bundle.get("imputation_medians", {})
        model_bundle["imputation_medians"][split_column] = medians
        predictions[f"expanded_lgbm_{split_column}_score"] = prediction

    selection_df = pd.concat(all_selection, ignore_index=True)
    metrics_df = pd.concat(all_metrics, ignore_index=True)
    feature_importance = pd.concat(all_importance, ignore_index=True)
    imputation_df = pd.concat(all_medians, ignore_index=True)

    predictions.to_csv(REPORT_DIR / "expanded_lgbm_priority_no_rule_predictions.csv", index=False, encoding="utf-8-sig")
    metrics_df.to_csv(REPORT_DIR / "expanded_lgbm_priority_no_rule_metrics.csv", index=False, encoding="utf-8-sig")
    selection_df.to_csv(REPORT_DIR / "expanded_lgbm_priority_no_rule_selection.csv", index=False, encoding="utf-8-sig")
    feature_mapping.to_csv(REPORT_DIR / "expanded_lgbm_priority_no_rule_features.csv", index=False, encoding="utf-8-sig")
    feature_importance.to_csv(
        REPORT_DIR / "expanded_lgbm_priority_no_rule_feature_importance.csv",
        index=False,
        encoding="utf-8-sig",
    )
    imputation_df.to_csv(REPORT_DIR / "expanded_lgbm_priority_no_rule_imputation.csv", index=False, encoding="utf-8-sig")
    joblib.dump(model_bundle, MODEL_DIR / "expanded_lgbm_priority_no_rule.joblib")
    write_report(df, metrics_df, selection_df, feature_importance, feature_mapping)

    print(REPORT_DIR / "expanded_lgbm_priority_no_rule_report.md")
    print(REPORT_DIR / "expanded_lgbm_priority_no_rule_metrics.csv")
    print(MODEL_DIR / "expanded_lgbm_priority_no_rule.joblib")


if __name__ == "__main__":
    main()
