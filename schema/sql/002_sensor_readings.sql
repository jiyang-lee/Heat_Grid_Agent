-- 002_sensor_readings.sql
-- 테이블: sensor_readings (실시간 센서 시계열, TimescaleDB hypertable)
-- 1행 = 기계실 1개의 1개 시점(ts). 운영에서 유일하게 실시간으로 들어오는 데이터.
-- 출처: operational_data/substation_*.csv (raw operational 50개 중 운영 유지 29개 = ts + 17 numeric + 11 control)
-- 컬럼명 정규화: raw의 '.'/공백을 snake_case로 변환 (raw->db 매핑은 schema/column_name_mapping.md 참고)

CREATE TABLE IF NOT EXISTS sensor_readings (
    substation_id INTEGER NOT NULL REFERENCES substations(substation_id),
    ts            TIMESTAMPTZ NOT NULL,                      -- raw 'timestamp'

    -- 숫자 센서 17개 (결측 가능 -> nullable)
    outdoor_temperature                    DOUBLE PRECISION,
    p_dhw_control_valve_position           DOUBLE PRECISION,
    p_dhw_return_temperature               DOUBLE PRECISION,
    p_hc1_control_valve_position_setpoint  DOUBLE PRECISION,
    p_hc1_return_temperature               DOUBLE PRECISION,
    p_net_meter_energy                     DOUBLE PRECISION,
    p_net_meter_flow                       DOUBLE PRECISION,
    p_net_meter_heat_power                 DOUBLE PRECISION,
    p_net_meter_volume                     DOUBLE PRECISION,
    p_net_return_temperature               DOUBLE PRECISION,
    p_net_supply_temperature               DOUBLE PRECISION,
    s_dhw_lower_storage_temperature        DOUBLE PRECISION,
    s_dhw_supply_temperature               DOUBLE PRECISION,
    s_dhw_supply_temperature_setpoint      DOUBLE PRECISION,
    s_dhw_upper_storage_temperature        DOUBLE PRECISION,
    s_hc1_supply_temperature               DOUBLE PRECISION,
    s_hc1_supply_temperature_setpoint      DOUBLE PRECISION,

    -- 상태/제어 센서 11개 (문자열, 결측은 적재 시 'missing' 가능)
    s_dhw_3way_valve_status            TEXT,                 -- raw: s_dhw_3-way_valve_status
    s_dhw_control_unit_mode            TEXT,
    s_hc1_1_control_unit_mode          TEXT,                 -- raw: s_hc1.1_control_unit_mode
    s_hc1_1_heating_pump_status        TEXT,                 -- raw: s_hc1.1_heating_pump_status
    s_hc1_2_control_unit_mode          TEXT,                 -- raw: s_hc1.2_control_unit_mode
    s_hc1_2_dhw_control_unit_mode      TEXT,                 -- raw: s_hc1.2_dhw_control unit_mode (공백 포함)
    s_hc1_2_heating_pump_status        TEXT,                 -- raw: s_hc1.2_heating_pump_status
    s_hc1_3_control_unit_mode          TEXT,                 -- raw: s_hc1.3_control_unit_mode
    s_hc1_3_heating_pump_status        TEXT,                 -- raw: s_hc1.3_heating_pump_status
    s_hc1_control_unit_mode            TEXT,
    s_hc1_heating_pump_status_setpoint TEXT,

    PRIMARY KEY (substation_id, ts)
);

-- 시계열 hypertable로 전환
-- 근거: 고빈도 시계열의 시간 파티셔닝/압축/시간범위 쿼리 성능 (TimescaleDB, AGENTS.md 규칙)
SELECT create_hypertable('sensor_readings', 'ts', if_not_exists => TRUE);

COMMENT ON TABLE sensor_readings IS '기계실 실시간 센서 시계열(운영 유일 실시간 소스). 6시간 윈도우 feature의 원천.';
