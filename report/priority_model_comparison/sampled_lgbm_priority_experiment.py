from __future__ import annotations

import sys
import hashlib
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from expanded_lgbm_priority_no_rule_experiment import (  # noqa: E402
    KEY_COLUMNS,
    MODEL_DIR,
    REPORT_DIR,
    RULE_ACTION_THRESHOLD,
    SPLIT_COLUMNS,
    TEAM_ACTION_THRESHOLD,
    build_feature_frame,
    candidate_grid,
    impute_by_train,
    load_dataset,
    markdown_table,
    metrics_for,
    validation_selection_score,
    best_action_threshold,
)


RANDOM_STATE = 42
OUTPUT_PREFIX = "sampled_lgbm_priority"


@dataclass(frozen=True)
class SamplingStrategy:
    name: str
    description: str
    use_severity: bool = False
    use_hard_cases: bool = False
    use_event_balance: bool = False
    use_substation_balance: bool = False
    resample: bool = False


STRATEGIES = [
    SamplingStrategy(
        name="baseline_no_weight",
        description="No train sampling or weighting.",
    ),
    SamplingStrategy(
        name="severity_weighted",
        description="Upweight 0-24h/1-3d/3-7d pre-fault rows and slightly downweight normal rows.",
        use_severity=True,
    ),
    SamplingStrategy(
        name="hard_case_weighted",
        description="Upweight hard negatives and low-signal positives based on upstream model outputs.",
        use_hard_cases=True,
    ),
    SamplingStrategy(
        name="event_balanced",
        description="Equalize pre-fault fault_event_id contribution inside train.",
        use_event_balance=True,
    ),
    SamplingStrategy(
        name="substation_balanced",
        description="Reduce dominance of high-row-count substations inside train.",
        use_substation_balance=True,
    ),
    SamplingStrategy(
        name="combined_context_weighted",
        description="Combine severity, hard-case, event, and substation weighting.",
        use_severity=True,
        use_hard_cases=True,
        use_event_balance=True,
        use_substation_balance=True,
    ),
    SamplingStrategy(
        name="combined_context_resampled",
        description="Sample train rows with replacement using combined context weights.",
        use_severity=True,
        use_hard_cases=True,
        use_event_balance=True,
        use_substation_balance=True,
        resample=True,
    ),
]


def hard_case_thresholds(train_df: pd.DataFrame) -> dict[str, float]:
    numeric = {}
    for column in ["risk_probability", "leadtime_prob_0-24h", "anomaly_score", "predicted_lead_time_confidence"]:
        if column in train_df.columns:
            numeric[column] = pd.to_numeric(train_df[column], errors="coerce")
    return {
        "risk_high": float(numeric.get("risk_probability", pd.Series([0.0])).quantile(0.80)),
        "leadtime_high": float(numeric.get("leadtime_prob_0-24h", pd.Series([0.0])).quantile(0.80)),
        "anomaly_high": float(numeric.get("anomaly_score", pd.Series([0.0])).quantile(0.80)),
        "risk_low": float(numeric.get("risk_probability", pd.Series([0.0])).quantile(0.35)),
        "confidence_low": float(numeric.get("predicted_lead_time_confidence", pd.Series([0.0])).quantile(0.35)),
    }


def normalized_train_weights(weights: pd.Series, train_mask: pd.Series, clip_hi: float = 10.0) -> pd.Series:
    result = weights.astype(float).copy()
    result.loc[~train_mask] = 1.0
    train_mean = result.loc[train_mask].mean()
    if pd.notna(train_mean) and train_mean > 0:
        result.loc[train_mask] = result.loc[train_mask] / train_mean
    result.loc[train_mask] = result.loc[train_mask].clip(0.20, clip_hi)
    return result


def strategy_weights(df: pd.DataFrame, split_column: str, strategy: SamplingStrategy) -> tuple[pd.Series, pd.DataFrame]:
    train_mask = df[split_column].eq("train")
    train_df = df.loc[train_mask].copy()
    weights = pd.Series(1.0, index=df.index, dtype=float)
    diagnostics: list[dict] = []

    if strategy.use_severity:
        severity = df["target_score"].map({0.0: 0.75, 33.0: 2.0, 66.0: 3.0, 100.0: 4.0}).fillna(1.0)
        weights.loc[train_mask] *= severity.loc[train_mask]
        diagnostics.append({"component": "severity", "affected_train_rows": int(train_mask.sum())})

    if strategy.use_hard_cases:
        thresholds = hard_case_thresholds(train_df)
        risk = pd.to_numeric(df.get("risk_probability"), errors="coerce")
        lead_0_24 = pd.to_numeric(df.get("leadtime_prob_0-24h"), errors="coerce")
        anomaly = pd.to_numeric(df.get("anomaly_score"), errors="coerce")
        confidence = pd.to_numeric(df.get("predicted_lead_time_confidence"), errors="coerce")

        hard_negative = (
            train_mask
            & df["target_score"].eq(0)
            & (
                risk.ge(thresholds["risk_high"])
                | lead_0_24.ge(thresholds["leadtime_high"])
                | anomaly.ge(thresholds["anomaly_high"])
            )
        )
        low_signal_positive = (
            train_mask
            & df["target_score"].gt(0)
            & (risk.le(thresholds["risk_low"]) | confidence.le(thresholds["confidence_low"]))
        )
        weights.loc[hard_negative] *= 2.8
        weights.loc[low_signal_positive] *= 2.2
        diagnostics.append({"component": "hard_negative", "affected_train_rows": int(hard_negative.sum())})
        diagnostics.append({"component": "low_signal_positive", "affected_train_rows": int(low_signal_positive.sum())})

    if strategy.use_event_balance and "fault_event_id" in df.columns:
        event_mask = train_mask & df["target_score"].gt(0) & df["fault_event_id"].notna()
        event_counts = df.loc[event_mask].groupby("fault_event_id")["fault_event_id"].transform("count")
        if not event_counts.empty:
            event_factor = np.sqrt(float(event_counts.mean()) / event_counts.astype(float))
            weights.loc[event_mask] *= event_factor
        diagnostics.append({"component": "event_balance", "affected_train_rows": int(event_mask.sum())})

    if strategy.use_substation_balance:
        group_counts = (
            df.loc[train_mask]
            .groupby(["manufacturer", "substation_id"])["substation_id"]
            .transform("count")
            .astype(float)
        )
        if not group_counts.empty:
            substation_factor = np.sqrt(float(group_counts.mean()) / group_counts)
            weights.loc[train_mask] *= substation_factor
        diagnostics.append({"component": "substation_balance", "affected_train_rows": int(train_mask.sum())})

    weights = normalized_train_weights(weights, train_mask, clip_hi=12.0 if strategy.resample else 10.0)
    diagnostics.append(
        {
            "component": "final_weight",
            "affected_train_rows": int(train_mask.sum()),
            "min": float(weights.loc[train_mask].min()),
            "mean": float(weights.loc[train_mask].mean()),
            "max": float(weights.loc[train_mask].max()),
        }
    )
    diag_df = pd.DataFrame(diagnostics)
    diag_df.insert(0, "split_strategy", split_column)
    diag_df.insert(1, "sampling_strategy", strategy.name)
    return weights, diag_df


def fit_candidate(
    candidate: object,
    train_x: pd.DataFrame,
    train_y: pd.Series,
    validation_x: pd.DataFrame,
    validation_y: pd.Series,
    sample_weight: pd.Series | None,
) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(**candidate.params)
    model.fit(
        train_x,
        train_y,
        sample_weight=sample_weight,
        eval_set=[(validation_x, validation_y)],
        eval_metric="l2",
        callbacks=[lgb.early_stopping(60, verbose=False), lgb.log_evaluation(0)],
    )
    return model


def train_strategy(
    df: pd.DataFrame,
    features: pd.DataFrame,
    split_column: str,
    strategy: SamplingStrategy,
) -> tuple[pd.DataFrame, lgb.LGBMRegressor, float, str, pd.Series, pd.DataFrame]:
    train_mask = df[split_column].eq("train")
    validation_mask = df[split_column].eq("validation")
    features_imputed, medians = impute_by_train(features, train_mask)
    weights, diagnostics = strategy_weights(df, split_column, strategy)
    y = df["target_score"].astype(float)
    seed_key = f"{split_column}|{strategy.name}".encode("utf-8")
    seed_offset = int(hashlib.sha256(seed_key).hexdigest()[:8], 16) % 100_000
    rng = np.random.default_rng(RANDOM_STATE + seed_offset)

    train_index = df.index[train_mask].to_numpy()
    if strategy.resample:
        probabilities = weights.loc[train_index].to_numpy(dtype=float)
        probabilities = probabilities / probabilities.sum()
        sample_size = int(round(len(train_index) * 1.75))
        sampled_index = rng.choice(train_index, size=sample_size, replace=True, p=probabilities)
        train_x = features_imputed.loc[sampled_index]
        train_y = y.loc[sampled_index]
        sample_weight = None
    else:
        train_x = features_imputed.loc[train_mask]
        train_y = y.loc[train_mask]
        sample_weight = weights.loc[train_mask]

    validation_x = features_imputed.loc[validation_mask]
    validation_y = y.loc[validation_mask]

    rows = []
    trained: dict[str, lgb.LGBMRegressor] = {}
    for candidate in candidate_grid():
        model = fit_candidate(candidate, train_x, train_y, validation_x, validation_y, sample_weight)
        score_col = f"{candidate.name}_score"
        validation_part = df.loc[validation_mask].copy()
        validation_part[score_col] = np.clip(model.predict(validation_x), 0, 100)
        threshold = best_action_threshold(validation_part, score_col)
        metric = metrics_for(validation_part, "validation", candidate.name, score_col, threshold)
        metric["split_strategy"] = split_column
        metric["sampling_strategy"] = strategy.name
        metric["selected_action_threshold"] = threshold
        metric["best_iteration"] = int(model.best_iteration_ or 0)
        metric["selection_score"] = validation_selection_score(metric)
        metric["train_rows_effective"] = int(len(train_x))
        rows.append(metric)
        trained[candidate.name] = model

    selection = pd.DataFrame(rows).sort_values(
        ["selection_score", "action_f1", "ndcg@R", "spearman"],
        ascending=[False, False, False, False],
    )
    best_name = str(selection.iloc[0]["model_key"])
    threshold = float(selection.iloc[0]["selected_action_threshold"])
    return selection, trained[best_name], threshold, best_name, medians, diagnostics


def evaluate_split(
    df: pd.DataFrame,
    features: pd.DataFrame,
    feature_mapping: pd.DataFrame,
    split_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object], pd.DataFrame]:
    holdout_mask = df[split_column].eq("holdout")
    holdout = df.loc[holdout_mask].copy()
    metric_rows = [
        metrics_for(holdout, f"{split_column}_holdout", "rule_base_raw_inference", "rule_priority_score", RULE_ACTION_THRESHOLD),
        metrics_for(holdout, f"{split_column}_holdout", "team_7feature_lgbm_raw", "team_lgbm_score", TEAM_ACTION_THRESHOLD),
    ]
    selection_rows = []
    importance_rows = []
    diagnostics_rows = []
    prediction_frame = df[KEY_COLUMNS + ["target_score", split_column]].copy()
    model_bundle: dict[str, object] = {}
    imputation_rows = []

    for strategy in STRATEGIES:
        selection, model, threshold, best_name, medians, diagnostics = train_strategy(df, features, split_column, strategy)
        selection_rows.append(selection)
        diagnostics_rows.append(diagnostics)

        train_mask = df[split_column].eq("train")
        features_imputed, _ = impute_by_train(features, train_mask)
        score_col = f"{strategy.name}_{split_column}_score"
        prediction = np.clip(model.predict(features_imputed), 0, 100)
        prediction_frame[score_col] = prediction
        scored = df.copy()
        scored[score_col] = prediction
        metric = metrics_for(scored.loc[holdout_mask].copy(), f"{split_column}_holdout", strategy.name, score_col, threshold)
        metric["split_strategy"] = split_column
        metric["sampling_strategy"] = strategy.name
        metric["selected_model_key"] = best_name
        metric_rows.append(metric)

        importance = feature_mapping.copy()
        importance["split_strategy"] = split_column
        importance["sampling_strategy"] = strategy.name
        importance["selected_model_key"] = best_name
        importance["importance"] = model.feature_importances_
        importance_rows.append(importance)

        model_bundle[strategy.name] = {
            "model": model,
            "selected_model_key": best_name,
            "action_threshold": threshold,
            "imputation_medians": medians,
        }
        imputation_rows.append(
            pd.DataFrame(
                {
                    "split_strategy": split_column,
                    "sampling_strategy": strategy.name,
                    "safe_feature": medians.index,
                    "median": medians.values,
                }
            )
        )

    metrics_df = pd.DataFrame(metric_rows)
    selection_df = pd.concat(selection_rows, ignore_index=True)
    importance_df = pd.concat(importance_rows, ignore_index=True)
    diagnostics_df = pd.concat(diagnostics_rows, ignore_index=True)
    imputation_df = pd.concat(imputation_rows, ignore_index=True)
    return metrics_df, selection_df, importance_df, diagnostics_df, model_bundle, prediction_frame, imputation_df


def split_winners(metrics_df: pd.DataFrame) -> pd.DataFrame:
    model_rows = metrics_df[~metrics_df["model_key"].isin(["rule_base_raw_inference", "team_7feature_lgbm_raw"])].copy()
    return (
        model_rows.sort_values(["split", "action_f1", "ndcg@R", "action_recall"], ascending=[True, False, False, False])
        .groupby("split")
        .head(3)
    )


def comparison_summary(metrics_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split_name, split_metrics in metrics_df.groupby("split"):
        rule = split_metrics[split_metrics["model_key"].eq("rule_base_raw_inference")].iloc[0]
        candidates = split_metrics[
            ~split_metrics["model_key"].isin(["rule_base_raw_inference", "team_7feature_lgbm_raw"])
        ].copy()
        best_f1 = candidates.sort_values(["action_f1", "ndcg@R"], ascending=[False, False]).iloc[0]
        best_ndcg = candidates.sort_values(["ndcg@R", "action_f1"], ascending=[False, False]).iloc[0]

        f1_delta = float(best_f1["action_f1"] - rule["action_f1"])
        ndcg_delta = float(best_f1["ndcg@R"] - rule["ndcg@R"])
        fp_delta = int(best_f1["fp"] - rule["fp"])
        fn_delta = int(best_f1["fn"] - rule["fn"])

        if f1_delta > 0 and ndcg_delta >= 0:
            verdict = "LGBM 개선"
        elif f1_delta > 0:
            verdict = "F1 개선, ranking 미달"
        else:
            verdict = "rule-base 우세"

        rows.append(
            {
                "split": split_name,
                "rule_f1": rule["action_f1"],
                "best_lgbm_f1_strategy": best_f1["model_key"],
                "best_lgbm_f1": best_f1["action_f1"],
                "f1_delta": f1_delta,
                "rule_ndcg@R": rule["ndcg@R"],
                "best_lgbm_ndcg@R": best_f1["ndcg@R"],
                "ndcg_delta": ndcg_delta,
                "fp_delta": fp_delta,
                "fn_delta": fn_delta,
                "best_lgbm_ndcg_strategy": best_ndcg["model_key"],
                "max_lgbm_ndcg@R": best_ndcg["ndcg@R"],
                "verdict": verdict,
            }
        )
    return pd.DataFrame(rows)


def write_report(
    df: pd.DataFrame,
    metrics_df: pd.DataFrame,
    selection_df: pd.DataFrame,
    importance_df: pd.DataFrame,
    diagnostics_df: pd.DataFrame,
) -> None:
    strategy_table = pd.DataFrame(
        [
            {"sampling_strategy": strategy.name, "description": strategy.description}
            for strategy in STRATEGIES
        ]
    )
    summary = comparison_summary(metrics_df)
    focus_columns = [
        "split",
        "model_key",
        "n",
        "mae",
        "spearman",
        "ndcg@R",
        "recall@100",
        "action_threshold",
        "action_precision",
        "action_recall",
        "action_f1",
        "fp",
        "fn",
    ]
    holdout_focus = metrics_df[focus_columns].sort_values(["split", "action_f1"], ascending=[True, False])
    top_lgbm = split_winners(metrics_df)[focus_columns]
    best_selection = (
        selection_df.sort_values(["split_strategy", "sampling_strategy", "selection_score"], ascending=[True, True, False])
        .groupby(["split_strategy", "sampling_strategy"])
        .head(1)
    )[
        [
            "split_strategy",
            "sampling_strategy",
            "model_key",
            "selection_score",
            "selected_action_threshold",
            "mae",
            "ndcg@R",
            "action_precision",
            "action_recall",
            "action_f1",
            "fp",
            "fn",
            "best_iteration",
        ]
    ]
    top_importance = (
        importance_df.sort_values(
            ["split_strategy", "sampling_strategy", "importance"],
            ascending=[True, True, False],
        )
        .groupby(["split_strategy", "sampling_strategy"])
        .head(8)[["split_strategy", "sampling_strategy", "original_feature", "importance"]]
    )
    weight_summary = diagnostics_df[diagnostics_df["component"].eq("final_weight")][
        ["split_strategy", "sampling_strategy", "min", "mean", "max"]
    ]

    lines = [
        "# 상황별 샘플링 LGBM Priority 실험",
        "",
        "## 목적",
        "",
        "룰베이스를 바로 대체할 수 있는지 보기 위해, 운영 추론 기준 데이터에서 상황별 train weighting/resampling을 적용한 LGBM priority head를 다시 실험했다.",
        "",
        "중요한 검증 원칙:",
        "",
        "- 샘플링/가중치는 train split에만 적용했다.",
        "- validation/holdout은 원분포 그대로 유지했다.",
        "- 모델과 action threshold는 validation에서만 선택했다.",
        "- holdout은 최종 비교에만 사용했다.",
        "- 룰베이스 점수/component/정답/식별자 계열은 feature에서 제외했다.",
        "",
        "## 데이터",
        "",
        f"- 입력: `report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv`",
        f"- rows: `{len(df)}`",
        "- leadtime 결측 누수 제거 기준: normal/pre_fault 모두 upstream leadtime 예측값 존재",
        "",
        "## 실험 전략",
        "",
        markdown_table(strategy_table, float_digits=4),
        "",
        "## 핵심 결과",
        "",
        markdown_table(summary, float_digits=4),
        "",
        "요약하면 샘플링/가중치로 `time`과 `regime` holdout의 action F1은 개선됐지만, `substation` holdout에서는 rule-base가 아직 더 안정적이다. 특히 새 설비 일반화 기준에서는 LGBM이 F1과 NDCG@R을 동시에 넘지 못했다.",
        "",
        "## Train Weight 요약",
        "",
        markdown_table(weight_summary, float_digits=4),
        "",
        "## Validation 선택 결과",
        "",
        markdown_table(best_selection, float_digits=4),
        "",
        "## Holdout 전체 비교",
        "",
        markdown_table(holdout_focus, float_digits=4),
        "",
        "## Split별 상위 LGBM 후보",
        "",
        markdown_table(top_lgbm, float_digits=4),
        "",
        "## 상위 Feature Importance",
        "",
        markdown_table(top_importance, float_digits=4),
        "",
        "## 판정 기준",
        "",
        "룰베이스보다 좋아졌다고 보려면 최소한 `split_substation_based_holdout`에서 F1과 NDCG@R을 동시에 넘거나, recall 개선을 위해 감수한 false positive 증가가 운영적으로 납득 가능해야 한다.",
        "",
        "## 산출물",
        "",
        f"- report: `report/priority_model_comparison/{OUTPUT_PREFIX}_report.md`",
        f"- metrics: `report/priority_model_comparison/{OUTPUT_PREFIX}_metrics.csv`",
        f"- selection: `report/priority_model_comparison/{OUTPUT_PREFIX}_selection.csv`",
        f"- feature importance: `report/priority_model_comparison/{OUTPUT_PREFIX}_feature_importance.csv`",
        f"- predictions: `report/priority_model_comparison/{OUTPUT_PREFIX}_predictions.csv`",
        f"- diagnostics: `report/priority_model_comparison/{OUTPUT_PREFIX}_weight_diagnostics.csv`",
        f"- models: `report/priority_model_comparison/models/{OUTPUT_PREFIX}.joblib`",
        "",
    ]
    (REPORT_DIR / f"{OUTPUT_PREFIX}_report.md").write_text("\n".join(lines), encoding="utf-8-sig")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = load_dataset()
    features, feature_mapping = build_feature_frame(df)

    all_metrics = []
    all_selection = []
    all_importance = []
    all_diagnostics = []
    all_predictions = []
    all_imputation = []
    model_bundle = {
        "input_basis": "report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv",
        "feature_mapping": feature_mapping,
        "strategies": [strategy.__dict__ for strategy in STRATEGIES],
        "models": {},
    }

    for split_column in SPLIT_COLUMNS:
        metrics, selection, importance, diagnostics, models, predictions, imputation = evaluate_split(
            df, features, feature_mapping, split_column
        )
        all_metrics.append(metrics)
        all_selection.append(selection)
        all_importance.append(importance)
        all_diagnostics.append(diagnostics)
        all_predictions.append(predictions)
        all_imputation.append(imputation)
        model_bundle["models"][split_column] = models

    metrics_df = pd.concat(all_metrics, ignore_index=True)
    selection_df = pd.concat(all_selection, ignore_index=True)
    importance_df = pd.concat(all_importance, ignore_index=True)
    diagnostics_df = pd.concat(all_diagnostics, ignore_index=True)
    imputation_df = pd.concat(all_imputation, ignore_index=True)
    predictions = all_predictions[0]
    for frame in all_predictions[1:]:
        extra_cols = [column for column in frame.columns if column not in predictions.columns]
        predictions = predictions.merge(frame[KEY_COLUMNS + extra_cols], on=KEY_COLUMNS, how="left", validate="one_to_one")

    metrics_df.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_metrics.csv", index=False, encoding="utf-8-sig")
    selection_df.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_selection.csv", index=False, encoding="utf-8-sig")
    importance_df.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_feature_importance.csv", index=False, encoding="utf-8-sig")
    diagnostics_df.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_weight_diagnostics.csv", index=False, encoding="utf-8-sig")
    imputation_df.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_imputation.csv", index=False, encoding="utf-8-sig")
    predictions.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_predictions.csv", index=False, encoding="utf-8-sig")
    feature_mapping.to_csv(REPORT_DIR / f"{OUTPUT_PREFIX}_features.csv", index=False, encoding="utf-8-sig")
    joblib.dump(model_bundle, MODEL_DIR / f"{OUTPUT_PREFIX}.joblib")
    write_report(df, metrics_df, selection_df, importance_df, diagnostics_df)

    print(REPORT_DIR / f"{OUTPUT_PREFIX}_report.md")
    print(REPORT_DIR / f"{OUTPUT_PREFIX}_metrics.csv")
    print(MODEL_DIR / f"{OUTPUT_PREFIX}.joblib")


if __name__ == "__main__":
    main()
