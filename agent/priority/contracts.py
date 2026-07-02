"""Priority rule engine 계약 상수.

출처 위계상 priority 단계는 mlmodel1의 ML output(`agent_full_data_contract.json`의
`priority_engine.input_columns` / `ml_outputs`)을 소비한다. IF + LGBM risk +
LGBM leadtime 체인은 고정하고, priority 단계만 규칙 기반 점수화로 운영한다.

priority_level 밴딩은 운영 엔진(`priority_engine_v2_rule_based_tuned`)의 기준
urgent/high/medium/low를 그대로 쓴다.
"""

from __future__ import annotations

# --- 키 ---
KEY_COLUMNS = ["manufacturer", "substation_id", "window_start", "window_end"]

# --- legacy priority LGBM 입력 7피처(학습 기록/평가용, runtime 미사용) ---
PRIORITY_FEATURES = [
    "anomaly_score",
    "risk_probability",
    "risk_score",
    "leadtime_prob_0-24h",
    "leadtime_prob_1-3d",
    "leadtime_prob_3-7d",
    "predicted_lead_time_confidence",
]

# --- priority rule engine 입력 ---
PRIORITY_RULE_INPUT_COLUMNS = KEY_COLUMNS + [
    "anomaly_score",
    "risk_probability",
    "risk_level_calibrated",
    "predicted_lead_time_bucket",
    "predicted_lead_time_confidence",
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
]

# --- 라벨(priority_target_v1): 학습셋 전용 ---
# 정상=0 / 3-7d=33 / 1-3d=66 / 0-24h=100
NORMAL_PRIORITY_LABEL = 0
PRIORITY_LABEL_BY_BUCKET = {
    "3-7d": 33,
    "1-3d": 66,
    "0-24h": 100,
}
PRE_FAULT_LABEL = "pre_fault"
NORMAL_LABEL = "normal"

# --- legacy priority LGBM 밴딩 (학습 기록/평가용, runtime 미사용) ---
PRIORITY_LEVEL_BANDS = [
    (83.0, "urgent"),
    (49.5, "high"),
    (16.5, "medium"),
    (0.0, "low"),
]
PRIORITY_LEVELS = ["low", "medium", "high", "urgent"]

# --- 출력 계약 ---
PRIORITY_SCORE_MIN = 0.0
PRIORITY_SCORE_MAX = 100.0
MODEL_VERSION = "priority_engine_v2_rule_based_tuned"

PRIORITY_SCORES_COLUMNS = [
    "manufacturer",
    "substation_id",
    "window_start",
    "window_end",
    "priority_score",
    "priority_level",
    "priority_reason",
    "model_version",
    "created_at",
]

# --- 목 데이터(ML output 레벨) 전체 컬럼 계약 ---
# 실 ML output은 main_abnormal_sensors 를 main_abnormal_features 로 부름 → 어댑터에서 매핑.
MOCK_ML_OUTPUT_COLUMNS = [
    # 키
    "manufacturer",
    "substation_id",
    "window_start",
    "window_end",
    # priority 입력 / 위험 / 리드타임
    "anomaly_score",
    "risk_score",
    "risk_probability",
    "risk_level_calibrated",
    "predicted_lead_time_bucket",
    "predicted_lead_time_confidence",
    "leadtime_prob_0-24h",
    "leadtime_prob_1-3d",
    "leadtime_prob_3-7d",
    "lead_time_bucket_distance",
    # 이력
    "days_since_last_fault_event",
    "days_since_last_task_event",
    "days_since_last_any_event",
    # 에이전트 컨텍스트
    "configuration_type",
    "has_dhw",
    "has_buffer_tank",
    "main_abnormal_sensors",
    # 라벨/타깃
    "label",
    "fault_label",
    "estimated_lead_time_hours",
    "lead_time_bucket",
]

RISK_LEVELS_CALIBRATED = ["low", "medium", "high", "critical"]
LEAD_TIME_BUCKETS = ["0-24h", "1-3d", "3-7d"]

# 실 ML output ↔ 데모 목 데이터 컬럼명 어댑팅(런타임 매핑)
ML_OUTPUT_COLUMN_ALIASES = {
    "main_abnormal_features": "main_abnormal_sensors",
}


def priority_level_for(score: float) -> str:
    """0~100 priority_score 를 운영 엔진과 동일 라벨로 밴딩."""
    for threshold, level in PRIORITY_LEVEL_BANDS:
        if score >= threshold:
            return level
    return "low"


def priority_label_for(label: str, lead_time_bucket: str | None) -> int:
    """label(normal/pre_fault) + lead_time_bucket → priority 라벨(0/33/66/100)."""
    if label == NORMAL_LABEL or not lead_time_bucket:
        return NORMAL_PRIORITY_LABEL
    return PRIORITY_LABEL_BY_BUCKET.get(lead_time_bucket, NORMAL_PRIORITY_LABEL)
