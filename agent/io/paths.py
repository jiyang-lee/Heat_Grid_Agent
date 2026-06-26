"""입출력 경로/계약 상수.

모든 산출물은 파일 기반(CSV/JSON/MD). 실DB는 기동하지 않으며 DDL은 스키마 계약으로만 둔다.
실 ML output 도착 시 ``MOCK_ML_OUTPUT`` 만 실제 경로로 바꾸면 파이프라인은 그대로 동작한다.
"""

from __future__ import annotations

import re
from pathlib import Path

# 리포 루트 = agent/io/paths.py 기준 2단계 상위
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- 입력(데모: 목 데이터, 명시 실행용 fallback) ---
DATA_DIR = REPO_ROOT / "data"
MOCK_DIR = DATA_DIR / "mock"
MOCK_ML_OUTPUT = MOCK_DIR / "mock_ml_output.csv"

# --- ML feature 계약(mlmodel1 이전본) ---
ML_FEATURES_DIR = DATA_DIR / "processed" / "ml_features"
AGENT_FULL_DATA_CONTRACT = ML_FEATURES_DIR / "agent_full_data_contract.json"

# --- priority 산출물 ---
PROCESSED_DIR = DATA_DIR / "processed"
PRIORITY_DIR = PROCESSED_DIR / "ml_priority"
PRIORITY_SCORES_CSV = PRIORITY_DIR / "priority_scores.csv"

# --- 실제 모델 체인 산출물 ---
MODEL_HANDOFF_DIR = REPO_ROOT / "model_handoff" / "heatgrid_ml_models_2026-06-25"
MODEL_CHAIN_DIR = PROCESSED_DIR / "ml_model_chain"
MODEL_CHAIN_OUTPUT_CSV = MODEL_CHAIN_DIR / "model_chain_output.csv"
MODEL_CHAIN_FEATURE_REPORT_JSON = MODEL_CHAIN_DIR / "feature_adapter_report.json"

# --- PreDist 감사 산출물 ---
PREDIST_LABEL_AUDIT_DIR = PROCESSED_DIR / "predist_label_audit"
PREDIST_LABEL_AUDIT_JSON = PREDIST_LABEL_AUDIT_DIR / "label_distribution.json"
PREDIST_LABEL_AUDIT_CSV = PREDIST_LABEL_AUDIT_DIR / "label_distribution.csv"
PREDIST_LABEL_AUDIT_MD = PREDIST_LABEL_AUDIT_DIR / "label_distribution.md"

# --- Full PreDist supervised 전처리 산출물 ---
PREDIST_FULL_SUPERVISED_DIR = PROCESSED_DIR / "predist_full_supervised"
PREDIST_FULL_PREPROCESSED_CSV = PREDIST_FULL_SUPERVISED_DIR / "preprocessed_windows.csv"
PREDIST_FULL_LABELS_CSV = PREDIST_FULL_SUPERVISED_DIR / "supervised_window_labels.csv"
PREDIST_FULL_MANIFEST_JSON = PREDIST_FULL_SUPERVISED_DIR / "manifest.json"

# --- priority 모델 아티팩트 ---
MODELS_DIR = REPO_ROOT / "agent" / "priority" / "models"
PRIORITY_MODEL_PATH = MODELS_DIR / "lightgbm_priority_model.joblib"
PRIORITY_MODEL_META = MODELS_DIR / "priority_model_metadata.json"

# --- 스키마 계약 ---
SCHEMA_DIR = REPO_ROOT / "schema"
SCHEMA_JSON_DIR = SCHEMA_DIR / "json"
SCHEMA_SQL_DIR = SCHEMA_DIR / "sql"
MODEL_CHAIN_OUTPUT_SCHEMA = SCHEMA_JSON_DIR / "model_chain_output.schema.json"
MODEL_CHAIN_OUTPUT_DDL = SCHEMA_SQL_DIR / "006_model_chain_output.sql"
PRIORITY_SCORES_SCHEMA = SCHEMA_JSON_DIR / "priority_scores.schema.json"
PRIORITY_SCORES_DDL = SCHEMA_SQL_DIR / "007_priority_scores.sql"

# --- 에이전트 산출물(보고서/메일 초안) ---
DOCS_SEND_DIR = REPO_ROOT / "docs" / "send"


def ensure_dir(path: Path) -> Path:
    """디렉토리를 보장하고 그대로 반환한다."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def slug(s) -> str:
    """비영숫자 제거 슬러그(키/파일명용)."""
    return re.sub(r"[^0-9A-Za-z]+", "", str(s))


def make_key(manufacturer, substation_id, window_start) -> str:
    """행 식별 키. PK(manufacturer, substation_id, window_start[, window_end])를 반영.

    manufacturer를 포함해야 서로 다른 제조사가 같은 substation_id+윈도우를 가져도 충돌하지 않는다.
    docs/send 파일명(work_order_{key}.md / email_{key}.md)과 동일하게 쓰인다.
    """
    return f"{slug(manufacturer)}_{int(substation_id)}_{slug(window_start)}"
