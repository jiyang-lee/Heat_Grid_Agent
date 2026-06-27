-- 003_fault_events.sql
-- 테이블: fault_events (고장 이력, 이벤트 로그)
-- 1행 = 고장 1건. 고장이 신고될 때만 추가됨.
-- 출처: faults.csv (운영에 필요한 컬럼만; 훈련 전용 컬럼은 제외)
-- 용도: days_since_last_fault_event / recent_fault_* feature 계산.
-- 제외(훈련 전용): Possible anomaly start/end, Training start/end, efd_possible, Monitoring potential

CREATE TABLE IF NOT EXISTS fault_events (
    event_id             BIGINT PRIMARY KEY,                 -- faults.csv 'Event ID'
    substation_id        INTEGER NOT NULL REFERENCES substations(substation_id),
    report_date          TIMESTAMPTZ NOT NULL,               -- 'Report date' (lead time/leakage 기준 시점)
    problem_en           TEXT,                               -- 'Problem EN'
    fault_label          TEXT,                               -- 'Fault label'
    event_description_en TEXT,                               -- 'Event description EN' (optional)
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 최근 고장 이벤트 조회 최적화 (days_since_last_fault_event 계산용)
CREATE INDEX IF NOT EXISTS idx_fault_events_sub_report
    ON fault_events (substation_id, report_date DESC);

COMMENT ON TABLE fault_events IS '고장 신고 이력(이벤트 로그). days_since_last_fault_event 계산 원천.';
