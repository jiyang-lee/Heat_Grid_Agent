from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "report" / "experiment_comparison"

FEATURE_DIR = DATA_DIR / "ml_features"
BASELINE_DIR = DATA_DIR / "ml_baseline"
RISK_DIR = DATA_DIR / "ml_risk"
LEADTIME_DIR = DATA_DIR / "ml_leadtime"

TRAINABLE_WINDOWS_PATH = FEATURE_DIR / "trainable_windows.csv"
IFOREST_METADATA_PATH = BASELINE_DIR / "models" / "baseline_model_metadata.json"
RISK_METADATA_PATH = RISK_DIR / "models" / "risk_model_metadata.json"
RISK_SCORES_PATH = RISK_DIR / "lgbm_risk_scores.csv"
RISK_CALIBRATED_PATH = RISK_DIR / "lgbm_risk_scores_calibrated.csv"
LEADTIME_METADATA_PATH = LEADTIME_DIR / "models" / "leadtime_bucket_model_promoted_metadata.json"
LEADTIME_SCORES_PATH = LEADTIME_DIR / "leadtime_bucket_scores_promoted.csv"

LEADTIME_PIPELINE_PATH = ROOT / "PREPROCESSING" / "osj" / "pipeline_scripts" / "06_leadtime_model.py"

OUTPUT_IFOREST_PATH = REPORT_DIR / "hyperparameter_tuning_iforest_metrics.csv"
OUTPUT_RISK_PATH = REPORT_DIR / "hyperparameter_tuning_risk_metrics.csv"
OUTPUT_LEADTIME_PATH = REPORT_DIR / "hyperparameter_tuning_leadtime_metrics.csv"
OUTPUT_SUMMARY_PATH = REPORT_DIR / "hyperparameter_tuning_summary.json"
OUTPUT_MD_PATH = REPORT_DIR / "06_hyperparameter_tuning_summary.md"

KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]
RANDOM_STATE = 42
PRIMARY_SPLIT_COLUMN = "split_event_regime_based"
BASE_RISK_THRESHOLDS = {"medium": 0.22, "high": 0.44, "critical": 0.90}
RISK_GROUP_OVERRIDES = {("manufacturer 2", "SH"): {"high": 0.78}}
LEADTIME_LABELS = ["0-24h", "1-3d", "3-7d"]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def false_positive_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    negatives = y_true.eq(0)
    if int(negatives.sum()) == 0:
        return float("nan")
    return float(((y_pred == 1) & negatives).sum() / negatives.sum())


def safe_roc_auc(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def safe_average_precision(y_true: pd.Series, y_score: pd.Series) -> float:
    if y_true.nunique() < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def binary_metrics(y_true: pd.Series, y_score: pd.Series, y_pred: pd.Series) -> dict:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    return {
        "roc_auc": safe_roc_auc(y_true, y_score),
        "average_precision": safe_average_precision(y_true, y_score),
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


def tune_iforest() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    metadata = json.loads(IFOREST_METADATA_PATH.read_text(encoding="utf-8"))
    features = [col for col in metadata["selected_feature_columns"] if col in df.columns]
    train_normal_mask = df["split_time_based"].eq("train") & df["label"].eq("normal")

    x_all = df[features].apply(pd.to_numeric, errors="coerce")
    medians = x_all.loc[train_normal_mask].median(numeric_only=True).fillna(0.0)
    x_all = x_all.fillna(medians).fillna(0.0)
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_all.loc[train_normal_mask])
    x_scaled = scaler.transform(x_all)

    param_grid = [
        {
            "n_estimators": n_estimators,
            "max_samples": max_samples,
            "max_features": max_features,
            "bootstrap": bootstrap,
            "threshold_quantile": quantile,
        }
        for n_estimators, max_samples, max_features, bootstrap, quantile in itertools.product(
            [300, 600],
            ["auto", 0.75, 1.0],
            [0.75, 1.0],
            [False, True],
            [0.90, 0.92, 0.95, 0.99],
        )
    ]

    rows: list[dict] = []
    score_cache: dict[tuple, np.ndarray] = {}
    for params in param_grid:
        model_key = (
            params["n_estimators"],
            params["max_samples"],
            params["max_features"],
            params["bootstrap"],
        )
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
            rows.append(
                {
                    "model": "isolation_forest",
                    "split": split,
                    "n_estimators": params["n_estimators"],
                    "max_samples": params["max_samples"],
                    "max_features": params["max_features"],
                    "bootstrap": params["bootstrap"],
                    "threshold_quantile": params["threshold_quantile"],
                    "threshold_value": threshold,
                    **binary_metrics(y_true, y_score, y_pred),
                }
            )

    metrics = pd.DataFrame(rows)
    validation = metrics[metrics["split"].eq("validation")].copy()
    best = validation.sort_values(["f1", "recall", "false_positive_rate"], ascending=[False, False, True]).iloc[0]
    best_holdout = metrics[
        metrics["split"].eq("holdout")
        & metrics["n_estimators"].eq(best["n_estimators"])
        & metrics["max_samples"].astype(str).eq(str(best["max_samples"]))
        & metrics["max_features"].eq(best["max_features"])
        & metrics["bootstrap"].eq(best["bootstrap"])
        & metrics["threshold_quantile"].eq(best["threshold_quantile"])
    ].iloc[0]
    baseline_holdout = metrics[
        metrics["split"].eq("holdout")
        & metrics["n_estimators"].eq(300)
        & metrics["max_samples"].astype(str).eq("auto")
        & metrics["max_features"].eq(1.0)
        & metrics["bootstrap"].eq(False)
        & metrics["threshold_quantile"].eq(0.99)
    ].iloc[0]
    summary = {
        "best_validation": best.to_dict(),
        "best_holdout": best_holdout.to_dict(),
        "baseline_holdout": baseline_holdout.to_dict(),
        "feature_count": len(features),
        "grid_size": len(param_grid),
    }
    return metrics, summary


def load_risk_frame() -> tuple[pd.DataFrame, list[str]]:
    trainable = pd.read_csv(TRAINABLE_WINDOWS_PATH)
    risk_scores = pd.read_csv(RISK_SCORES_PATH)
    metadata = json.loads(RISK_METADATA_PATH.read_text(encoding="utf-8"))
    features = [col for col in metadata["model_feature_columns"] if col in trainable.columns or col in risk_scores.columns]
    merge_columns = list(dict.fromkeys(KEY_COLUMNS + [
        "label",
        "configuration_type",
        PRIMARY_SPLIT_COLUMN,
        "anomaly_score",
        "days_since_last_fault_event",
        "days_since_last_task_event",
        "days_since_last_any_event",
    ]))
    merge_columns = [col for col in merge_columns if col in risk_scores.columns]
    df = trainable.merge(
        risk_scores[merge_columns].drop_duplicates(subset=KEY_COLUMNS),
        on=KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_risk"),
    )
    for base in ["label", "configuration_type", PRIMARY_SPLIT_COLUMN, "anomaly_score"]:
        risk_col = f"{base}_risk"
        if base in df.columns and risk_col in df.columns:
            df = df.drop(columns=[base]).rename(columns={risk_col: base})
        elif base not in df.columns and risk_col in df.columns:
            df = df.rename(columns={risk_col: base})
    if "use_for_supervised_training" in df.columns:
        df = df.loc[df["use_for_supervised_training"].fillna(True).astype(bool)].copy()
    for col in features:
        risk_col = f"{col}_risk"
        if col not in df.columns and risk_col in df.columns:
            df = df.rename(columns={risk_col: col})
    features = [col for col in features if col in df.columns]
    df["target"] = df["label"].eq("pre_fault").astype(int)
    return df, features


def make_numeric_frame(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    x = df[features].copy()
    for col in x.columns:
        if x[col].dtype == "bool":
            x[col] = x[col].astype("int8")
        elif x[col].dtype == "object":
            x[col] = pd.to_numeric(x[col], errors="coerce")
    return x.fillna(0.0)


def tune_risk() -> tuple[pd.DataFrame, dict]:
    df, features = load_risk_frame()
    x = make_numeric_frame(df, features)
    y = df["target"].astype(int)
    train_mask = df[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = df[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = df[PRIMARY_SPLIT_COLUMN].eq("holdout")

    param_grid = [
        {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "num_leaves": num_leaves,
            "max_depth": max_depth,
            "min_child_samples": min_child_samples,
            "subsample": subsample,
            "colsample_bytree": colsample,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "class_weight": class_weight,
        }
        for n_estimators, learning_rate, num_leaves, max_depth, min_child_samples, subsample, colsample, reg_alpha, reg_lambda, class_weight
        in itertools.product(
            [100, 150, 250],
            [0.03, 0.05],
            [7, 15, 31],
            [3, 4, -1],
            [30, 50],
            [0.8, 0.9],
            [0.8, 0.9],
            [0.1],
            [1.0],
            ["balanced"],
        )
    ]

    rows: list[dict] = []
    for idx, params in enumerate(param_grid, start=1):
        model = LGBMClassifier(
            objective="binary",
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
            **params,
        )
        model.fit(
            x.loc[train_mask],
            y.loc[train_mask],
            eval_set=[(x.loc[validation_mask], y.loc[validation_mask])],
            eval_metric="binary_logloss",
        )
        probabilities = model.predict_proba(x)[:, 1]
        score_col = f"risk_probability_candidate_{idx}"
        temp_columns = list(dict.fromkeys([*KEY_COLUMNS, "manufacturer", "configuration_type", "label", PRIMARY_SPLIT_COLUMN]))
        temp = df[temp_columns].copy()
        temp[score_col] = probabilities
        temp["candidate_level"] = temp.apply(lambda row: risk_level(row, score_col), axis=1)
        temp["candidate_positive"] = temp["candidate_level"].isin(["high", "critical"]).astype(int)

        for split, mask in {"validation": validation_mask, "holdout": holdout_mask}.items():
            y_true = y.loc[mask]
            y_score = temp.loc[mask, score_col]
            y_pred = temp.loc[mask, "candidate_positive"]
            rows.append(
                {
                    "model": "risk_lgbm",
                    "split": split,
                    "candidate_id": idx,
                    **params,
                    **binary_metrics(y_true, y_score, y_pred),
                }
            )

    metrics = pd.DataFrame(rows)
    validation = metrics[metrics["split"].eq("validation")].copy()
    best = validation.sort_values(["f1", "recall", "false_positive_rate", "average_precision"], ascending=[False, False, True, False]).iloc[0]
    best_holdout = metrics[metrics["split"].eq("holdout") & metrics["candidate_id"].eq(best["candidate_id"])].iloc[0]

    official = pd.read_csv(RISK_CALIBRATED_PATH)
    official_holdout = official[official[PRIMARY_SPLIT_COLUMN].eq("holdout")].copy()
    y_true = official_holdout["label"].eq("pre_fault").astype(int)
    y_pred = official_holdout["risk_level_calibrated"].isin(["high", "critical"]).astype(int)
    baseline_holdout = {
        "model": "risk_official_calibrated",
        "split": "holdout",
        **binary_metrics(y_true, official_holdout["risk_probability"], y_pred),
    }
    summary = {
        "best_validation": best.to_dict(),
        "best_holdout": best_holdout.to_dict(),
        "baseline_holdout": baseline_holdout,
        "feature_count": len(features),
        "grid_size": len(param_grid),
    }
    return metrics, summary


def tune_leadtime() -> tuple[pd.DataFrame, dict]:
    leadtime_module = load_module(LEADTIME_PIPELINE_PATH, "leadtime_pipeline_for_tuning")
    frame, base_features, _ = leadtime_module.load_base_frame()
    x = leadtime_module.make_numeric_frame(frame, base_features)
    x = leadtime_module.add_timeflow_features(frame, x)
    y = frame["lead_time_target"].astype(int)
    train_mask = frame[PRIMARY_SPLIT_COLUMN].eq("train")
    validation_mask = frame[PRIMARY_SPLIT_COLUMN].eq("validation")
    holdout_mask = frame[PRIMARY_SPLIT_COLUMN].eq("holdout")

    param_grid = [
        {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "num_leaves": num_leaves,
            "max_depth": max_depth,
            "min_child_samples": min_child_samples,
            "subsample": subsample,
            "colsample_bytree": colsample,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "class_weight": class_weight,
        }
        for n_estimators, learning_rate, num_leaves, max_depth, min_child_samples, subsample, colsample, reg_alpha, reg_lambda, class_weight
        in itertools.product(
            [150, 200, 300],
            [0.03, 0.05],
            [7, 15, 31],
            [3, 4, -1],
            [10, 20, 30],
            [0.8, 0.9],
            [0.8, 0.9],
            [0.1],
            [1.0],
            ["balanced"],
        )
    ]

    rows: list[dict] = []
    for idx, params in enumerate(param_grid, start=1):
        model = LGBMClassifier(
            objective="multiclass",
            num_class=len(LEADTIME_LABELS),
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
            **params,
        )
        model.fit(
            x.loc[train_mask],
            y.loc[train_mask],
            eval_set=[(x.loc[validation_mask], y.loc[validation_mask])],
            eval_metric="multi_logloss",
        )
        probs = model.predict_proba(x)
        pred = probs.argmax(axis=1)
        for split, mask in {"validation": validation_mask, "holdout": holdout_mask}.items():
            y_true = y.loc[mask]
            y_pred = pd.Series(pred[mask.to_numpy()], index=y_true.index)
            split_probs = probs[mask.to_numpy()]
            top2 = leadtime_module.top2_accuracy(split_probs, y_true)
            rows.append(
                {
                    "model": "leadtime_lgbm",
                    "split": split,
                    "candidate_id": idx,
                    **params,
                    "row_count": int(len(y_true)),
                    "accuracy": float(accuracy_score(y_true, y_pred)),
                    "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
                    "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
                    "top2_accuracy": float(top2),
                    "bucket_distance_mae": float((y_true - y_pred).abs().mean()),
                }
            )

    metrics = pd.DataFrame(rows)
    validation = metrics[metrics["split"].eq("validation")].copy()
    best = validation.sort_values(["macro_f1", "accuracy", "bucket_distance_mae"], ascending=[False, False, True]).iloc[0]
    best_holdout = metrics[metrics["split"].eq("holdout") & metrics["candidate_id"].eq(best["candidate_id"])].iloc[0]

    official = pd.read_csv(LEADTIME_SCORES_PATH)
    official_holdout = official[official[PRIMARY_SPLIT_COLUMN].eq("holdout")].copy()
    y_true = official_holdout["lead_time_target"].astype(int)
    y_pred = official_holdout["predicted_lead_time_index"].astype(int)
    baseline_holdout = {
        "model": "leadtime_official_promoted",
        "split": "holdout",
        "row_count": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "top2_accuracy": float(leadtime_module.top2_accuracy(
            official_holdout[[f"leadtime_prob_{label}" for label in LEADTIME_LABELS]].to_numpy(),
            y_true,
        )),
        "bucket_distance_mae": float((y_true - y_pred).abs().mean()),
    }
    summary = {
        "best_validation": best.to_dict(),
        "best_holdout": best_holdout.to_dict(),
        "baseline_holdout": baseline_holdout,
        "feature_count": int(x.shape[1]),
        "grid_size": len(param_grid),
    }
    return metrics, summary


def make_markdown(summary: dict) -> str:
    lines = [
        "# 06 Hyperparameter Tuning Summary",
        "",
        "## 실험 원칙",
        "",
        "- train split으로만 학습했다.",
        "- validation split으로 하이퍼파라미터를 선택했다.",
        "- holdout split은 최종 비교에만 사용했다.",
        "- 기존 공식 산출물은 덮어쓰지 않았다.",
        "",
    ]

    iforest = summary["isolation_forest"]
    risk = summary["risk_lgbm"]
    lead = summary["leadtime_lgbm"]

    lines.extend(
        [
            "## Isolation Forest",
            "",
            f"- grid size: `{iforest['grid_size']}`",
            f"- feature count: `{iforest['feature_count']}`",
            f"- 공식 holdout F1/Recall/FPR: `{iforest['baseline_holdout']['f1']:.4f}` / `{iforest['baseline_holdout']['recall']:.4f}` / `{iforest['baseline_holdout']['false_positive_rate']:.4f}`",
            f"- 튜닝 holdout F1/Recall/FPR: `{iforest['best_holdout']['f1']:.4f}` / `{iforest['best_holdout']['recall']:.4f}` / `{iforest['best_holdout']['false_positive_rate']:.4f}`",
            f"- 선택 파라미터: n_estimators `{iforest['best_validation']['n_estimators']}`, max_samples `{iforest['best_validation']['max_samples']}`, max_features `{iforest['best_validation']['max_features']}`, bootstrap `{iforest['best_validation']['bootstrap']}`, q `{iforest['best_validation']['threshold_quantile']}`",
            "",
            "## Risk LightGBM",
            "",
            f"- grid size: `{risk['grid_size']}`",
            f"- feature count: `{risk['feature_count']}`",
            f"- 공식 holdout F1/Recall/FPR/ROC-AUC: `{risk['baseline_holdout']['f1']:.4f}` / `{risk['baseline_holdout']['recall']:.4f}` / `{risk['baseline_holdout']['false_positive_rate']:.4f}` / `{risk['baseline_holdout']['roc_auc']:.4f}`",
            f"- 튜닝 holdout F1/Recall/FPR/ROC-AUC: `{risk['best_holdout']['f1']:.4f}` / `{risk['best_holdout']['recall']:.4f}` / `{risk['best_holdout']['false_positive_rate']:.4f}` / `{risk['best_holdout']['roc_auc']:.4f}`",
            f"- 선택 candidate_id: `{risk['best_validation']['candidate_id']}`",
            "",
            "## Leadtime LightGBM",
            "",
            f"- grid size: `{lead['grid_size']}`",
            f"- feature count: `{lead['feature_count']}`",
            f"- 공식 holdout accuracy/macro_f1/top2: `{lead['baseline_holdout']['accuracy']:.4f}` / `{lead['baseline_holdout']['macro_f1']:.4f}` / `{lead['baseline_holdout']['top2_accuracy']:.4f}`",
            f"- 튜닝 holdout accuracy/macro_f1/top2: `{lead['best_holdout']['accuracy']:.4f}` / `{lead['best_holdout']['macro_f1']:.4f}` / `{lead['best_holdout']['top2_accuracy']:.4f}`",
            f"- 선택 candidate_id: `{lead['best_validation']['candidate_id']}`",
            "",
            "## 결론",
            "",
        ]
    )

    conclusions: list[str] = []
    if risk["best_holdout"]["f1"] > risk["baseline_holdout"]["f1"]:
        conclusions.append("- Risk LightGBM은 튜닝 후보가 공식 holdout F1을 개선했다. 단 FPR 변화까지 같이 검토해야 한다.")
    else:
        conclusions.append("- Risk LightGBM은 튜닝 후보가 공식 모델을 명확히 넘지 못했다.")
    if lead["best_holdout"]["macro_f1"] > lead["baseline_holdout"]["macro_f1"]:
        conclusions.append("- Leadtime LightGBM은 튜닝 후보가 macro F1을 개선했다.")
    else:
        conclusions.append("- Leadtime LightGBM은 튜닝 후보가 공식 모델을 명확히 넘지 못했다.")
    if iforest["best_holdout"]["f1"] > iforest["baseline_holdout"]["f1"]:
        conclusions.append("- Isolation Forest는 threshold/parameter 튜닝으로 anomaly label 민감도 개선 여지가 있다.")
    else:
        conclusions.append("- Isolation Forest는 튜닝 후보가 공식 기준을 명확히 넘지 못했다.")
    lines.extend(conclusions)
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    iforest_metrics, iforest_summary = tune_iforest()
    iforest_metrics.to_csv(OUTPUT_IFOREST_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_IFOREST_PATH)

    risk_metrics, risk_summary = tune_risk()
    risk_metrics.to_csv(OUTPUT_RISK_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_RISK_PATH)

    leadtime_metrics, leadtime_summary = tune_leadtime()
    leadtime_metrics.to_csv(OUTPUT_LEADTIME_PATH, index=False, encoding="utf-8-sig")
    print(OUTPUT_LEADTIME_PATH)

    summary = {
        "isolation_forest": iforest_summary,
        "risk_lgbm": risk_summary,
        "leadtime_lgbm": leadtime_summary,
    }
    OUTPUT_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    OUTPUT_MD_PATH.write_text(make_markdown(summary), encoding="utf-8-sig")
    print(OUTPUT_SUMMARY_PATH)
    print(OUTPUT_MD_PATH)
    print()
    print(make_markdown(summary))


if __name__ == "__main__":
    main()
