"""입출력 경로/계약 상수.

모든 산출물은 파일 기반(CSV/JSON/MD). 실DB는 기동하지 않으며 DDL은 스키마 계약으로만 둔다.
실 ML output 도착 시 ``MOCK_ML_OUTPUT`` 만 실제 경로로 바꾸면 파이프라인은 그대로 동작한다.
"""

from __future__ import annotations

from pathlib import Path

# 리포 루트 = agent/io/paths.py 기준 2단계 상위
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- 입력(데모: 목 데이터) ---
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

# --- priority 모델 아티팩트 ---
MODELS_DIR = REPO_ROOT / "agent" / "priority" / "models"
PRIORITY_MODEL_PATH = MODELS_DIR / "lightgbm_priority_model.joblib"
PRIORITY_MODEL_META = MODELS_DIR / "priority_model_metadata.json"

# --- 스키마 계약 ---
SCHEMA_DIR = REPO_ROOT / "schema"
SCHEMA_JSON_DIR = SCHEMA_DIR / "json"
SCHEMA_SQL_DIR = SCHEMA_DIR / "sql"
PRIORITY_SCORES_SCHEMA = SCHEMA_JSON_DIR / "priority_scores.schema.json"
PRIORITY_SCORES_DDL = SCHEMA_SQL_DIR / "006_priority_scores.sql"

# --- 에이전트 산출물(보고서/메일 초안) ---
DOCS_SEND_DIR = REPO_ROOT / "docs" / "send"


def ensure_dir(path: Path) -> Path:
    """디렉토리를 보장하고 그대로 반환한다."""
    path.mkdir(parents=True, exist_ok=True)
    return path
