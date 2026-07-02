"""FastAPI 서버 — 파일 읽어 제공(발송 엔드포인트 없음).

- GET /priority           : 우선순위 목록
- GET /priority/{key}      : 단건 상세(점수 + ML 근거)
- GET /agent/output/{key}  : 보고서/메일 초안 md 원문

key = "{substation_id}_{window_start_slug}" (docs/send 파일명 규칙과 동일).
실행: ``uv run uvicorn server.main:app --port 8000``
"""

from __future__ import annotations

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.io import paths

app = FastAPI(title="HeatGrid Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

KEYS = ["manufacturer", "substation_id", "window_start", "window_end"]
CTX_COLS = [
    "risk_level_calibrated",
    "predicted_lead_time_bucket",
    "predicted_lead_time_confidence",
    "anomaly_score",
    "risk_probability",
    "risk_score",
    "main_abnormal_sensors",
    "configuration_type",
    "has_dhw",
    "has_buffer_tank",
    "days_since_last_fault_event",
    "days_since_last_task_event",
]


def _load() -> pd.DataFrame:
    if not paths.PRIORITY_SCORES_CSV.exists():
        raise HTTPException(503, "priority_scores.csv 없음 — run_priority 먼저 실행")
    pr = pd.read_csv(paths.PRIORITY_SCORES_CSV)
    pr["window_start"] = pr["window_start"].astype(str)
    pr["window_end"] = pr["window_end"].astype(str)
    ml_output_path = paths.MODEL_CHAIN_OUTPUT_CSV if paths.MODEL_CHAIN_OUTPUT_CSV.exists() else paths.MOCK_ML_OUTPUT
    if ml_output_path.exists():
        ml = pd.read_csv(ml_output_path)
        ml["window_start"] = ml["window_start"].astype(str)
        ml["window_end"] = ml["window_end"].astype(str)
        cols = KEYS + [c for c in CTX_COLS if c in ml.columns]
        pr = pr.merge(ml[cols], on=KEYS, how="left")
    pr["key"] = [
        paths.make_key(m, s, w)
        for m, s, w in zip(pr["manufacturer"], pr["substation_id"], pr["window_start"])
    ]
    return pr.astype(object).where(pd.notna(pr), None)


@app.get("/")
def health():
    return {"status": "ok", "service": "heatgrid-agent"}


@app.get("/priority")
def list_priority(limit: int = 50):
    df = _load().sort_values("priority_score", ascending=False).head(limit)
    return df.to_dict(orient="records")


@app.get("/priority/{key}")
def priority_detail(key: str):
    df = _load()
    row = df[df["key"] == key]
    if row.empty:
        raise HTTPException(404, f"key 없음: {key}")
    return row.iloc[0].to_dict()


@app.get("/agent/output/{key}")
def agent_output(key: str):
    parts = key.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(400, "key 형식 오류")
    wo = paths.DOCS_SEND_DIR / f"work_order_{key}.md"
    email = paths.DOCS_SEND_DIR / f"email_{key}.md"
    if not wo.exists() and not email.exists():
        raise HTTPException(404, f"초안 없음: {key} (run_agent 먼저 실행)")
    return {
        "key": key,
        "work_order_md": wo.read_text(encoding="utf-8") if wo.exists() else None,
        "email_md": email.read_text(encoding="utf-8") if email.exists() else None,
    }
