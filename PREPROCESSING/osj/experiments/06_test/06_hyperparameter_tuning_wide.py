from __future__ import annotations

import importlib.util
import itertools
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = ROOT / "report" / "experiment_comparison"
BASE_TUNING_PATH = ROOT / "PREPROCESSING" / "osj" / "experiments" / "06_test" / "06_hyperparameter_tuning_all.py"
LEADTIME_SCORES_PATH = ROOT / "data" / "processed" / "ml_leadtime" / "leadtime_bucket_scores_promoted.csv"

OUTPUT_IFOREST_PATH = REPORT_DIR / "hyperparameter_tuning_wide_iforest_metrics.csv"
OUTPUT_RISK_PATH = REPORT_DIR / "hyperparameter_tuning_wide_risk_metrics.csv"
OUTPUT_LEADTIME_PATH = REPORT_DIR / "hyperparameter_tuning_wide_leadtime_metrics.csv"
OUTPUT_CONFUSION_PATH = REPORT_DIR / "leadtime_bucket_confusion_official_vs_tuned.csv"
OUTPUT_SUMMARY_PATH = REPORT_DIR / "hyperparameter_tuning_wide_summary.json"
OUTPUT_MD_PATH = REPORT_DIR / "06_hyperparameter_tuning_wide_summary.md"

RANDOM_STATE = 42
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
LEADTIME_LABELS = ["0-24h", "1-3d", "3-7d"]
BASE_RISK_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
RISK_GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_module(BASE_TUNING_PATH, "base_hyperparameter_tuning")


def sample_grid(grid: dict[str, list], sample_size: int) -> list[dict]:
    keys = list(grid)
    all_params = [dict(zip(keys, values)) for values in itertools.product(*(grid[key] for key in keys))]
    rng = random.Random(RANDOM_STATE)
    if len(all_params) <= sample_size:
        return all_params
    return rng.sample(all_params, sample_size)


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def binary_metrics(y_true: pd.Series, y_score: pd.Series, y_pred: pd.Series) -> dict:
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "roc_auc": float(roc_auc_score(y_true, y_score)) if y_true.nunique() > 1 else float("nan"),
        "average_precision": float(average_precision_score(y_true, y_score)) if y_true.nunique() > 1 else float("nan"),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": false_positive_rate(y_true, y_pred),
        "predicted_positive_count": int(y_pred.sum()),
        "true_positive_count": int(((y_pred == 1) & y_true.eq(1)).sum()),
        "false_positive_count": int(((y_pred == 1) & y_true.eq(0)).sum()),
        "positive_count": int(y_true.sum()),
        "row_count": int(len(y_true)),
    }


def risk_level(row: pd.Series, score_col: str) -> str:
    medium = BASE_RISK_THRESHOLDS["medium"]
    high = BASE_RISK_THRESHOLDS["high"]
    critical = BASE_RISK_THRESHOLDS["critical"]
    override = RISK_GROUP_OVERRIDES.get((row.get("manufacturer"), row.get("configuration_type")))
    if override:
        high = override.get("high", high)
        critical = max(critical, high)
    score = float(row[score_col])
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def tune_iforest_wide() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(BASE.TRAINABLE_WINDOWS_PATH)
    metadata = json.loads(BASE.IFOREST_METADATA_PATH.read_text(encoding="utf-8"))
    features = [col for col in metadata["selected_feature_columns"] if col in df.columns]
    train_normal_mask = df["split_time_based"].eq("train") & df["label"].eq("normal")
    x_all = df[features].apply(pd.to_numeric, errors="coerce")
    medians = x_all.loc[train_normal_mask].median(numeric_only=True).fillna(0.0)
    x_all = x_all.fillna(medians).fillna(0.0)
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_all.loc[train_normal_mask])
    x_scaled = scaler.transform(x_all)

    grid = {
        "n_estimators": [200, 300, 500, 800],
        "max_samples": ["auto", 0.5, 0.65, 0.8, 1.0],
        "max_features": [0.5, 0.65, 0.75, 0.9, 1.0],
        "bootstrap": [False, True],
        "threshold_quantile": [0.85, 0.88, 0.90, 0.92, 0.95, 0.98, 0.99],
    }
    params_list = sample_grid(grid, 220)
    rows: list[dict] = []
    score_cache: dict[tuple, np.ndarray] = {}
    for idx, params in enumerate(params_list, start=1):
        model_key = (params["n_estimators"], params["max_samples"], params["max_features"], params["bootstrap"])
        if model_key not in score_cache:
            model = IsolationForest(
                n_estimators=params["n_estimators"],
                contamination="auto",
                max_samples=params["max_samples"],
                max_features=params["max_features"],
                bootstrap=params["bootstrap"],
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
            model.fit(x_train)
            score_cache[model_key] = -model.score_samples(x_scaled)
        scores = score_cache[model_key]
        threshold = float(np.quantile(scores[train_normal_mask.to_numpy()], params["threshold_quantile"]))
        for split in ["validation", "holdout"]:
            mask = df["split_time_based"].eq(split)
            y_true = df.loc[mask, "label"].eq("pre_fault").astype(int)
            y_score = pd.Series(scores[mask.to_numpy()], index=df.index[mask])
            y_pred = (y_score >= threshold).astype(int)
            rows.append({"candidate_id": idx, "split": split, **params, "threshold_value": threshold, **binary_metrics(y_true, y_score, y_pred)})

    metrics = pd.DataFrame(rows)
    best_val = metrics[metrics["split"].eq("validation")].sort_values(["f1", "recall", "false_positive_rate"], ascending=[False, False, True]).iloc[0]
    best_hold = metrics[(metrics["split"].eq("holdout")) & (metrics["candidate_id"].eq(best_val["candidate_id"]))].iloc[0]
    summary = {"grid_sample_size": len(params_list), "best_validation": best_val.to_dict(), "best_holdout": best_hold.to_dict()}
    return metrics, summary


def tune_risk_wide() -> tuple[pd.DataFrame, dict]:
    df, features = BASE.load_risk_frame()
    x = BASE.make_numeric_frame(df, features)
    y = df["target"].astype(int)
    train_mask = df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = df[PRIMARY_SPLIT_COLUMN].eq("holdout")

    grid = {
        "n_estimators": [80, 120, 180, 260, 400],
        "learning_rate": [0.015, 0.025, 0.04, 0.06, 0.08],
        "num_leaves": [5, 7, 11, 15, 31, 63],
        "max_depth": [2, 3, 4, 5, -1],
        "min_child_samples": [20, 40, 60, 90, 120],
        "subsample": [0.65, 0.8, 0.95, 1.0],
        "colsample_bytree": [0.65, 0.8, 0.95, 1.0],
        "reg_alpha": [0.0, 0.1, 0.5, 1.0],
        "reg_lambda": [0.5, 1.0, 2.0, 5.0],
        "class_weight": ["balanced", None],
    }
    params_list = sample_grid(grid, 320)
    rows: list[dict] = []
    temp_columns = list(dict.fromkeys([*BASE.KEY_COLUMNS, "manufacturer", "configuration_type", "label", PRIMARY_SPLIT_COLUMN]))
    for idx, params in enumerate(params_list, start=1):
        model = LGBMClassifier(objective="binary", random_state=RANDOM_STATE, n_jobs=-1, verbosity=-1, **params)
        model.fit(x.loc[train_mask], y.loc[train_mask], eval_set=[(x.loc[validation_mask], y.loc[validation_mask])], eval_metric="binary_logloss")
        probabilities = model.predict_proba(x)[:, 1]
        score_col = "candidate_score"
        temp = df[temp_columns].copy()
        temp[score_col] = probabilities
        temp["candidate_level"] = temp.apply(lambda row: risk_level(row, score_col), axis=1)
        temp["candidate_positive"] = temp["candidate_level"].isin(["high", "critical"]).astype(int)
        for split, mask in {"validation": validation_mask, "holdout": holdout_mask}.items():
            rows.append({"candidate_id": idx, "split": split, **params, **binary_metrics(y.loc[mask], temp.loc[mask, score_col], temp.loc[mask, "candidate_positive"])})

    metrics = pd.DataFrame(rows)
    best_val = metrics[metrics["split"].eq("validation")].sort_values(["f1", "false_positive_rate", "average_precision"], ascending=[False, True, False]).iloc[0]
    best_hold = metrics[(metrics["split"].eq("holdout")) & (metrics["candidate_id"].eq(best_val["candidate_id"]))].iloc[0]
    best_hold_oracle = metrics[metrics["split"].eq("holdout")].sort_values(["f1", "false_positive_rate"], ascending=[False, True]).iloc[0]
    summary = {"grid_sample_size": len(params_list), "best_validation": best_val.to_dict(), "best_holdout": best_hold.to_dict(), "best_holdout_oracle": best_hold_oracle.to_dict()}
    return metrics, summary


def top2_accuracy(probabilities: np.ndarray, y_true: pd.Series) -> float:
    top2 = probabilities.argsort(axis=1)[:, -2:]
    truth = y_true.to_numpy().reshape(-1, 1)
    return float((top2 == truth).any(axis=1).mean())


def tune_leadtime_wide() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    leadtime_module = load_module(BASE.LEADTIME_PIPELINE_PATH, "leadtime_pipeline_for_wide_tuning")
    frame, base_features, _ = leadtime_module.load_base_frame()
    x = leadtime_module.make_numeric_frame(frame, base_features)
    x = leadtime_module.add_timeflow_features(frame, x)
    y = frame["lead_time_target"].astype(int)
    train_mask = frame[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = frame[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = frame[PRIMARY_SPLIT_COLUMN].eq("holdout")

    grid = {
        "n_estimators": [120, 180, 240, 320, 450],
        "learning_rate": [0.015, 0.025, 0.04, 0.06],
        "num_leaves": [7, 15, 31, 63],
        "max_depth": [3, 4, 5, -1],
        "min_child_samples": [5, 10, 20, 30, 45],
        "subsample": [0.7, 0.85, 1.0],
        "colsample_bytree": [0.7, 0.85, 1.0],
        "reg_alpha": [0.0, 0.1, 0.5],
        "reg_lambda": [0.5, 1.0, 2.0, 5.0],
        "class_weight": ["balanced", None],
    }
    params_list = sample_grid(grid, 320)
    rows: list[dict] = []
    holdout_predictions: dict[int, np.ndarray] = {}
    for idx, params in enumerate(params_list, start=1):
        model = LGBMClassifier(objective="multiclass", num_class=len(LEADTIME_LABELS), random_state=RANDOM_STATE, n_jobs=-1, verbosity=-1, **params)
        model.fit(x.loc[train_mask], y.loc[train_mask], eval_set=[(x.loc[validation_mask], y.loc[validation_mask])], eval_metric="multi_logloss")
        probs = model.predict_proba(x)
        pred = probs.argmax(axis=1)
        holdout_predictions[idx] = pred[holdout_mask.to_numpy()]
        for split, mask in {"validation": validation_mask, "holdout": holdout_mask}.items():
            y_true = y.loc[mask]
            y_pred = pd.Series(pred[mask.to_numpy()], index=y_true.index)
            rows.append(
                {
                    "candidate_id": idx,
                    "split": split,
                    **params,
                    "row_count": int(len(y_true)),
                    "accuracy": float(accuracy_score(y_true, y_pred)),
                    "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
                    "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
                    "top2_accuracy": top2_accuracy(probs[mask.to_numpy()], y_true),
                    "bucket_distance_mae": float((y_true - y_pred).abs().mean()),
                }
            )

    metrics = pd.DataFrame(rows)
    best_val = metrics[metrics["split"].eq("validation")].sort_values(["macro_f1", "accuracy", "bucket_distance_mae"], ascending=[False, False, True]).iloc[0]
    best_hold = metrics[(metrics["split"].eq("holdout")) & (metrics["candidate_id"].eq(best_val["candidate_id"]))].iloc[0]
    best_hold_oracle = metrics[metrics["split"].eq("holdout")].sort_values(["macro_f1", "accuracy"], ascending=[False, False]).iloc[0]

    official = pd.read_csv(LEADTIME_SCORES_PATH)
    official_hold = official[official[PRIMARY_SPLIT_COLUMN].eq("holdout")].copy()
    y_hold = official_hold["lead_time_target"].astype(int)
    official_pred = official_hold["predicted_lead_time_index"].astype(int).to_numpy()
    tuned_pred = holdout_predictions[int(best_val["candidate_id"])]
    confusion_rows = []
    for name, pred in [("official_promoted", official_pred), ("wide_tuned_validation_selected", tuned_pred)]:
        matrix = confusion_matrix(y_hold, pred, labels=list(range(len(LEADTIME_LABELS))))
        for true_idx, true_label in enumerate(LEADTIME_LABELS):
            for pred_idx, pred_label in enumerate(LEADTIME_LABELS):
                confusion_rows.append({"variant": name, "actual_bucket": true_label, "predicted_bucket": pred_label, "count": int(matrix[true_idx, pred_idx])})
    confusion_df = pd.DataFrame(confusion_rows)
    summary = {"grid_sample_size": len(params_list), "best_validation": best_val.to_dict(), "best_holdout": best_hold.to_dict(), "best_holdout_oracle": best_hold_oracle.to_dict()}
    return metrics, confusion_df, summary


def make_markdown(summary: dict) -> str:
    lead = summary["leadtime_lgbm_wide"]
    risk = summary["risk_lgbm_wide"]
    iso = summary["isolation_forest_wide"]
    lines = [
        "# 06 Hyperparameter Tuning Wide Summary",
        "",
        "## 실험 원칙",
        "",
        "- train split으로만 학습했다.",
        "- validation split으로 하이퍼파라미터를 선택했다.",
        "- holdout split은 최종 비교에만 사용했다.",
        "- 넓은 범위는 전체 exhaustive grid가 아니라 고정 seed random search로 수행했다.",
        "",
        "## Isolation Forest Wide",
        "",
        f"- sample size: `{iso['grid_sample_size']}`",
        f"- validation 선택 holdout F1/Recall/FPR: `{iso['best_holdout']['f1']:.4f}` / `{iso['best_holdout']['recall']:.4f}` / `{iso['best_holdout']['false_positive_rate']:.4f}`",
        "",
        "## Risk LightGBM Wide",
        "",
        f"- sample size: `{risk['grid_sample_size']}`",
        f"- validation 선택 holdout F1/Recall/FPR/ROC-AUC: `{risk['best_holdout']['f1']:.4f}` / `{risk['best_holdout']['recall']:.4f}` / `{risk['best_holdout']['false_positive_rate']:.4f}` / `{risk['best_holdout']['roc_auc']:.4f}`",
        f"- holdout oracle 최고 F1: `{risk['best_holdout_oracle']['f1']:.4f}`",
        "",
        "## Leadtime LightGBM Wide",
        "",
        f"- sample size: `{lead['grid_sample_size']}`",
        f"- validation 선택 holdout accuracy/macro_f1/top2: `{lead['best_holdout']['accuracy']:.4f}` / `{lead['best_holdout']['macro_f1']:.4f}` / `{lead['best_holdout']['top2_accuracy']:.4f}`",
        f"- holdout oracle 최고 macro_f1: `{lead['best_holdout_oracle']['macro_f1']:.4f}`",
        "",
        "## 결론",
        "",
        "- Risk는 넓은 튜닝에서도 validation 선택 후보가 holdout 일반화를 안정적으로 개선하는지 확인해야 한다.",
        "- Leadtime은 bucket별 confusion과 함께 승격 여부를 판단한다.",
        "- Isolation Forest는 민감도 개선과 오탐 증가 trade-off가 핵심이다.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    iforest_metrics, iforest_summary = tune_iforest_wide()
    iforest_metrics.to_csv(OUTPUT_IFOREST_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_IFOREST_PATH)

    risk_metrics, risk_summary = tune_risk_wide()
    risk_metrics.to_csv(OUTPUT_RISK_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_RISK_PATH)

    lead_metrics, lead_confusion, lead_summary = tune_leadtime_wide()
    lead_metrics.to_csv(OUTPUT_LEADTIME_PATH, index=False, encoding="utf-8-sig")
    lead_confusion.to_csv(OUTPUT_CONFUSION_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_LEADTIME_PATH)
    print(OUTPUT_CONFUSION_PATH)

    summary = {
        "isolation_forest_wide": iforest_summary,
        "risk_lgbm_wide": risk_summary,
        "leadtime_lgbm_wide": lead_summary,
    }
    OUTPUT_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    OUTPUT_MD_PATH.write_text(make_markdown(summary), encoding="utf-8-sig")
    print(OUTPUT_SUMMARY_PATH)
    print(OUTPUT_MD_PATH)
    print()
    print(make_markdown(summary))
    print(lead_confusion.to_string(index=False))


if __name__ == "__main__":
    main()
