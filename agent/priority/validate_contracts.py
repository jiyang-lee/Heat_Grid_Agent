"""계약 검증: jsonschema 메타검증 + pglast DDL 파싱 + 목 데이터 컬럼 정합.

실행: ``uv run python -m agent.priority.validate_contracts``
실패 시 비정상 종료(exit!=0). 단계마다 호출하는 게이트.
"""

from __future__ import annotations

import json
import sys

import pandas as pd
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pglast import parse_sql
from pglast.parser import ParseError

from agent.io import paths
from agent.priority import contracts


def _check_json_schemas() -> list[str]:
    errors: list[str] = []
    for path in sorted(paths.SCHEMA_JSON_DIR.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            print(f"[jsonschema] OK  {path.name}")
        except (SchemaError, json.JSONDecodeError) as exc:
            errors.append(f"[jsonschema] FAIL {path.name}: {exc}")
    return errors


def _check_sql_ddls() -> list[str]:
    errors: list[str] = []
    for path in sorted(paths.SCHEMA_SQL_DIR.glob("*.sql")):
        try:
            parse_sql(path.read_text(encoding="utf-8"))
            print(f"[pglast]     OK  {path.name}")
        except ParseError as exc:
            errors.append(f"[pglast]     FAIL {path.name}: {exc}")
    return errors


def _check_priority_scores_schema_usable() -> list[str]:
    """priority_scores 스키마로 샘플 1행을 실제 검증 가능한지 확인."""
    schema = json.loads(paths.PRIORITY_SCORES_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    sample = {
        "manufacturer": "manufacturer_1",
        "substation_id": 12,
        "window_start": "2026-06-20T00:00:00",
        "window_end": "2026-06-20T06:00:00",
        "priority_score": 87.4,
        "priority_level": "urgent",
        "priority_reason": "high risk + 0-24h imminent",
        "model_version": contracts.MODEL_VERSION,
        "created_at": "2026-06-25T09:00:00",
    }
    errs = [e.message for e in validator.iter_errors(sample)]
    if errs:
        return [f"[priority_scores] sample FAIL: {errs}"]
    print("[priority_scores] OK  sample row validates")
    return []


def _check_model_chain_output_schema_usable() -> list[str]:
    """model_chain_output 스키마로 샘플 1행을 실제 검증 가능한지 확인."""
    schema = json.loads(paths.MODEL_CHAIN_OUTPUT_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    sample = {
        "manufacturer": "manufacturer 1",
        "substation_id": 12,
        "window_start": "2026-06-20T00:00:00Z",
        "window_end": "2026-06-20T06:00:00Z",
        "anomaly_score": 0.42,
        "risk_score": 88.7,
        "risk_probability": 0.887,
        "risk_level_calibrated": "critical",
        "predicted_lead_time_bucket": "0-24h",
        "predicted_lead_time_confidence": 0.91,
        "leadtime_prob_0-24h": 0.91,
        "leadtime_prob_1-3d": 0.07,
        "leadtime_prob_3-7d": 0.02,
        "lead_time_bucket_distance": 0,
        "days_since_last_fault_event": 42.5,
        "days_since_last_task_event": None,
        "days_since_last_any_event": 12.0,
        "configuration_type": "missing",
        "has_dhw": None,
        "has_buffer_tank": None,
        "main_abnormal_sensors": "p_net_meter_flow;s_dhw_supply_temperature",
        "label": "pre_fault",
        "fault_label": "",
        "estimated_lead_time_hours": 18.0,
        "lead_time_bucket": "0-24h",
    }
    errs = [e.message for e in validator.iter_errors(sample)]
    if errs:
        return [f"[model_chain_output] sample FAIL: {errs}"]
    print("[model_chain_output] OK  sample row validates")
    return []


def _check_mock_columns() -> list[str]:
    if not paths.MOCK_ML_OUTPUT.exists():
        print(f"[mock]       SKIP {paths.MOCK_ML_OUTPUT.name} (아직 생성 전)")
        return []
    df = pd.read_csv(paths.MOCK_ML_OUTPUT)
    expected = contracts.MOCK_ML_OUTPUT_COLUMNS
    if list(df.columns) != expected:
        return [
            "[mock] 컬럼 불일치\n"
            f"  expected={expected}\n  actual  ={list(df.columns)}"
        ]
    missing_feat = [c for c in contracts.PRIORITY_FEATURES if c not in df.columns]
    if missing_feat:
        return [f"[mock] priority 피처 누락: {missing_feat}"]
    # PK(manufacturer, substation_id, window_start, window_end) 유니크 보장
    dup = df.duplicated(subset=contracts.KEY_COLUMNS).sum()
    if dup:
        return [f"[mock] PK 중복 {dup}건 (키={contracts.KEY_COLUMNS}) — generate_mock 유니크 위반"]
    print(f"[mock]       OK  {paths.MOCK_ML_OUTPUT.name} cols={len(df.columns)} rows={len(df)} (PK 유니크)")
    return []


def main() -> int:
    errors: list[str] = []
    errors += _check_json_schemas()
    errors += _check_sql_ddls()
    errors += _check_model_chain_output_schema_usable()
    errors += _check_priority_scores_schema_usable()
    errors += _check_mock_columns()

    print("-" * 60)
    if errors:
        print(f"검증 실패 {len(errors)}건:")
        for e in errors:
            print("  " + e)
        return 1
    print("계약 검증 통과 [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
