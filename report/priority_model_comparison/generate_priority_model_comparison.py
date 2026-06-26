from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    r2_score,
)


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report" / "priority_model_comparison"

RULE_SCORE_PATH = ROOT / "data" / "processed" / "ml_priority" / "priority_engine_scores_tuned.csv"
WINDOWS_PATH = ROOT / "data" / "processed" / "ml_features" / "trainable_windows.csv"

MODEL_PATHS = {
    "lgbm_priority_only": ROOT
    / "lgbm_priority_model"
    / "heatgrid_priority_model_2026-06-26"
    / "model_handoff"
    / "heatgrid_priority_model_2026-06-26"
    / "priority"
    / "lightgbm_priority_model.joblib",
    "lgbm_prediction_bundle": ROOT
    / "lgbm_priority_model"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "model_handoff"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "priority"
    / "lightgbm_priority_model.joblib",
}

METADATA_PATHS = {
    "lgbm_priority_only": ROOT
    / "lgbm_priority_model"
    / "heatgrid_priority_model_2026-06-26"
    / "model_handoff"
    / "heatgrid_priority_model_2026-06-26"
    / "priority"
    / "priority_model_metadata.json",
    "lgbm_prediction_bundle": ROOT
    / "lgbm_priority_model"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "model_handoff"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "priority"
    / "priority_model_metadata.json",
}

OFFICIAL_MODEL_PATHS = {
    "anomaly_isolation_forest": ROOT
    / "model_handoff"
    / "heatgrid_ml_models_2026-06-25"
    / "anomaly"
    / "isolation_forest.joblib",
    "anomaly_standard_scaler": ROOT
    / "model_handoff"
    / "heatgrid_ml_models_2026-06-25"
    / "anomaly"
    / "standard_scaler.joblib",
    "risk_lgbm": ROOT
    / "model_handoff"
    / "heatgrid_ml_models_2026-06-25"
    / "risk"
    / "lightgbm_risk_model.joblib",
    "leadtime_lgbm": ROOT
    / "model_handoff"
    / "heatgrid_ml_models_2026-06-25"
    / "leadtime"
    / "lightgbm_leadtime_bucket_model_promoted.joblib",
}

BUNDLE_UPSTREAM_MODEL_PATHS = {
    "anomaly_isolation_forest": ROOT
    / "lgbm_priority_model"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "model_handoff"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "anomaly"
    / "isolation_forest.joblib",
    "anomaly_standard_scaler": ROOT
    / "lgbm_priority_model"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "model_handoff"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "anomaly"
    / "standard_scaler.joblib",
    "risk_lgbm": ROOT
    / "lgbm_priority_model"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "model_handoff"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "risk"
    / "lightgbm_risk_model.joblib",
    "leadtime_lgbm": ROOT
    / "lgbm_priority_model"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "model_handoff"
    / "heatgrid_prediction_priority_models_2026-06-26"
    / "leadtime"
    / "lightgbm_leadtime_bucket_model_promoted.joblib",
}

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
FEATURE_COLUMNS = [
    "anomaly_score",
    "risk_probability",
    "risk_score",
    "leadtime_prob_0-24h",
    "leadtime_prob_1-3d",
    "leadtime_prob_3-7d",
    "predicted_lead_time_confidence",
]
MODEL_LABELS = {
    "rule_based": "Rule-based v2_threshold48",
    "lgbm_priority_only": "LGBM priority-only package",
    "lgbm_prediction_bundle": "LGBM prediction+priority package",
}
PLOT_MODEL_LABELS = {
    "rule_based": "Rule-based",
    "lgbm_priority_only": "LGBM priority-only",
    "lgbm_prediction_bundle": "LGBM bundled",
}
LEVEL_ORDER = ["low", "medium", "high", "urgent"]
BUCKET_ORDER = ["normal", "3-7d", "1-3d", "0-24h"]
SPLIT_ORDER = ["all", "train", "validation", "holdout"]
FONT_FAMILY = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans CJK KR, Arial, sans-serif"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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


def target_level(bucket: str) -> str:
    return {"normal": "low", "3-7d": "medium", "1-3d": "high", "0-24h": "urgent"}[bucket]


def lgbm_level(score: float) -> str:
    if score >= 83.0:
        return "urgent"
    if score >= 49.5:
        return "high"
    if score >= 16.5:
        return "medium"
    return "low"


def rule_level(score: float) -> str:
    if score >= 70.0:
        return "urgent"
    if score >= 48.0:
        return "high"
    if score >= 34.0:
        return "medium"
    return "low"


def ndcg_at_k(relevance: np.ndarray, scores: np.ndarray, k: int) -> float:
    if len(relevance) == 0 or np.max(relevance) <= 0:
        return np.nan
    k = min(k, len(relevance))
    order = np.argsort(scores)[::-1][:k]
    ideal = np.argsort(relevance)[::-1][:k]
    gains = relevance[order]
    ideal_gains = relevance[ideal]
    discounts = 1.0 / np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(gains * discounts))
    idcg = float(np.sum(ideal_gains * discounts))
    return dcg / idcg if idcg > 0 else np.nan


def precision_recall_at_k(y_positive: np.ndarray, scores: np.ndarray, k: int) -> tuple[float, float]:
    k = min(k, len(y_positive))
    positives = int(y_positive.sum())
    if k == 0 or positives == 0:
        return np.nan, np.nan
    order = np.argsort(scores)[::-1][:k]
    hits = int(y_positive[order].sum())
    return hits / k, hits / positives


def safe_corr(a: pd.Series, b: pd.Series) -> tuple[float, float]:
    if a.nunique(dropna=True) <= 1 or b.nunique(dropna=True) <= 1:
        return np.nan, np.nan
    pearson = pearsonr(a, b).statistic
    spearman = spearmanr(a, b).statistic
    return float(pearson), float(spearman)


def load_comparison_dataset() -> tuple[pd.DataFrame, dict[str, dict]]:
    rule_df = pd.read_csv(RULE_SCORE_PATH)
    windows_columns = KEY_COLUMNS + [
        "label",
        "estimated_lead_time_hours",
        "split_time_based",
        "split_substation_based",
        "split_regime_based",
        "use_for_supervised_training",
        "fault_label",
        "fault_event_id",
    ]
    windows_df = pd.read_csv(WINDOWS_PATH, usecols=windows_columns)
    merged = rule_df.merge(
        windows_df.drop_duplicates(subset=KEY_COLUMNS),
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    if merged["label"].isna().any():
        missing = int(merged["label"].isna().sum())
        raise ValueError(f"label join failed for {missing} rows")

    merged["true_bucket"] = merged.apply(true_bucket, axis=1)
    merged["target_score"] = merged["true_bucket"].map(target_score).astype(float)
    merged["target_level"] = merged["true_bucket"].map(target_level)
    merged["is_pre_fault"] = merged["target_score"] > 0
    merged["is_within_3d"] = merged["target_score"] >= 66

    merged["rule_based_score"] = pd.to_numeric(merged["priority_score"], errors="coerce").clip(0, 100)
    merged["rule_based_level"] = merged["rule_based_score"].map(rule_level)

    metadata: dict[str, dict] = {}
    X = merged[FEATURE_COLUMNS].astype(float)
    for model_key, model_path in MODEL_PATHS.items():
        model = joblib.load(model_path)
        raw_pred = pd.Series(model.predict(X), index=merged.index)
        merged[f"{model_key}_score_raw"] = raw_pred
        merged[f"{model_key}_score"] = raw_pred.clip(0, 100)
        merged[f"{model_key}_level"] = merged[f"{model_key}_score"].map(lgbm_level)
        with METADATA_PATHS[model_key].open("r", encoding="utf-8") as f:
            metadata[model_key] = json.load(f)

    return merged, metadata


def make_model_file_summary(metadata: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for model_key, path in MODEL_PATHS.items():
        meta = metadata[model_key]
        rows.append(
            {
                "model_key": model_key,
                "label": MODEL_LABELS[model_key],
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "model_version": meta.get("model_version"),
                "model_type": meta.get("model_type"),
                "best_iteration": meta.get("best_iteration"),
                "feature_order": "|".join(meta.get("feature_order", [])),
                "training_basis": meta.get("training_basis"),
                "n_train_metadata": meta.get("n_train"),
                "n_holdout_metadata": meta.get("n_holdout"),
            }
        )
    return pd.DataFrame(rows)


def make_package_scope_summary(model_summary: pd.DataFrame) -> pd.DataFrame:
    priority_only_hash = model_summary.loc[
        model_summary["model_key"].eq("lgbm_priority_only"), "sha256"
    ].iloc[0]
    bundle_priority_hash = model_summary.loc[
        model_summary["model_key"].eq("lgbm_prediction_bundle"), "sha256"
    ].iloc[0]

    upstream_hash_matches = []
    for model_name, bundle_path in BUNDLE_UPSTREAM_MODEL_PATHS.items():
        official_path = OFFICIAL_MODEL_PATHS[model_name]
        upstream_hash_matches.append(
            {
                "upstream_model": model_name,
                "bundle_sha256": sha256(bundle_path),
                "official_sha256": sha256(official_path),
                "matches_official_model_handoff": sha256(bundle_path) == sha256(official_path),
            }
        )
    upstream_match_all = all(row["matches_official_model_handoff"] for row in upstream_hash_matches)

    rows = [
        {
            "package_key": "heatgrid_priority_model_2026-06-26",
            "package_role": "priority regression only",
            "contains_anomaly_model": False,
            "contains_risk_model": False,
            "contains_leadtime_model": False,
            "contains_priority_lgbm": True,
            "priority_lgbm_sha256": priority_only_hash,
            "priority_lgbm_same_as_other_package": priority_only_hash == bundle_priority_hash,
            "upstream_models_match_official_handoff": "not_applicable",
            "interpretation": "LGBM priority regressor만 포함한다. 입력 feature 7개는 외부 예측 체인에서 이미 만들어져 있어야 한다.",
        },
        {
            "package_key": "heatgrid_prediction_priority_models_2026-06-26",
            "package_role": "prediction chain plus priority regression",
            "contains_anomaly_model": True,
            "contains_risk_model": True,
            "contains_leadtime_model": True,
            "contains_priority_lgbm": True,
            "priority_lgbm_sha256": bundle_priority_hash,
            "priority_lgbm_same_as_other_package": priority_only_hash == bundle_priority_hash,
            "upstream_models_match_official_handoff": upstream_match_all,
            "interpretation": "anomaly/risk/leadtime 예측 모델과 같은 LGBM priority regressor를 함께 포함한다.",
        },
    ]
    package_summary = pd.DataFrame(rows)

    upstream_detail = pd.DataFrame(upstream_hash_matches)
    upstream_detail.to_csv(
        REPORT_DIR / "priority_lgbm_vs_rule_upstream_hash_check.csv",
        index=False,
        encoding="utf-8-sig",
    )
    return package_summary


def regression_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    models = ["rule_based", "lgbm_priority_only", "lgbm_prediction_bundle"]
    for split in SPLIT_ORDER:
        part = df if split == "all" else df[df["split_time_based"] == split]
        y = part["target_score"].astype(float)
        for model_key in models:
            pred = part[f"{model_key}_score"].astype(float)
            pearson, spearman = safe_corr(y, pred)
            rows.append(
                {
                    "split": split,
                    "model_key": model_key,
                    "model": MODEL_LABELS[model_key],
                    "n": int(len(part)),
                    "mae": mean_absolute_error(y, pred),
                    "rmse": math.sqrt(float(np.mean((y - pred) ** 2))),
                    "r2": r2_score(y, pred) if y.nunique() > 1 else np.nan,
                    "pearson": pearson,
                    "spearman": spearman,
                    "mean_prediction": float(pred.mean()),
                    "std_prediction": float(pred.std()),
                }
            )
    return pd.DataFrame(rows)


def classification_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    models = ["rule_based", "lgbm_priority_only", "lgbm_prediction_bundle"]
    for split in SPLIT_ORDER:
        part = df if split == "all" else df[df["split_time_based"] == split]
        y_level = part["target_level"]
        y_action = part["is_within_3d"].astype(bool)
        for model_key in models:
            pred_level = part[f"{model_key}_level"]
            pred_action = pred_level.isin(["high", "urgent"])
            tn, fp, fn, tp = confusion_matrix(y_action, pred_action, labels=[False, True]).ravel()
            precision = tp / (tp + fp) if tp + fp else np.nan
            recall = tp / (tp + fn) if tp + fn else np.nan
            specificity = tn / (tn + fp) if tn + fp else np.nan
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else np.nan
            rows.append(
                {
                    "split": split,
                    "model_key": model_key,
                    "model": MODEL_LABELS[model_key],
                    "n": int(len(part)),
                    "level_accuracy": accuracy_score(y_level, pred_level),
                    "level_macro_f1": f1_score(y_level, pred_level, labels=LEVEL_ORDER, average="macro"),
                    "action_definition": "predicted high/urgent vs true <=3d",
                    "tp": int(tp),
                    "fp": int(fp),
                    "fn": int(fn),
                    "tn": int(tn),
                    "action_precision": precision,
                    "action_recall": recall,
                    "action_specificity": specificity,
                    "action_f1": f1,
                    "action_rate": float(pred_action.mean()),
                }
            )
    return pd.DataFrame(rows)


def topk_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    models = ["rule_based", "lgbm_priority_only", "lgbm_prediction_bundle"]
    for split in SPLIT_ORDER:
        part = df if split == "all" else df[df["split_time_based"] == split]
        relevance_binary = part["is_pre_fault"].to_numpy(dtype=bool)
        relevance_graded = (part["target_score"] / 100.0).to_numpy(dtype=float)
        positives = int(relevance_binary.sum())
        k_values = [10, 20, 50, 100, positives]
        k_values = sorted({k for k in k_values if 0 < k <= len(part)})
        for model_key in models:
            scores = part[f"{model_key}_score"].to_numpy(dtype=float)
            for k in k_values:
                precision, recall = precision_recall_at_k(relevance_binary, scores, k)
                rows.append(
                    {
                        "split": split,
                        "model_key": model_key,
                        "model": MODEL_LABELS[model_key],
                        "k": int(k),
                        "k_label": "R" if k == positives else str(k),
                        "n": int(len(part)),
                        "pre_fault_count": positives,
                        "precision_pre_fault": precision,
                        "recall_pre_fault": recall,
                        "ndcg_graded": ndcg_at_k(relevance_graded, scores, k),
                    }
                )
    return pd.DataFrame(rows)


def confusion_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    models = ["rule_based", "lgbm_priority_only", "lgbm_prediction_bundle"]
    for split in SPLIT_ORDER:
        part = df if split == "all" else df[df["split_time_based"] == split]
        for model_key in models:
            ct = pd.crosstab(
                pd.Categorical(part["target_level"], categories=LEVEL_ORDER, ordered=True),
                pd.Categorical(part[f"{model_key}_level"], categories=LEVEL_ORDER, ordered=True),
                rownames=["actual"],
                colnames=["predicted"],
                dropna=False,
            )
            tables[f"{split}__{model_key}"] = ct
    return tables


def make_long_scores(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    models = ["rule_based", "lgbm_priority_only", "lgbm_prediction_bundle"]
    for model_key in models:
        part = df[
            KEY_COLUMNS
            + [
                "split_time_based",
                "true_bucket",
                "target_score",
                "target_level",
                "is_pre_fault",
                "is_within_3d",
                f"{model_key}_score",
                f"{model_key}_level",
            ]
        ].copy()
        part = part.rename(columns={f"{model_key}_score": "score", f"{model_key}_level": "predicted_level"})
        part["model_key"] = model_key
        part["model"] = MODEL_LABELS[model_key]
        part["plot_model"] = PLOT_MODEL_LABELS[model_key]
        records.append(part)
    return pd.concat(records, ignore_index=True)


def style_fig(fig: go.Figure, title: str | None = None) -> go.Figure:
    fig.update_layout(
        title=title,
        template="plotly_white",
        font=dict(family=FONT_FAMILY, size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=30, t=70, b=55),
    )
    return fig


def make_figures(
    df: pd.DataFrame,
    long_df: pd.DataFrame,
    reg_df: pd.DataFrame,
    cls_df: pd.DataFrame,
    topk_df: pd.DataFrame,
    metadata: dict[str, dict],
) -> list[tuple[str, go.Figure]]:
    figures: list[tuple[str, go.Figure]] = []

    score_fig = px.violin(
        long_df[long_df["model_key"].isin(["rule_based", "lgbm_priority_only"])],
        x="true_bucket",
        y="score",
        color="plot_model",
        category_orders={"true_bucket": BUCKET_ORDER},
        box=True,
        points=False,
        labels={"true_bucket": "실제 리드타임 버킷", "score": "우선순위 점수", "plot_model": "모델"},
    )
    figures.append(("01_score_distribution", style_fig(score_fig, "실제 버킷별 우선순위 점수 분포")))

    scatter_fig = px.scatter(
        df,
        x="rule_based_score",
        y="lgbm_priority_only_score",
        color="true_bucket",
        symbol="split_time_based",
        category_orders={"true_bucket": BUCKET_ORDER},
        opacity=0.72,
        hover_data=KEY_COLUMNS + ["target_score", "rule_based_level", "lgbm_priority_only_level"],
        labels={
            "rule_based_score": "Rule-based 점수",
            "lgbm_priority_only_score": "LGBM 점수",
            "true_bucket": "실제 버킷",
            "split_time_based": "split",
        },
    )
    scatter_fig.add_trace(
        go.Scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color="black", dash="dash"), name="y=x")
    )
    figures.append(("02_rule_vs_lgbm_scatter", style_fig(scatter_fig, "Rule-based와 LGBM 점수 관계")))

    metric_focus = reg_df[
        reg_df["model_key"].isin(["rule_based", "lgbm_priority_only"])
        & reg_df["split"].isin(["all", "holdout"])
    ].melt(
        id_vars=["split", "model"],
        value_vars=["mae", "rmse", "spearman"],
        var_name="metric",
        value_name="value",
    )
    metric_fig = px.bar(
        metric_focus,
        x="metric",
        y="value",
        color="model",
        facet_col="split",
        barmode="group",
        labels={"metric": "지표", "value": "값", "model": "모델"},
    )
    figures.append(("03_regression_metrics", style_fig(metric_fig, "회귀/순위 상관 지표 비교")))

    holdout_topk = topk_df[
        (topk_df["split"] == "holdout")
        & (topk_df["model_key"].isin(["rule_based", "lgbm_priority_only"]))
        & (topk_df["k_label"].isin(["10", "20", "50", "100", "R"]))
    ].copy()
    topk_fig = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=("Precision@K", "Recall@K", "Graded NDCG@K"),
    )
    for model_key, group in holdout_topk.groupby("model_key"):
        label = PLOT_MODEL_LABELS[model_key]
        x = group["k_label"].astype(str)
        topk_fig.add_trace(
            go.Scatter(x=x, y=group["precision_pre_fault"], mode="lines+markers", name=label),
            row=1,
            col=1,
        )
        topk_fig.add_trace(
            go.Scatter(x=x, y=group["recall_pre_fault"], mode="lines+markers", name=label, showlegend=False),
            row=1,
            col=2,
        )
        topk_fig.add_trace(
            go.Scatter(x=x, y=group["ndcg_graded"], mode="lines+markers", name=label, showlegend=False),
            row=1,
            col=3,
        )
    topk_fig.update_yaxes(range=[0, 1.03])
    figures.append(("04_holdout_topk", style_fig(topk_fig, "Holdout 기준 Top-K 포착 성능")))

    class_focus = cls_df[
        cls_df["model_key"].isin(["rule_based", "lgbm_priority_only"])
        & cls_df["split"].isin(["all", "holdout"])
    ].melt(
        id_vars=["split", "model"],
        value_vars=["action_precision", "action_recall", "action_f1", "action_specificity", "action_rate"],
        var_name="metric",
        value_name="value",
    )
    class_fig = px.bar(
        class_focus,
        x="metric",
        y="value",
        color="model",
        facet_col="split",
        barmode="group",
        labels={"metric": "지표", "value": "값", "model": "모델"},
    )
    class_fig.update_yaxes(range=[0, 1.03])
    figures.append(("05_action_metrics", style_fig(class_fig, "High/Urgent 운영 액션 지표")))

    level_counts = (
        long_df[long_df["model_key"].isin(["rule_based", "lgbm_priority_only"])]
        .groupby(["model", "predicted_level"], observed=False)
        .size()
        .reset_index(name="count")
    )
    level_counts["predicted_level"] = pd.Categorical(level_counts["predicted_level"], LEVEL_ORDER, ordered=True)
    level_fig = px.bar(
        level_counts.sort_values("predicted_level"),
        x="predicted_level",
        y="count",
        color="model",
        barmode="group",
        labels={"predicted_level": "예측 priority level", "count": "윈도우 수", "model": "모델"},
    )
    figures.append(("06_level_distribution", style_fig(level_fig, "예측 priority level 분포")))

    delta_df = df.copy()
    delta_df["lgbm_minus_rule"] = delta_df["lgbm_priority_only_score"] - delta_df["rule_based_score"]
    delta_fig = px.histogram(
        delta_df,
        x="lgbm_minus_rule",
        color="true_bucket",
        category_orders={"true_bucket": BUCKET_ORDER},
        nbins=60,
        marginal="box",
        labels={"lgbm_minus_rule": "LGBM 점수 - Rule-based 점수", "true_bucket": "실제 버킷"},
    )
    figures.append(("07_score_delta_distribution", style_fig(delta_fig, "LGBM과 Rule-based 점수 차이 분포")))

    curve_rows = []
    for split in ["all", "holdout"]:
        part = df if split == "all" else df[df["split_time_based"] == split]
        positives = max(int(part["is_pre_fault"].sum()), 1)
        for model_key in ["rule_based", "lgbm_priority_only"]:
            ordered = part.sort_values(f"{model_key}_score", ascending=False).reset_index(drop=True)
            ordered["rank"] = np.arange(1, len(ordered) + 1)
            ordered["capture_rate"] = ordered["is_pre_fault"].cumsum() / positives
            sampled = ordered.iloc[np.unique(np.linspace(0, len(ordered) - 1, min(200, len(ordered))).astype(int))]
            for _, row in sampled.iterrows():
                curve_rows.append(
                    {
                        "split": split,
                        "model": PLOT_MODEL_LABELS[model_key],
                        "rank_share": row["rank"] / len(ordered),
                        "capture_rate": row["capture_rate"],
                    }
                )
    curve_df = pd.DataFrame(curve_rows)
    curve_fig = px.line(
        curve_df,
        x="rank_share",
        y="capture_rate",
        color="model",
        facet_col="split",
        labels={"rank_share": "상위 점검 비율", "capture_rate": "pre_fault 누적 포착률", "model": "모델"},
    )
    curve_fig.update_yaxes(range=[0, 1.03])
    curve_fig.update_xaxes(tickformat=".0%")
    figures.append(("08_capture_curve", style_fig(curve_fig, "상위 점검 비율별 pre_fault 누적 포착 곡선")))

    fi = pd.DataFrame(metadata["lgbm_priority_only"]["feature_importance"])
    fi = fi.sort_values("importance", ascending=True)
    fi_fig = px.bar(
        fi,
        x="importance",
        y="feature",
        orientation="h",
        labels={"importance": "importance", "feature": "피처"},
    )
    figures.append(("09_feature_importance", style_fig(fi_fig, "LGBM priority 모델 피처 중요도")))

    return figures


def figure_html(figures: list[tuple[str, go.Figure]], summary_html: str) -> str:
    parts = [
        "<!doctype html>",
        "<html lang='ko'>",
        "<head><meta charset='utf-8'><title>Priority Model Comparison</title>",
        "<style>",
        "body{font-family:Malgun Gothic,Apple SD Gothic Neo,Noto Sans CJK KR,Arial,sans-serif;margin:28px;color:#1f2937;}",
        "h1{font-size:28px;margin-bottom:6px;} h2{font-size:20px;margin-top:34px;border-top:1px solid #e5e7eb;padding-top:20px;}",
        ".note{background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin:18px 0;}",
        "table{border-collapse:collapse;margin:10px 0 22px 0;font-size:13px;} th,td{border:1px solid #e5e7eb;padding:7px 9px;text-align:right;} th:first-child,td:first-child{text-align:left;} th{background:#f3f4f6;}",
        "</style></head><body>",
        "<h1>Priority 모델 비교 리포트</h1>",
        summary_html,
    ]
    for idx, (name, fig) in enumerate(figures):
        parts.append(f"<h2>{name}</h2>")
        parts.append(pio.to_html(fig, full_html=False, include_plotlyjs=True if idx == 0 else False))
    parts.append("</body></html>")
    return "\n".join(parts)


def markdown_table(df: pd.DataFrame, max_rows: int | None = None, float_digits: int = 4) -> str:
    part = df if max_rows is None else df.head(max_rows)
    if part.empty:
        return "_empty_"

    def format_cell(value: object) -> str:
        if pd.isna(value):
            text = ""
        elif isinstance(value, float):
            text = f"{value:.{float_digits}f}"
        else:
            text = str(value)
        return text.replace("|", "\\|").replace("\n", " ")

    columns = list(part.columns)
    rows = [[format_cell(row[col]) for col in columns] for _, row in part.iterrows()]
    widths = [
        max(len(str(col)), *(len(row[idx]) for row in rows))
        for idx, col in enumerate(columns)
    ]
    header = "| " + " | ".join(str(col).ljust(widths[idx]) for idx, col in enumerate(columns)) + " |"
    sep = "| " + " | ".join("-" * widths[idx] for idx in range(len(columns))) + " |"
    body = [
        "| " + " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(columns))) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def make_report_markdown(
    df: pd.DataFrame,
    model_summary: pd.DataFrame,
    package_summary: pd.DataFrame,
    reg_df: pd.DataFrame,
    cls_df: pd.DataFrame,
    topk_df: pd.DataFrame,
) -> str:
    n_rows = len(df)
    split_counts = df["split_time_based"].value_counts().reindex(["train", "validation", "holdout"]).fillna(0).astype(int)
    bucket_counts = df["true_bucket"].value_counts().reindex(BUCKET_ORDER).fillna(0).astype(int)
    duplicate_same = bool(
        model_summary.loc[model_summary["model_key"] == "lgbm_priority_only", "sha256"].iloc[0]
        == model_summary.loc[model_summary["model_key"] == "lgbm_prediction_bundle", "sha256"].iloc[0]
    )
    max_pred_diff = float((df["lgbm_priority_only_score"] - df["lgbm_prediction_bundle_score"]).abs().max())

    reg_focus = reg_df[
        reg_df["model_key"].isin(["rule_based", "lgbm_priority_only"])
        & reg_df["split"].isin(["all", "holdout"])
    ][["split", "model", "n", "mae", "rmse", "r2", "pearson", "spearman"]]
    cls_focus = cls_df[
        cls_df["model_key"].isin(["rule_based", "lgbm_priority_only"])
        & cls_df["split"].isin(["all", "holdout"])
    ][
        [
            "split",
            "model",
            "level_accuracy",
            "level_macro_f1",
            "action_precision",
            "action_recall",
            "action_f1",
            "action_specificity",
            "action_rate",
        ]
    ]
    topk_focus = topk_df[
        topk_df["model_key"].isin(["rule_based", "lgbm_priority_only"])
        & topk_df["split"].eq("holdout")
        & topk_df["k_label"].isin(["10", "20", "50", "100", "R"])
    ][
        [
            "split",
            "model",
            "k_label",
            "pre_fault_count",
            "precision_pre_fault",
            "recall_pre_fault",
            "ndcg_graded",
        ]
    ]

    holdout_reg = reg_focus[reg_focus["split"].eq("holdout")].set_index("model")
    holdout_cls = cls_focus[cls_focus["split"].eq("holdout")].set_index("model")
    rule_name = MODEL_LABELS["rule_based"]
    lgbm_name = MODEL_LABELS["lgbm_priority_only"]
    holdout_mae_gap = holdout_reg.loc[lgbm_name, "mae"] - holdout_reg.loc[rule_name, "mae"]
    all_reg = reg_focus[reg_focus["split"].eq("all")].set_index("model")
    all_mae_gain = all_reg.loc[rule_name, "mae"] - all_reg.loc[lgbm_name, "mae"]
    ndcg10 = topk_focus[(topk_focus["k_label"] == "10")].set_index("model")
    ndcg_delta = ndcg10.loc[lgbm_name, "ndcg_graded"] - ndcg10.loc[rule_name, "ndcg_graded"]
    holdout_rule_recall = holdout_cls.loc[rule_name, "action_recall"]
    holdout_lgbm_recall = holdout_cls.loc[lgbm_name, "action_recall"]
    holdout_rule_precision = holdout_cls.loc[rule_name, "action_precision"]
    holdout_lgbm_precision = holdout_cls.loc[lgbm_name, "action_precision"]

    lines = [
        "# Priority 모델 비교 리포트",
        "",
        "## 요약",
        "",
        f"- 비교 데이터는 현재 공식 룰베이스 산출물 `data/processed/ml_priority/priority_engine_scores_tuned.csv`를 기준으로 만들었다.",
        f"- 비교 행 수는 `{n_rows}`개이며 split 분포는 train `{split_counts['train']}`, validation `{split_counts['validation']}`, holdout `{split_counts['holdout']}`이다.",
        f"- 실제 버킷 분포는 normal `{bucket_counts['normal']}`, 3-7d `{bucket_counts['3-7d']}`, 1-3d `{bucket_counts['1-3d']}`, 0-24h `{bucket_counts['0-24h']}`이다.",
        f"- 팀원 산출물은 두 패키지가 맞다. 하나는 priority 회귀 단독 패키지이고, 다른 하나는 anomaly/risk/leadtime 예측 체인과 priority 회귀를 합친 통합 패키지다.",
        f"- 다만 두 패키지 안의 `lightgbm_priority_model.joblib`은 SHA256 기준 동일 파일이다: `{duplicate_same}`.",
        f"- 두 LGBM 패키지의 예측 점수 최대 절대 차이는 `{max_pred_diff:.6f}`이다.",
        f"- 전체 데이터 기준 MAE는 LGBM이 Rule-based보다 `{all_mae_gain:.4f}` 낮지만, holdout 기준 MAE는 LGBM이 `{holdout_mae_gap:.4f}` 더 높다.",
        f"- holdout Top-10 graded NDCG는 LGBM이 Rule-based 대비 `{ndcg_delta:.4f}` 낮다.",
        f"- holdout high/urgent 액션 기준 precision은 Rule-based `{holdout_rule_precision:.4f}`, LGBM `{holdout_lgbm_precision:.4f}`이고, recall은 Rule-based `{holdout_rule_recall:.4f}`, LGBM `{holdout_lgbm_recall:.4f}`이다.",
        "",
        "## 해석",
        "",
        "- LGBM priority 모델은 train 구간에서는 Rule-based보다 낮은 MAE/RMSE를 보이지만, validation과 holdout에서는 성능이 떨어진다. 현재 공식 데이터 기준으로는 일반화가 약한 후보로 보는 것이 맞다.",
        "- Rule-based는 risk level, risk probability, leadtime, anomaly, history adjustment를 사람이 해석 가능한 방식으로 더한 운영 엔진이다. holdout에서 회귀 지표, 순위 지표, high/urgent recall이 모두 LGBM보다 안정적이다.",
        "- LGBM은 high/urgent 판단을 더 보수적으로 한다. 전체 기준 precision과 specificity는 높지만, holdout recall이 크게 낮아 실제 3일 이내 장애 리드타임을 많이 놓친다.",
        "- 팀원 산출물은 패키지 기준으로 두 개가 맞다. `priority-only`는 LGBM 회귀만 넘기는 형태이고, `prediction+priority`는 anomaly/risk/leadtime 예측 모델까지 같이 넘기는 통합 형태다.",
        "- 하지만 두 패키지의 최종 priority 회귀 estimator는 같은 파일이다. 따라서 이 리포트의 Rule-based vs LGBM priority score 비교에서는 두 패키지 간 priority 결과 차이가 없다.",
        "- 통합 패키지에 들어 있는 anomaly/risk/leadtime 모델은 현재 `model_handoff/heatgrid_ml_models_2026-06-25`의 공식 모델과 SHA256 기준 동일하다. 즉 통합 패키지의 차별점은 upstream 모델 자체가 새롭다는 점이 아니라, 예측 체인을 함께 포장했다는 점이다.",
        "- LGBM 메타데이터에는 자체 평가에서 LGBM이 rule baseline을 이겼다고 기록되어 있지만, 현재 저장소에는 그 기준 파일인 `data/processed/ml_model_chain/model_chain_output.csv`가 없다. 이 리포트는 학습 재현이 아니라 현재 공식 룰베이스 산출물 위에서의 재스코어링 비교다.",
        "- 운영 채택 관점에서는 LGBM으로 교체하지 않는 것이 맞다. Rule-based `priority_engine_v2_threshold48`을 공식 유지하고, LGBM은 보수적 shadow score나 추가 검토용 ranking 후보로만 붙이는 것이 안전하다.",
        "",
        "## 패키지 구조 확인",
        "",
        markdown_table(
            package_summary[
                [
                    "package_key",
                    "package_role",
                    "contains_anomaly_model",
                    "contains_risk_model",
                    "contains_leadtime_model",
                    "contains_priority_lgbm",
                    "priority_lgbm_same_as_other_package",
                    "upstream_models_match_official_handoff",
                ]
            ],
            float_digits=0,
        ),
        "",
        "## Priority 회귀 파일 확인",
        "",
        markdown_table(
            model_summary[
                [
                    "model_key",
                    "model_version",
                    "model_type",
                    "best_iteration",
                    "n_train_metadata",
                    "n_holdout_metadata",
                    "sha256",
                ]
            ],
            float_digits=0,
        ),
        "",
        "## 회귀/상관 지표",
        "",
        markdown_table(reg_focus, float_digits=4),
        "",
        "## High/Urgent 운영 액션 지표",
        "",
        "`predicted high/urgent`를 `실제 3일 이내 장애 리드타임(0-24h 또는 1-3d)` 포착으로 평가했다.",
        "",
        markdown_table(cls_focus, float_digits=4),
        "",
        "## Holdout Top-K Ranking 지표",
        "",
        "`pre_fault` 전체를 relevant로 보고, NDCG는 normal=0, 3-7d=0.33, 1-3d=0.66, 0-24h=1.0의 graded relevance로 계산했다.",
        "",
        markdown_table(topk_focus, float_digits=4),
        "",
        "## 산출물",
        "",
        "- Plotly HTML: `report/priority_model_comparison/priority_lgbm_vs_rule_plotly.html`",
        "- 비교 데이터: `report/priority_model_comparison/priority_lgbm_vs_rule_dataset.csv`",
        "- 회귀 지표: `report/priority_model_comparison/priority_lgbm_vs_rule_regression_metrics.csv`",
        "- 운영 액션 지표: `report/priority_model_comparison/priority_lgbm_vs_rule_classification_metrics.csv`",
        "- Top-K 지표: `report/priority_model_comparison/priority_lgbm_vs_rule_topk_metrics.csv`",
        "",
    ]
    return "\n".join(lines)


def make_summary_html(markdown_report: str) -> str:
    lines = []
    in_list = False
    for line in markdown_report.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{line[2:]}</li>")
        elif line.strip() == "":
            if in_list:
                lines.append("</ul>")
                in_list = False
        elif line.startswith("|"):
            continue
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p>{line}</p>")
    if in_list:
        lines.append("</ul>")
    return "<div class='note'>" + "\n".join(lines[:36]) + "</div>"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df, metadata = load_comparison_dataset()
    model_summary = make_model_file_summary(metadata)
    package_summary = make_package_scope_summary(model_summary)
    reg_df = regression_metrics(df)
    cls_df = classification_metrics(df)
    topk_df = topk_metrics(df)
    confusions = confusion_tables(df)
    long_df = make_long_scores(df)
    figures = make_figures(df, long_df, reg_df, cls_df, topk_df, metadata)

    report_md = make_report_markdown(df, model_summary, package_summary, reg_df, cls_df, topk_df)
    html = figure_html(figures, make_summary_html(report_md))

    df.to_csv(REPORT_DIR / "priority_lgbm_vs_rule_dataset.csv", index=False, encoding="utf-8-sig")
    package_summary.to_csv(REPORT_DIR / "priority_lgbm_vs_rule_package_scope.csv", index=False, encoding="utf-8-sig")
    model_summary.to_csv(REPORT_DIR / "priority_lgbm_vs_rule_model_files.csv", index=False, encoding="utf-8-sig")
    reg_df.to_csv(REPORT_DIR / "priority_lgbm_vs_rule_regression_metrics.csv", index=False, encoding="utf-8-sig")
    cls_df.to_csv(REPORT_DIR / "priority_lgbm_vs_rule_classification_metrics.csv", index=False, encoding="utf-8-sig")
    topk_df.to_csv(REPORT_DIR / "priority_lgbm_vs_rule_topk_metrics.csv", index=False, encoding="utf-8-sig")
    for name, table in confusions.items():
        table.to_csv(REPORT_DIR / f"confusion_{name}.csv", encoding="utf-8-sig")
    (REPORT_DIR / "priority_lgbm_vs_rule_report.md").write_text(report_md, encoding="utf-8-sig")
    (REPORT_DIR / "priority_lgbm_vs_rule_plotly.html").write_text(html, encoding="utf-8")

    print(REPORT_DIR / "priority_lgbm_vs_rule_report.md")
    print(REPORT_DIR / "priority_lgbm_vs_rule_plotly.html")


if __name__ == "__main__":
    main()
