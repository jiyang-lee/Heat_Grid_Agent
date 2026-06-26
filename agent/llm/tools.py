"""LLM 에이전트 tool 5종 — 전부 파일 읽기/쓰기 기반(발송 없음).

- get_top_priority(n)
- get_substation_context(substation_id)
- get_sensor_evidence(substation_id, window_start, window_end)
- draft_work_order(...) -> docs/send/work_order_*.md 경로
- draft_email(...) -> docs/send/email_*.md 경로
"""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd
from langchain_core.tools import tool

from agent.io import paths
from agent.llm import prompts


@lru_cache(maxsize=1)
def _mock() -> pd.DataFrame:
    df = pd.read_csv(paths.MOCK_ML_OUTPUT)
    df["window_start"] = df["window_start"].astype(str)
    df["window_end"] = df["window_end"].astype(str)
    return df


def _priority() -> pd.DataFrame:
    df = pd.read_csv(paths.PRIORITY_SCORES_CSV)
    df["window_start"] = df["window_start"].astype(str)
    df["window_end"] = df["window_end"].astype(str)
    return df


def _join_keys(df: pd.DataFrame) -> pd.DataFrame:
    """priority_scores + mock(위험/리드타임/근거) 키 merge."""
    mock = _mock()
    keys = ["manufacturer", "substation_id", "window_start", "window_end"]
    cols = keys + [
        "risk_level_calibrated",
        "predicted_lead_time_bucket",
        "main_abnormal_sensors",
        "anomaly_score",
        "risk_probability",
    ]
    return df.merge(mock[cols], on=keys, how="left")


@tool
def get_top_priority(n: int = 5) -> str:
    """우선순위 점수 상위 n건을 JSON 문자열로 반환한다.

    각 항목: manufacturer, substation_id, window_start, window_end, priority_score,
    priority_level, risk_level_calibrated, predicted_lead_time_bucket.
    """
    df = _priority().sort_values("priority_score", ascending=False).head(int(n))
    df = _join_keys(df)
    records = df[
        [
            "manufacturer",
            "substation_id",
            "window_start",
            "window_end",
            "priority_score",
            "priority_level",
            "risk_level_calibrated",
            "predicted_lead_time_bucket",
        ]
    ].to_dict(orient="records")
    return json.dumps(records, ensure_ascii=False)


@tool
def get_substation_context(substation_id: int) -> str:
    """기계실 설비 구성 + 최근 이벤트 이력(가장 최근 윈도우 기준)을 JSON 으로 반환한다."""
    mock = _mock()
    sub = mock[mock["substation_id"] == int(substation_id)]
    if sub.empty:
        return json.dumps({"substation_id": int(substation_id), "found": False})
    row = sub.sort_values("window_start").iloc[-1]
    ctx = {
        "substation_id": int(substation_id),
        "found": True,
        "configuration_type": row["configuration_type"],
        "has_dhw": int(row["has_dhw"]),
        "has_buffer_tank": int(row["has_buffer_tank"]),
        "days_since_last_fault_event": float(row["days_since_last_fault_event"]),
        "days_since_last_task_event": float(row["days_since_last_task_event"]),
        "days_since_last_any_event": float(row["days_since_last_any_event"]),
    }
    return json.dumps(ctx, ensure_ascii=False)


@tool
def get_sensor_evidence(substation_id: int, window_start: str, window_end: str) -> str:
    """특정 윈도우의 주요 이상 센서/통계 근거를 JSON 으로 반환한다."""
    mock = _mock()
    sel = mock[
        (mock["substation_id"] == int(substation_id))
        & (mock["window_start"] == str(window_start))
        & (mock["window_end"] == str(window_end))
    ]
    if sel.empty:
        return json.dumps({"found": False})
    row = sel.iloc[0]
    sensors = str(row["main_abnormal_sensors"]) if pd.notna(row["main_abnormal_sensors"]) else ""
    ev = {
        "found": True,
        "anomaly_score": float(row["anomaly_score"]),
        "risk_score": float(row["risk_score"]),
        "risk_probability": float(row["risk_probability"]),
        "risk_level_calibrated": row["risk_level_calibrated"],
        "predicted_lead_time_bucket": row["predicted_lead_time_bucket"],
        "predicted_lead_time_confidence": float(row["predicted_lead_time_confidence"]),
        "main_abnormal_sensors": [s for s in sensors.split(";") if s],
    }
    return json.dumps(ev, ensure_ascii=False)


@tool
def draft_work_order(
    manufacturer: str,
    substation_id: int,
    window_start: str,
    window_end: str,
    findings: str,
) -> str:
    """점검 보고서 초안을 docs/send/work_order_*.md 로 저장하고 경로를 반환한다.

    findings 는 get_sensor_evidence/get_substation_context 결과를 합친 JSON 문자열을 권장.
    """
    data = _safe_json(findings)
    ev = data.get("evidence", data)
    ctx = data.get("context", {})
    pr = data.get("priority", {})

    sensors = ev.get("main_abnormal_sensors") or []
    evidence_md = _evidence_md(ev, sensors)
    context_md = _context_md(ctx)

    body = prompts.WORK_ORDER_TEMPLATE.format(
        substation_id=substation_id,
        manufacturer=manufacturer,
        window_start=window_start,
        window_end=window_end,
        priority_score=pr.get("priority_score", "NA"),
        priority_level=pr.get("priority_level", "NA"),
        risk_level=ev.get("risk_level_calibrated", "NA"),
        lead_time_bucket=ev.get("predicted_lead_time_bucket", "NA"),
        evidence=evidence_md,
        causes=prompts.DEFAULT_CAUSES,
        checklist=prompts.DEFAULT_CHECKLIST,
        context=context_md,
    )
    paths.ensure_dir(paths.DOCS_SEND_DIR)
    key = paths.make_key(manufacturer, substation_id, window_start)
    fpath = paths.DOCS_SEND_DIR / f"work_order_{key}.md"
    fpath.write_text(body, encoding="utf-8")
    return str(fpath.relative_to(paths.REPO_ROOT)).replace("\\", "/")


@tool
def draft_email(
    manufacturer: str,
    substation_id: int,
    window_start: str,
    window_end: str,
    work_order_path: str,
    priority_score: float = 0.0,
    priority_level: str = "NA",
    evidence_short: str = "",
) -> str:
    """작업자 메일 초안을 docs/send/email_*.md 로 저장하고 경로를 반환한다."""
    body = prompts.EMAIL_TEMPLATE.format(
        substation_id=substation_id,
        manufacturer=manufacturer,
        window_start=window_start,
        window_end=window_end,
        priority_score=priority_score,
        priority_level=priority_level,
        evidence_short=evidence_short or "주요 이상 센서 및 위험 점수 상승",
        work_order_path=work_order_path,
    )
    paths.ensure_dir(paths.DOCS_SEND_DIR)
    key = paths.make_key(manufacturer, substation_id, window_start)
    fpath = paths.DOCS_SEND_DIR / f"email_{key}.md"
    fpath.write_text(body, encoding="utf-8")
    return str(fpath.relative_to(paths.REPO_ROOT)).replace("\\", "/")


def _safe_json(s: str) -> dict:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {"evidence": v}
    except (json.JSONDecodeError, TypeError):
        return {"evidence": {"note": str(s)}}


def _evidence_md(ev: dict, sensors: list) -> str:
    lines = []
    if sensors:
        lines.append("- 주요 이상 센서: " + ", ".join(sensors))
    if "anomaly_score" in ev:
        lines.append(f"- anomaly_score: {ev['anomaly_score']:.2f}")
    if "risk_probability" in ev:
        lines.append(f"- risk_probability: {ev['risk_probability']:.2f} "
                     f"(level={ev.get('risk_level_calibrated', 'NA')})")
    if "predicted_lead_time_confidence" in ev:
        lines.append(f"- 리드타임 신뢰도: {ev['predicted_lead_time_confidence']:.2f} "
                     f"(bucket={ev.get('predicted_lead_time_bucket', 'NA')})")
    return "\n".join(lines) if lines else "- (근거 없음)"


def _context_md(ctx: dict) -> str:
    if not ctx:
        return "- (컨텍스트 없음)"
    return (
        f"- 구성: {ctx.get('configuration_type', 'NA')} "
        f"(DHW={ctx.get('has_dhw', 'NA')}, buffer_tank={ctx.get('has_buffer_tank', 'NA')})\n"
        f"- 최근 고장 이후: {ctx.get('days_since_last_fault_event', 'NA')}일, "
        f"최근 정비 이후: {ctx.get('days_since_last_task_event', 'NA')}일"
    )


ALL_TOOLS = [
    get_top_priority,
    get_substation_context,
    get_sensor_evidence,
    draft_work_order,
    draft_email,
]
