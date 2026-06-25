"""학습셋 구성: 목 데이터(ML output 레벨) → priority 라벨 + 7피처 + holdout split.

라벨(A): label+lead_time_bucket → 0/33/66/100.
holdout: substation 기반(일부 substation을 평가용으로 분리) — event/substation 일반화 평가 근사.
leakage guard: 데모 목 데이터는 전 구간 과거이므로 별도 컷 없음(실데이터 전환 시 window_end<=report_date 적용).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agent.io import paths
from agent.priority import contracts

# substation_id % 3 == 0 → holdout (결정적 분리)
HOLDOUT_MOD = 3


def _adapt_aliases(df: pd.DataFrame) -> pd.DataFrame:
    for real, demo in contracts.ML_OUTPUT_COLUMN_ALIASES.items():
        if real in df.columns and demo not in df.columns:
            df = df.rename(columns={real: demo})
    return df


def build_dataset(path: Path | None = None) -> pd.DataFrame:
    src = path or paths.MOCK_ML_OUTPUT
    df = pd.read_csv(src)
    df = _adapt_aliases(df)
    df["lead_time_bucket"] = df["lead_time_bucket"].fillna("").astype(str)
    df["label"] = df["label"].astype(str)
    df["target"] = [
        contracts.priority_label_for(lbl, bkt or None)
        for lbl, bkt in zip(df["label"], df["lead_time_bucket"])
    ]
    df["split"] = np.where(
        df["substation_id"] % HOLDOUT_MOD == 0, "holdout", "train"
    )
    return df


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    return df[contracts.PRIORITY_FEATURES].astype(float)


if __name__ == "__main__":
    d = build_dataset()
    print(d["split"].value_counts().to_dict())
    print(d.groupby("split")["target"].apply(lambda s: (s > 0).sum()).to_dict())
