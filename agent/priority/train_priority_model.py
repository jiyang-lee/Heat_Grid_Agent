"""legacy priority LGBM 학습 스크립트.

모델 체인 output → 라벨(0/33/66/100) → 얕은 트리·강한 정규화·early stopping →
event/substation holdout 평가(evaluate, rule v2 대비) → joblib + metadata 저장.

현재 proto runtime은 이 모델을 사용하지 않고 `priority_engine_v2_rule_based_tuned`
규칙 엔진으로 priority_scores.csv를 생성한다. 이 스크립트는 과거 LGBM 실험 재현용이다.

실행: ``uv run python -m agent.priority.train_priority_model``
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import numpy as np

from agent.io import paths
from agent.priority import build_dataset, contracts, evaluate


def train() -> dict:
    if not paths.MODEL_CHAIN_OUTPUT_CSV.exists():
        from agent.model_chain.run_model_chain import run as run_model_chain

        run_model_chain(dst=paths.MODEL_CHAIN_OUTPUT_CSV)

    df = build_dataset.build_dataset()
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    hold_df = df[df["split"] == "holdout"].reset_index(drop=True)

    X = build_dataset.feature_matrix(train_df)
    y = train_df["target"].astype(float)

    # train 내부 train/val 분리 (early stopping용)
    rng = np.random.default_rng(42)
    idx = np.arange(len(train_df))
    rng.shuffle(idx)
    n_val = max(20, int(len(idx) * 0.2))
    val_idx, tr_idx = idx[:n_val], idx[n_val:]

    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=500,
        learning_rate=0.05,
        max_depth=3,
        num_leaves=7,
        min_child_samples=25,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.9,
        reg_alpha=1.0,
        reg_lambda=2.0,
        random_state=42,
        n_jobs=1,
        verbose=-1,
    )
    model.fit(
        X.iloc[tr_idx],
        y.iloc[tr_idx],
        eval_set=[(X.iloc[val_idx], y.iloc[val_idx])],
        eval_metric="l2",
        callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)],
    )

    print(f"[train] n_train={len(tr_idx)} n_val={len(val_idx)} "
          f"best_iter={model.best_iteration_}")
    metrics = evaluate.evaluate_holdout(model, hold_df)

    paths.ensure_dir(paths.MODELS_DIR)
    joblib.dump(model, paths.PRIORITY_MODEL_PATH)
    feature_importance = [
        {"feature": feature, "importance": int(importance)}
        for feature, importance in zip(contracts.PRIORITY_FEATURES, model.feature_importances_)
    ]
    meta = {
        "model_version": contracts.MODEL_VERSION,
        "model_type": "LGBMRegressor",
        "feature_order": contracts.PRIORITY_FEATURES,
        "label_mapping": {"normal": 0, "3-7d": 33, "1-3d": 66, "0-24h": 100},
        "training_basis": str(paths.MODEL_CHAIN_OUTPUT_CSV.relative_to(paths.REPO_ROOT)).replace("\\", "/"),
        "n_train": int(len(train_df)),
        "n_holdout": int(len(hold_df)),
        "target_distribution": {
            "train": {str(k): int(v) for k, v in train_df["target"].value_counts().sort_index().items()},
            "holdout": {str(k): int(v) for k, v in hold_df["target"].value_counts().sort_index().items()},
        },
        "best_iteration": int(model.best_iteration_ or 0),
        "feature_importance": sorted(feature_importance, key=lambda row: row["importance"], reverse=True),
        "metrics": metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    paths.PRIORITY_MODEL_META.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[train] saved model -> {paths.PRIORITY_MODEL_PATH}")
    print(f"[train] saved meta  -> {paths.PRIORITY_MODEL_META}")
    return meta


if __name__ == "__main__":
    train()
