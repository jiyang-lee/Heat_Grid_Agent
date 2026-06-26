from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
PRIORITY_DIR = DATA_DIR / "ml_priority"
RISK_DIR = DATA_DIR / "ml_risk"
REPORT_DIR = ROOT / "report" / "experiment_comparison"
MODEL_DIR = PRIORITY_DIR / "models"

PRIORITY_V2_PATH = PRIORITY_DIR / "priority_engine_scores_tuned.csv"
PRIORITY_V2_THRESHOLD48_PATH = PRIORITY_DIR / "priority_engine_scores_v2_threshold48.csv"
RISK_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"

OUTPUT_METRICS_PATH = REPORT_DIR / "priority_lgbm_regression_candidate_metrics.csv"
OUTPUT_SCORES_PATH = REPORT_DIR / "priority_lgbm_regression_candidate_scores.csv"
OUTPUT_FEATURE_IMPORTANCE_PATH = REPORT_DIR / "priority_lgbm_regression_candidate_feature_importance.csv"
OUTPUT_DETAIL_PATH = REPORT_DIR / "priority_lgbm_regression_candidate_detail.json"
OUTPUT_MD_PATH = REPORT_DIR / "07_priority_lgbm_regression_candidate_summary.md"
MODEL_OUTPUT_PATH = MODEL_DIR / "lightgbm_priority_regression_v3_candidate.joblib"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
SPLIT_COLUMN = "split_event_regime_based"
RANDOM_STATE = 42
THRESHOLDS = np.round(np.arange(20.0, 85.5, 0.5), 2)
FPR_LIMITS = [0.0, 0.005, 0.01, 0.02, 0.05]

NUMERIC_FEATURES_LEAK_DIAGNOSTIC = [
    "anomaly_score",
    "risk_probability",
    "risk_score",
    "predicted_lead_time_confidence",
    "leadtime_prob_0-24h",
    "leadtime_prob_1-3d",
    "leadtime_prob_3-7d",
    "lead_time_bucket_distance",
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
    "risk_base_score",
    "risk_probability_component_score",
    "leadtime_bucket_base_score",
    "leadtime_confidence_multiplier",
    "leadtime_component_score",
    "anomaly_component_score",
    "history_adjustment_score",
]
NUMERIC_FEATURES_GUARDED = [
    "anomaly_score",
    "risk_probability",
    "risk_score",
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
    "risk_base_score",
    "risk_probability_component_score",
    "anomaly_component_score",
    "history_adjustment_score",
]
CATEGORICAL_FEATURES_LEAK_DIAGNOSTIC = [
    "manufacturer",
    "risk_level_calibrated",
    "predicted_lead_time_bucket",
]
CATEGORICAL_FEATURES_GUARDED = [
    "manufacturer",
    "risk_level_calibrated",
]


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def priority_target(row: pd.Series) -> float:
    if row["label"] != "pre_fault":
        return 0.0
    bucket = row.get("lead_time_bucket")
    if bucket == "0-24h":
        return 100.0
    if bucket == "1-3d":
        return 80.0
    if bucket == "3-7d":
        return 60.0
    return 70.0


def build_dataset() -> pd.DataFrame:
    priority_path = PRIORITY_V2_THRESHOLD48_PATH if PRIORITY_V2_THRESHOLD48_PATH.exists() else PRIORITY_V2_PATH
    priority_df = pd.read_csv(priority_path)
    risk_df = pd.read_csv(RISK_PATH)
    risk_columns = KEY_COLUMNS + [
        "label",
        "fault_event_id",
        "fault_label",
        "configuration_type",
        "lead_time_bucket",
        "estimated_lead_time_hours",
        SPLIT_COLUMN,
    ]
    df = priority_df.merge(
        risk_df[risk_columns],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    df["target"] = df["label"].eq("pre_fault").astype(int)
    df["priority_regression_target"] = df.apply(priority_target, axis=1)
    return df


def build_model(numeric_features: list[str], categorical_features: list[str]) -> Pipeline:
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    regressor = LGBMRegressor(
        objective="regression",
        n_estimators=400,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=4,
        min_child_samples=25,
        subsample=0.85,
        colsample_bytree=0.9,
        reg_alpha=0.5,
        reg_lambda=1.0,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=-1,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("regressor", regressor)])


def evaluate_threshold(df: pd.DataFrame, variant: str, score_column: str, threshold: float) -> dict:
    y_true = df["target"].astype(int)
    y_pred = (df[score_column] >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "variant": variant,
        "threshold": float(threshold),
        "rows": int(len(df)),
        "positives": int(y_true.sum()),
        "predicted_positive": int(y_pred.sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "false_positive_count": int(((y_pred == 1) & y_true.eq(0)).sum()),
        "true_positive_count": int(((y_pred == 1) & y_true.eq(1)).sum()),
        "mae_to_proxy_target": float(mean_absolute_error(df["priority_regression_target"], df[score_column])),
    }


def find_best_threshold(validation_df: pd.DataFrame, score_column: str, fpr_limit: float) -> float:
    rows = [evaluate_threshold(validation_df, "validation_search", score_column, t) for t in THRESHOLDS]
    sweep = pd.DataFrame(rows)
    allowed = sweep[sweep["false_positive_rate"] <= fpr_limit].copy()
    if allowed.empty:
        return float(sweep.sort_values(["false_positive_rate", "f1"], ascending=[True, False]).iloc[0]["threshold"])
    best = allowed.sort_values(["f1", "recall", "threshold"], ascending=[False, False, False]).iloc[0]
    return float(best["threshold"])


def top_n_coverage(df: pd.DataFrame, score_column: str, n: int) -> float:
    positives = int(df["target"].sum())
    if positives == 0:
        return float("nan")
    top = df.sort_values(score_column, ascending=False).head(n)
    return float(top["target"].sum() / positives)


def metric_summary(df: pd.DataFrame, variant: str, score_column: str, threshold: float) -> dict:
    row = evaluate_threshold(df, variant, score_column, threshold)
    row.update(
        {
            "top10_prefault_coverage": top_n_coverage(df, score_column, 10),
            "top20_prefault_coverage": top_n_coverage(df, score_column, 20),
            "top50_prefault_coverage": top_n_coverage(df, score_column, 50),
            "score_mean": float(df[score_column].mean()),
            "score_p95": float(df[score_column].quantile(0.95)),
        }
    )
    return row


def feature_importance(model: Pipeline, variant: str) -> pd.DataFrame:
    preprocessor = model.named_steps["preprocessor"]
    regressor = model.named_steps["regressor"]
    names = preprocessor.get_feature_names_out()
    return pd.DataFrame(
        {
            "variant": variant,
            "feature": names,
            "importance": regressor.feature_importances_,
        }
    ).sort_values("importance", ascending=False)


def make_markdown(metrics_df: pd.DataFrame, threshold_map: dict) -> str:
    lines = [
        "# 07 Priority LightGBM Regression Candidate Summary",
        "",
        "## 목적",
        "",
        "Rule-based Priority v2_threshold48을 기준으로, LightGBM 회귀모델이 우선순위 점수를 더 잘 정렬할 수 있는지 실험했다.",
        "",
        "## Validation 기준 선택 threshold",
        "",
    ]
    for key, value in threshold_map.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Holdout 비교", ""])
    for _, row in metrics_df.iterrows():
        lines.append(
            f"- `{row['variant']}`: threshold `{row['threshold']:.1f}`, F1 `{row['f1']:.4f}`, "
            f"Recall `{row['recall']:.4f}`, Precision `{row['precision']:.4f}`, "
            f"FPR `{row['false_positive_rate']:.4f}`, TP `{int(row['true_positive_count'])}`, FP `{int(row['false_positive_count'])}`"
        )
    lines.extend(
        [
            "",
            "## 해석",
            "",
            "- v3 후보는 실제 출동 우선순위 정답이 없어서 pre_fault와 leadtime bucket으로 만든 proxy target을 학습한다.",
            "- 현재 leadtime 예측 컬럼은 normal에는 모두 결측, pre_fault에는 모두 존재하므로 그대로 쓰면 라벨 누수가 된다.",
            "- 따라서 승격 검토 대상은 `v3_lgbm_guarded_*` 결과이며, `v3_lgbm_leak_diagnostic_*`는 누수 확인용 기록이다.",
            "- 따라서 회귀 MAE보다 holdout F1, Recall, FPR, TopK 포착률을 중심으로 봐야 한다.",
            "- v2_threshold48보다 FPR을 유지하면서 F1/Recall/TopK가 개선될 때만 v3 승격을 검토한다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    df = build_dataset()

    all_numeric_features = sorted(set(NUMERIC_FEATURES_LEAK_DIAGNOSTIC + NUMERIC_FEATURES_GUARDED))
    all_categorical_features = sorted(set(CATEGORICAL_FEATURES_LEAK_DIAGNOSTIC + CATEGORICAL_FEATURES_GUARDED))
    needed = all_numeric_features + all_categorical_features + [SPLIT_COLUMN, "priority_regression_target", "target"]
    missing = [col for col in needed if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    train_df = df[df[SPLIT_COLUMN].eq("train")].copy()
    validation_df = df[df[SPLIT_COLUMN].eq("validation")].copy()
    holdout_df = df[df[SPLIT_COLUMN].eq("holdout")].copy()
    if train_df.empty or validation_df.empty or holdout_df.empty:
        raise ValueError("train/validation/holdout split is required for priority regression experiment.")

    guarded_model = build_model(NUMERIC_FEATURES_GUARDED, CATEGORICAL_FEATURES_GUARDED)
    guarded_features = NUMERIC_FEATURES_GUARDED + CATEGORICAL_FEATURES_GUARDED
    guarded_model.fit(train_df[guarded_features], train_df["priority_regression_target"])
    joblib.dump(guarded_model, MODEL_OUTPUT_PATH)

    leak_model = build_model(NUMERIC_FEATURES_LEAK_DIAGNOSTIC, CATEGORICAL_FEATURES_LEAK_DIAGNOSTIC)
    leak_features = NUMERIC_FEATURES_LEAK_DIAGNOSTIC + CATEGORICAL_FEATURES_LEAK_DIAGNOSTIC
    leak_model.fit(train_df[leak_features], train_df["priority_regression_target"])

    for part in [train_df, validation_df, holdout_df]:
        guarded_pred = guarded_model.predict(part[guarded_features])
        leak_pred = leak_model.predict(part[leak_features])
        part["priority_lgbm_guarded_score"] = np.clip(guarded_pred, 0.0, 100.0)
        part["priority_lgbm_leak_diagnostic_score"] = np.clip(leak_pred, 0.0, 100.0)
        part["priority_v2_threshold48_score"] = pd.to_numeric(part["priority_score"], errors="coerce").fillna(0.0)
        urgency_prob = pd.to_numeric(part["leadtime_prob_0-24h"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
        risk_gate = part["risk_level_calibrated"].isin(["high", "critical"]).astype(float)
        part["risk_gated_urgency_x8_score"] = (part["priority_v2_threshold48_score"] + urgency_prob * 8.0 * risk_gate).clip(0.0, 100.0)

    threshold_map = {
        "v2_threshold48_fixed": 48.0,
        "risk_gated_urgency_x8_fixed": 52.0,
        "lgbm_guarded_fpr0": find_best_threshold(validation_df, "priority_lgbm_guarded_score", 0.0),
        "lgbm_guarded_fpr1pct": find_best_threshold(validation_df, "priority_lgbm_guarded_score", 0.01),
        "lgbm_guarded_fpr5pct": find_best_threshold(validation_df, "priority_lgbm_guarded_score", 0.05),
        "lgbm_leak_diagnostic_fpr0": find_best_threshold(validation_df, "priority_lgbm_leak_diagnostic_score", 0.0),
    }

    metric_rows = [
        metric_summary(holdout_df, "v2_threshold48", "priority_v2_threshold48_score", threshold_map["v2_threshold48_fixed"]),
        metric_summary(holdout_df, "risk_gated_urgency_x8", "risk_gated_urgency_x8_score", threshold_map["risk_gated_urgency_x8_fixed"]),
        metric_summary(holdout_df, "v3_lgbm_guarded_fpr0", "priority_lgbm_guarded_score", threshold_map["lgbm_guarded_fpr0"]),
        metric_summary(holdout_df, "v3_lgbm_guarded_fpr1pct", "priority_lgbm_guarded_score", threshold_map["lgbm_guarded_fpr1pct"]),
        metric_summary(holdout_df, "v3_lgbm_guarded_fpr5pct", "priority_lgbm_guarded_score", threshold_map["lgbm_guarded_fpr5pct"]),
        metric_summary(
            holdout_df,
            "v3_lgbm_leak_diagnostic_fpr0",
            "priority_lgbm_leak_diagnostic_score",
            threshold_map["lgbm_leak_diagnostic_fpr0"],
        ),
    ]
    metrics_df = pd.DataFrame(metric_rows).sort_values(["f1", "recall"], ascending=[False, False])

    score_columns = KEY_COLUMNS + [
        "label",
        "fault_event_id",
        "fault_label",
        "configuration_type",
        "lead_time_bucket",
        "estimated_lead_time_hours",
        SPLIT_COLUMN,
        "priority_regression_target",
        "target",
        "priority_v2_threshold48_score",
        "risk_gated_urgency_x8_score",
        "priority_lgbm_guarded_score",
        "priority_lgbm_leak_diagnostic_score",
    ]
    scores_df = pd.concat([train_df, validation_df, holdout_df], ignore_index=True)[score_columns].copy()
    scores_df["model_version"] = "priority_engine_v3_lgbm_regression_candidate"

    importance_df = pd.concat(
        [
            feature_importance(guarded_model, "v3_lgbm_guarded"),
            feature_importance(leak_model, "v3_lgbm_leak_diagnostic"),
        ],
        ignore_index=True,
    )
    detail = {
        "model_version": "priority_engine_v3_lgbm_regression_candidate",
        "priority_v2_input_path": str(PRIORITY_V2_PATH),
        "priority_v2_threshold48_path": str(PRIORITY_V2_THRESHOLD48_PATH),
        "risk_path": str(RISK_PATH),
        "model_output_path": str(MODEL_OUTPUT_PATH),
        "target_definition": {
            "normal": 0.0,
            "pre_fault_0-24h": 100.0,
            "pre_fault_1-3d": 80.0,
            "pre_fault_3-7d": 60.0,
            "pre_fault_unknown_bucket": 70.0,
        },
        "guarded_numeric_features": NUMERIC_FEATURES_GUARDED,
        "guarded_categorical_features": CATEGORICAL_FEATURES_GUARDED,
        "leak_diagnostic_numeric_features": NUMERIC_FEATURES_LEAK_DIAGNOSTIC,
        "leak_diagnostic_categorical_features": CATEGORICAL_FEATURES_LEAK_DIAGNOSTIC,
        "threshold_map": threshold_map,
        "split_counts": df[SPLIT_COLUMN].value_counts(dropna=False).to_dict(),
        "notes": [
            "This is a candidate experiment and does not replace priority_engine_v2_threshold48.",
            "The model is trained on a proxy target because actual dispatch priority labels are unavailable.",
            "Validation split is used to select candidate thresholds; holdout is used only for final comparison.",
        ],
    }

    metrics_df.to_csv(OUTPUT_METRICS_PATH, index=False, encoding="utf-8-sig")
    scores_df.to_csv(OUTPUT_SCORES_PATH, index=False, encoding="utf-8-sig")
    importance_df.to_csv(OUTPUT_FEATURE_IMPORTANCE_PATH, index=False, encoding="utf-8-sig")
    OUTPUT_DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    OUTPUT_MD_PATH.write_text(make_markdown(metrics_df, threshold_map), encoding="utf-8-sig")

    print(OUTPUT_METRICS_PATH)
    print(OUTPUT_SCORES_PATH)
    print(OUTPUT_FEATURE_IMPORTANCE_PATH)
    print(OUTPUT_DETAIL_PATH)
    print(OUTPUT_MD_PATH)
    print(MODEL_OUTPUT_PATH)
    print()
    print(metrics_df.to_string(index=False))
    print()
    print(importance_df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
