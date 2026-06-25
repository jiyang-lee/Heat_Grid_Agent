-- 004_maintenance_events.sql
-- 테이블: maintenance_events (정비/작업 이력, 이벤트 로그)
-- 1행 = 정비 1건. 정비가 발생할 때만 추가됨.
-- 출처: disturbances.csv (substation ID, Event start, type)
-- 용도: days_since_last_task_event / days_since_last_any_event / maintenance_related / disturbance_count 계산.
-- 합성 키: disturbances.csv에는 고유 event id가 없어 BIGSERIAL로 대리키 부여.

CREATE TABLE IF NOT EXISTS maintenance_events (
    id            BIGSERIAL PRIMARY KEY,
    substation_id INTEGER NOT NULL REFERENCES substations(substation_id),
    event_start   TIMESTAMPTZ NOT NULL,                      -- 'Event start'
    type          TEXT,                                      -- 'type' (정비/작업 종류)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 최근 정비 이벤트 조회 최적화 (days_since_last_task_event 계산용)
CREATE INDEX IF NOT EXISTS idx_maintenance_events_sub_start
    ON maintenance_events (substation_id, event_start DESC);

COMMENT ON TABLE maintenance_events IS '정비/작업 이력(이벤트 로그). days_since_last_task_event 등 계산 원천.';
