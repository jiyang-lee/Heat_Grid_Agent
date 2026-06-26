-- 006_model_chain_output.sql
-- 테이블: model_chain_output (IF + LGBM risk + LGBM leadtime 중간 예측 체인 출력)
-- 1행 = 기계실 1개 x 6시간 윈도우 1개에 대한 anomaly/risk/leadtime 신호.
-- priority_scores의 직접 입력이므로 priority_scores보다 먼저 적재된다.

CREATE TABLE IF NOT EXISTS model_chain_output (
    manufacturer                    TEXT NOT NULL,              -- 제조사 식별자
    substation_id                   INTEGER NOT NULL,           -- 기계실 식별자
    window_start                    TIMESTAMPTZ NOT NULL,       -- 윈도우 시작
    window_end                      TIMESTAMPTZ NOT NULL,       -- 윈도우 종료
    anomaly_score                   DOUBLE PRECISION NOT NULL,  -- IF 기반 이상 점수 0~1
    risk_score                      DOUBLE PRECISION NOT NULL,  -- risk_probability x 100
    risk_probability                DOUBLE PRECISION NOT NULL,  -- LGBM risk 확률 0~1
    risk_level_calibrated           TEXT NOT NULL,              -- low/medium/high/critical
    predicted_lead_time_bucket      TEXT NOT NULL,              -- 0-24h/1-3d/3-7d
    predicted_lead_time_confidence  DOUBLE PRECISION NOT NULL,  -- leadtime 예측 max probability
    "leadtime_prob_0-24h"           DOUBLE PRECISION NOT NULL,  -- 0-24h bucket probability
    "leadtime_prob_1-3d"            DOUBLE PRECISION NOT NULL,  -- 1-3d bucket probability
    "leadtime_prob_3-7d"            DOUBLE PRECISION NOT NULL,  -- 3-7d bucket probability
    lead_time_bucket_distance       INTEGER,                    -- 실제/예측 bucket 거리(라벨 있을 때)
    days_since_last_fault_event     DOUBLE PRECISION,           -- 최근 고장 이후 일수
    days_since_last_task_event      DOUBLE PRECISION,           -- 최근 정비 이후 일수
    days_since_last_any_event       DOUBLE PRECISION,           -- 최근 이벤트 이후 일수
    configuration_type              TEXT,                       -- 설비 구성
    has_dhw                         BOOLEAN,                    -- DHW 여부
    has_buffer_tank                 BOOLEAN,                    -- buffer tank 여부
    main_abnormal_sensors           TEXT,                       -- 주요 이상 센서 요약
    label                           TEXT,                       -- supervised label(검증/학습용)
    fault_label                     TEXT,                       -- 원천 fault label(있을 때)
    estimated_lead_time_hours       DOUBLE PRECISION,           -- 신고까지 남은 시간(학습/검증용)
    lead_time_bucket                TEXT,                       -- 실제 leadtime bucket(학습/검증용)
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (manufacturer, substation_id, window_start, window_end),
    CONSTRAINT model_chain_output_time_chk CHECK (window_start < window_end),
    CONSTRAINT model_chain_output_anomaly_chk CHECK (anomaly_score >= 0 AND anomaly_score <= 1),
    CONSTRAINT model_chain_output_risk_score_chk CHECK (risk_score >= 0 AND risk_score <= 100),
    CONSTRAINT model_chain_output_risk_prob_chk CHECK (risk_probability >= 0 AND risk_probability <= 1),
    CONSTRAINT model_chain_output_lead_conf_chk CHECK (
        predicted_lead_time_confidence >= 0 AND predicted_lead_time_confidence <= 1
    ),
    CONSTRAINT model_chain_output_lead_prob_chk CHECK (
        "leadtime_prob_0-24h" >= 0 AND "leadtime_prob_0-24h" <= 1
        AND "leadtime_prob_1-3d" >= 0 AND "leadtime_prob_1-3d" <= 1
        AND "leadtime_prob_3-7d" >= 0 AND "leadtime_prob_3-7d" <= 1
    ),
    CONSTRAINT model_chain_output_risk_level_chk CHECK (
        risk_level_calibrated IN ('low', 'medium', 'high', 'critical')
    ),
    CONSTRAINT model_chain_output_predicted_leadtime_chk CHECK (
        predicted_lead_time_bucket IN ('0-24h', '1-3d', '3-7d')
    ),
    CONSTRAINT model_chain_output_label_chk CHECK (
        label IS NULL OR label IN ('normal', 'pre_fault', '')
    ),
    CONSTRAINT model_chain_output_leadtime_chk CHECK (
        lead_time_bucket IS NULL OR lead_time_bucket IN ('0-24h', '1-3d', '3-7d', '')
    )
);

CREATE INDEX IF NOT EXISTS idx_model_chain_output_risk
    ON model_chain_output (risk_probability DESC);

CREATE INDEX IF NOT EXISTS idx_model_chain_output_leadtime
    ON model_chain_output (predicted_lead_time_bucket);

COMMENT ON TABLE model_chain_output IS 'IF + LGBM risk + LGBM leadtime 중간 예측 체인 출력. priority_scores의 직접 입력.';
