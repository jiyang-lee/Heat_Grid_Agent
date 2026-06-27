-- 001_substations.sql
-- 테이블: substations (설비 마스터, 정적 데이터)
-- 1행 = 기계실 1개. 거의 변하지 않는 기준 정보.
-- 출처: configuration_types.csv + source metadata(manufacturer, substation_id, source_file)
-- 용도: configuration_type / has_dhw / has_buffer_tank / manufacturer feature 생성의 원천.

CREATE TABLE IF NOT EXISTS substations (
    substation_id      INTEGER PRIMARY KEY,                 -- 기계실 식별자 (파일명/소스 메타에서 확정)
    manufacturer       TEXT NOT NULL,                       -- 'manufacturer 1' | 'manufacturer 2'
    configuration_type TEXT,                                -- 설비 구성 유형 (enum, 아래 CHECK 참고)
    has_dhw            BOOLEAN,                             -- 온수(DHW) 설비 보유 여부
    has_buffer_tank    BOOLEAN,                             -- 버퍼탱크 보유 여부
    source_file        TEXT,                                -- 추적용 원본 파일 경로/이름
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT substations_manufacturer_chk
        CHECK (manufacturer IN ('manufacturer 1', 'manufacturer 2')),
    CONSTRAINT substations_configuration_type_chk
        CHECK (configuration_type IS NULL OR configuration_type IN (
            'sh',
            'sh_dhw',
            'sh_dhw_with_sub_circuits',
            'sh_with_buffer_tank',
            'sh_with_sub_circuits',
            'missing'
        ))
);

COMMENT ON TABLE substations IS '기계실 설비 마스터(정적). ML feature의 설비 구성/제조사 원천.';
COMMENT ON COLUMN substations.configuration_type IS 'configuration_types.csv 기반 설비 구성 유형';
