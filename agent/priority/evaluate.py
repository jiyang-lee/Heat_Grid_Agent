"""legacy priority LGBM 평가: precision@k / recall@k / NDCG@k.

정답집합 R = holdout 중 target>0(실제 pre_fault). priority_score 내림차순 단일 랭킹.
현재 proto runtime은 priority LGBM을 채택하지 않고 rule engine
`priority_engine_v2_rule_based_tuned`를 직접 사용한다. 이 파일은 과거 LGBM과 rule
engine의 비교 기록을 재현할 때만 사용한다.

실행: ``uv run python -m agent.priority.evaluate`` (저장된 모델 로드 후 비교 출력)
"""

from __future__ import annotations

import math

import joblib
import numpy as np
import pandas as pd

from agent.io import paths
from agent.priority import build_dataset, contracts, rule_baseline


def _rank_desc(scores: np.ndarray) -> np.ndarray:
    # 점수 내림차순. 동점은 안정 정렬.
    return np.argsort(-scores, kind="stable")


def ranking_metrics(scores: np.ndarray, targets: np.ndarray, ks=(10, 20)) -> dict:
    order = _rank_desc(scores)
    rel = (targets[order] > 0).astype(float)         # binary relevance
    graded = targets[order] / 100.0                  # graded relevance
    R = int((targets > 0).sum())
    k_set = list(ks) + [R]
    out = {}
    for k in k_set:
        if k <= 0:
            continue
        kk = min(k, len(order))
        hit = rel[:kk].sum()
        precision = hit / kk
        recall = hit / R if R else 0.0
        # NDCG@k
        dcg = sum(graded[i] / math.log2(i + 2) for i in range(kk))
        ideal = np.sort(graded)[::-1]
        idcg = sum(ideal[i] / math.log2(i + 2) for i in range(min(kk, len(ideal))))
        ndcg = (dcg / idcg) if idcg > 0 else 0.0
        out[f"k={k}"] = {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "ndcg": round(float(ndcg), 4),
        }
    out["R"] = R
    return out


def model_scores(model, df: pd.DataFrame) -> np.ndarray:
    X = build_dataset.feature_matrix(df)
    return np.clip(model.predict(X), contracts.PRIORITY_SCORE_MIN, contracts.PRIORITY_SCORE_MAX)


def evaluate_holdout(model, hold_df: pd.DataFrame) -> dict:
    """모델 vs rule baseline 평가. 모델 metrics 반환(+채택 판정)."""
    targets = hold_df["target"].to_numpy(dtype=float)
    m_scores = model_scores(model, hold_df)
    r_scores = rule_baseline.score_frame(hold_df).to_numpy(dtype=float)

    m = ranking_metrics(m_scores, targets)
    r = ranking_metrics(r_scores, targets)

    _print_table(m, r)
    verdict = _verdict(m, r)
    print(f"-> 판정: {verdict}")
    return {"model": m, "rule_baseline": r, "verdict": verdict}


def _print_table(m: dict, r: dict) -> None:
    print(f"=== Priority 모델 vs rule v2 (동일 holdout, R={m['R']}) ===")
    print(f"{'metric':<16}{'priority_v3':>14}{'rule_v2':>12}")
    for key in m:
        if key == "R":
            continue
        for metric in ("precision", "recall", "ndcg"):
            label = f"{metric}@{key.split('=')[1]}"
            mv = m[key][metric]
            rv = r[key][metric]
            print(f"{label:<16}{mv:>14}{rv:>12}")


def _verdict(m: dict, r: dict) -> str:
    # 핵심 지표(precision@10, ndcg@10 또는 R 기준)에서 모델이 baseline 이상이면 채택
    keys = [k for k in m if k != "R"]
    wins = ties = losses = 0
    for k in keys:
        for metric in ("precision", "recall", "ndcg"):
            mv, rv = m[k][metric], r[k][metric]
            if mv > rv + 1e-9:
                wins += 1
            elif abs(mv - rv) <= 1e-9:
                ties += 1
            else:
                losses += 1
    if wins >= losses:
        return f"priority 모델 채택 (wins={wins}, ties={ties}, losses={losses}; baseline 동등 이상)"
    return f"priority 모델 보류 (wins={wins}, ties={ties}, losses={losses}; baseline 미달)"


def main() -> int:
    if not paths.PRIORITY_MODEL_PATH.exists():
        print(f"모델 없음: {paths.PRIORITY_MODEL_PATH} (먼저 train_priority_model 실행)")
        return 1
    model = joblib.load(paths.PRIORITY_MODEL_PATH)
    df = build_dataset.build_dataset()
    hold_df = df[df["split"] == "holdout"].reset_index(drop=True)
    evaluate_holdout(model, hold_df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
