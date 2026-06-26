-- 007_priority_scores.sql
-- 테이블: priority_scores (rule priority engine 출력)
-- 1행 = 기계실 1개 x 6시간 윈도우 1개에 대한 우선순위 점수.
-- 출처: IF + LGBM risk + LGBM leadtime 중간 출력 → 규칙 기반 priority score(0~100).
-- 엔진: priority_engine_v2_rule_based_tuned.
-- 범위: 점수/밴딩/버전만 보관. 컴포넌트 점수 풀세트는 엔진 산출물(priority_engine_scores_tuned.csv)에 둔다.

CREATE TABLE IF NOT EXISTS priority_scores (
    manufacturer       TEXT NOT NULL,              -- 제조사 식별자
    substation_id      INTEGER NOT NULL,           -- 기계실 식별자
    window_start       TIMESTAMPTZ NOT NULL,       -- 윈도우 시작
    window_end         TIMESTAMPTZ NOT NULL,       -- 윈도우 종료
    priority_score     DOUBLE PRECISION NOT NULL,  -- 우선순위 점수 0~100 (규칙 기반, clip)
    priority_level     TEXT,                       -- 밴딩 라벨(urgent/high/medium/low)
    priority_reason    TEXT,                       -- 사람이 읽는 근거 요약(선택)
    model_version      TEXT NOT NULL,              -- 엔진 버전(예: priority_engine_v2_rule_based_tuned)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(), -- 생성 시각

    PRIMARY KEY (manufacturer, substation_id, window_start, window_end),
    CONSTRAINT priority_scores_model_chain_fk FOREIGN KEY (
        manufacturer,
        substation_id,
        window_start,
        window_end
    ) REFERENCES model_chain_output (
        manufacturer,
        substation_id,
        window_start,
        window_end
    ),
    CONSTRAINT priority_scores_time_chk CHECK (window_start < window_end),
    CONSTRAINT priority_scores_range_chk CHECK (priority_score >= 0 AND priority_score <= 100),
    CONSTRAINT priority_scores_level_chk CHECK (
        priority_level IS NULL
        OR priority_level IN ('low', 'medium', 'high', 'urgent')
    )
);

CREATE INDEX IF NOT EXISTS idx_priority_scores_rank
    ON priority_scores (priority_score DESC);

COMMENT ON TABLE priority_scores IS '규칙 기반 priority engine 출력. 1행은 기계실 1개 x 6시간 윈도우 1개의 우선순위 점수.';
