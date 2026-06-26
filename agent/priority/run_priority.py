"""추론: 모델 체인 output → priority 모델 predict → priority_scores.csv.

7피처 구성 → 모델 predict → clip(0,100) → 밴딩 → priority_scores.csv 적재.
출력은 priority_scores.schema.json 으로 자체 검증.
기본 입력은 raw/preprocessing fixture에서 생성한 IF+LGBM risk+LGBM leadtime 체인 출력이다.
목 데이터는 src를 명시했을 때만 보조 입력으로 사용할 수 있다.

실행: ``uv run python -m agent.priority.run_priority``
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator

from agent.io import paths
from agent.priority import contracts


def _adapt_aliases(df: pd.DataFrame) -> pd.DataFrame:
    for real, demo in contracts.ML_OUTPUT_COLUMN_ALIASES.items():
        if real in df.columns and demo not in df.columns:
            df = df.rename(columns={real: demo})
    return df


def _reason(row: pd.Series) -> str:
    return (
        f"risk={row.get('risk_level_calibrated', 'NA')}, "
        f"leadtime={row.get('predicted_lead_time_bucket', 'NA')}, "
        f"anomaly={float(row.get('anomaly_score', 0.0)):.2f}"
    )


def run(src: Path | None = None, dst: Path | None = None) -> pd.DataFrame:
    if not paths.PRIORITY_MODEL_PATH.exists():
        raise SystemExit("모델 없음 — 먼저 train_priority_model 실행")
    model = joblib.load(paths.PRIORITY_MODEL_PATH)

    source = src or paths.MODEL_CHAIN_OUTPUT_CSV
    if source == paths.MODEL_CHAIN_OUTPUT_CSV and not source.exists():
        from agent.model_chain.run_model_chain import run as run_model_chain

        run_model_chain(dst=source)

    df = pd.read_csv(source)
    df = _adapt_aliases(df)
    X = df[contracts.PRIORITY_FEATURES].astype(float)
    scores = np.clip(
        model.predict(X), contracts.PRIORITY_SCORE_MIN, contracts.PRIORITY_SCORE_MAX
    )
    levels = [contracts.priority_level_for(float(s)) for s in scores]
    now = datetime.now(timezone.utc).isoformat()

    out = pd.DataFrame(
        {
            "manufacturer": df["manufacturer"].astype(str),
            "substation_id": df["substation_id"].astype(int),
            "window_start": df["window_start"].astype(str),
            "window_end": df["window_end"].astype(str),
            "priority_score": np.round(scores, 2),
            "priority_level": levels,
            "priority_reason": [_reason(r) for _, r in df.iterrows()],
            "model_version": contracts.MODEL_VERSION,
            "created_at": now,
        },
        columns=contracts.PRIORITY_SCORES_COLUMNS,
    )
    out = out.sort_values("priority_score", ascending=False).reset_index(drop=True)

    dst = dst or paths.PRIORITY_SCORES_CSV
    paths.ensure_dir(dst.parent)
    out.to_csv(dst, index=False, encoding="utf-8")

    _validate_output(out)
    print(
        f"[run_priority] wrote {dst} rows={len(out)} "
        f"top={out['priority_score'].max():.1f} "
        f"levels={out['priority_level'].value_counts().to_dict()}"
    )
    return out


def _validate_output(out: pd.DataFrame) -> None:
    schema = json.loads(paths.PRIORITY_SCORES_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errs: list[str] = []
    for rec in out.head(25).to_dict(orient="records"):
        rec = {
            "manufacturer": str(rec["manufacturer"]),
            "substation_id": int(rec["substation_id"]),
            "window_start": str(rec["window_start"]),
            "window_end": str(rec["window_end"]),
            "priority_score": float(rec["priority_score"]),
            "priority_level": rec["priority_level"],
            "priority_reason": rec["priority_reason"],
            "model_version": str(rec["model_version"]),
            "created_at": str(rec["created_at"]),
        }
        errs += [e.message for e in validator.iter_errors(rec)]
    if errs:
        raise SystemExit(f"priority_scores 스키마 검증 실패: {errs[:3]}")
    print("[run_priority] priority_scores 스키마 검증 OK")


if __name__ == "__main__":
    run()
