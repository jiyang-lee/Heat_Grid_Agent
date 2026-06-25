-- 005_preprocessed_windows.sql
-- 테이블: preprocessed_windows (전처리 데이터, 피처 엔지니어링 입력)
-- 1행 = 기계실 1개 x 6시간 구간 1개.
-- 출처: raw 4테이블(substations, sensor_readings, fault_events, maintenance_events).
-- 범위: 피처 엔지니어링 전 표준 중간 데이터. one-hot/imputation/selected feature는 포함하지 않는다.

CREATE TABLE IF NOT EXISTS preprocessed_windows (
    substation_id                                              INTEGER NOT NULL REFERENCES substations(substation_id), -- 기계실 식별자
    window_start                                               TIMESTAMPTZ NOT NULL, -- 전처리 구간 시작
    window_end                                                 TIMESTAMPTZ NOT NULL, -- 전처리 구간 종료
    source_file                                                TEXT, -- 원천 센서 파일 또는 스트림 식별자
    row_count                                                  INTEGER NOT NULL, -- 실제 관측 row 수
    expected_row_count                                         INTEGER, -- 기대 row 수
    median_interval_minutes                                    DOUBLE PRECISION, -- 중앙 샘플링 간격(분)
    missing_count                                              INTEGER, -- 구간 전체 결측 수
    missing_rate                                               DOUBLE PRECISION, -- 구간 전체 결측률
    invalid_timestamp_rows_in_file                             INTEGER, -- 파일/배치 단위 invalid timestamp row 수
    timestamp_gap_count                                        INTEGER, -- timestamp gap 수
    max_timestamp_gap_minutes                                  DOUBLE PRECISION, -- 최대 timestamp gap(분)
    sensor_error_candidate_count                               INTEGER, -- 센서 오류 후보 수
    extreme_change_count                                       INTEGER, -- 급격 변화 후보 수
    outdoor_temperature__mean                                  DOUBLE PRECISION, -- outdoor_temperature mean
    outdoor_temperature__min                                   DOUBLE PRECISION, -- outdoor_temperature min
    outdoor_temperature__max                                   DOUBLE PRECISION, -- outdoor_temperature max
    outdoor_temperature__std                                   DOUBLE PRECISION, -- outdoor_temperature std
    outdoor_temperature__first                                 DOUBLE PRECISION, -- outdoor_temperature first
    outdoor_temperature__last                                  DOUBLE PRECISION, -- outdoor_temperature last
    outdoor_temperature__delta                                 DOUBLE PRECISION, -- outdoor_temperature delta
    outdoor_temperature__missing_count                         INTEGER, -- outdoor_temperature missing_count
    outdoor_temperature__missing_rate                          DOUBLE PRECISION, -- outdoor_temperature missing_rate
    p_dhw_control_valve_position__mean                         DOUBLE PRECISION, -- p_dhw_control_valve_position mean
    p_dhw_control_valve_position__min                          DOUBLE PRECISION, -- p_dhw_control_valve_position min
    p_dhw_control_valve_position__max                          DOUBLE PRECISION, -- p_dhw_control_valve_position max
    p_dhw_control_valve_position__std                          DOUBLE PRECISION, -- p_dhw_control_valve_position std
    p_dhw_control_valve_position__first                        DOUBLE PRECISION, -- p_dhw_control_valve_position first
    p_dhw_control_valve_position__last                         DOUBLE PRECISION, -- p_dhw_control_valve_position last
    p_dhw_control_valve_position__delta                        DOUBLE PRECISION, -- p_dhw_control_valve_position delta
    p_dhw_control_valve_position__missing_count                INTEGER, -- p_dhw_control_valve_position missing_count
    p_dhw_control_valve_position__missing_rate                 DOUBLE PRECISION, -- p_dhw_control_valve_position missing_rate
    p_dhw_return_temperature__mean                             DOUBLE PRECISION, -- p_dhw_return_temperature mean
    p_dhw_return_temperature__min                              DOUBLE PRECISION, -- p_dhw_return_temperature min
    p_dhw_return_temperature__max                              DOUBLE PRECISION, -- p_dhw_return_temperature max
    p_dhw_return_temperature__std                              DOUBLE PRECISION, -- p_dhw_return_temperature std
    p_dhw_return_temperature__first                            DOUBLE PRECISION, -- p_dhw_return_temperature first
    p_dhw_return_temperature__last                             DOUBLE PRECISION, -- p_dhw_return_temperature last
    p_dhw_return_temperature__delta                            DOUBLE PRECISION, -- p_dhw_return_temperature delta
    p_dhw_return_temperature__missing_count                    INTEGER, -- p_dhw_return_temperature missing_count
    p_dhw_return_temperature__missing_rate                     DOUBLE PRECISION, -- p_dhw_return_temperature missing_rate
    p_hc1_control_valve_position_setpoint__mean                DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint mean
    p_hc1_control_valve_position_setpoint__min                 DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint min
    p_hc1_control_valve_position_setpoint__max                 DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint max
    p_hc1_control_valve_position_setpoint__std                 DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint std
    p_hc1_control_valve_position_setpoint__first               DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint first
    p_hc1_control_valve_position_setpoint__last                DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint last
    p_hc1_control_valve_position_setpoint__delta               DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint delta
    p_hc1_control_valve_position_setpoint__missing_count       INTEGER, -- p_hc1_control_valve_position_setpoint missing_count
    p_hc1_control_valve_position_setpoint__missing_rate        DOUBLE PRECISION, -- p_hc1_control_valve_position_setpoint missing_rate
    p_hc1_return_temperature__mean                             DOUBLE PRECISION, -- p_hc1_return_temperature mean
    p_hc1_return_temperature__min                              DOUBLE PRECISION, -- p_hc1_return_temperature min
    p_hc1_return_temperature__max                              DOUBLE PRECISION, -- p_hc1_return_temperature max
    p_hc1_return_temperature__std                              DOUBLE PRECISION, -- p_hc1_return_temperature std
    p_hc1_return_temperature__first                            DOUBLE PRECISION, -- p_hc1_return_temperature first
    p_hc1_return_temperature__last                             DOUBLE PRECISION, -- p_hc1_return_temperature last
    p_hc1_return_temperature__delta                            DOUBLE PRECISION, -- p_hc1_return_temperature delta
    p_hc1_return_temperature__missing_count                    INTEGER, -- p_hc1_return_temperature missing_count
    p_hc1_return_temperature__missing_rate                     DOUBLE PRECISION, -- p_hc1_return_temperature missing_rate
    p_net_meter_energy__mean                                   DOUBLE PRECISION, -- p_net_meter_energy mean
    p_net_meter_energy__min                                    DOUBLE PRECISION, -- p_net_meter_energy min
    p_net_meter_energy__max                                    DOUBLE PRECISION, -- p_net_meter_energy max
    p_net_meter_energy__std                                    DOUBLE PRECISION, -- p_net_meter_energy std
    p_net_meter_energy__first                                  DOUBLE PRECISION, -- p_net_meter_energy first
    p_net_meter_energy__last                                   DOUBLE PRECISION, -- p_net_meter_energy last
    p_net_meter_energy__delta                                  DOUBLE PRECISION, -- p_net_meter_energy delta
    p_net_meter_energy__missing_count                          INTEGER, -- p_net_meter_energy missing_count
    p_net_meter_energy__missing_rate                           DOUBLE PRECISION, -- p_net_meter_energy missing_rate
    p_net_meter_flow__mean                                     DOUBLE PRECISION, -- p_net_meter_flow mean
    p_net_meter_flow__min                                      DOUBLE PRECISION, -- p_net_meter_flow min
    p_net_meter_flow__max                                      DOUBLE PRECISION, -- p_net_meter_flow max
    p_net_meter_flow__std                                      DOUBLE PRECISION, -- p_net_meter_flow std
    p_net_meter_flow__first                                    DOUBLE PRECISION, -- p_net_meter_flow first
    p_net_meter_flow__last                                     DOUBLE PRECISION, -- p_net_meter_flow last
    p_net_meter_flow__delta                                    DOUBLE PRECISION, -- p_net_meter_flow delta
    p_net_meter_flow__missing_count                            INTEGER, -- p_net_meter_flow missing_count
    p_net_meter_flow__missing_rate                             DOUBLE PRECISION, -- p_net_meter_flow missing_rate
    p_net_meter_heat_power__mean                               DOUBLE PRECISION, -- p_net_meter_heat_power mean
    p_net_meter_heat_power__min                                DOUBLE PRECISION, -- p_net_meter_heat_power min
    p_net_meter_heat_power__max                                DOUBLE PRECISION, -- p_net_meter_heat_power max
    p_net_meter_heat_power__std                                DOUBLE PRECISION, -- p_net_meter_heat_power std
    p_net_meter_heat_power__first                              DOUBLE PRECISION, -- p_net_meter_heat_power first
    p_net_meter_heat_power__last                               DOUBLE PRECISION, -- p_net_meter_heat_power last
    p_net_meter_heat_power__delta                              DOUBLE PRECISION, -- p_net_meter_heat_power delta
    p_net_meter_heat_power__missing_count                      INTEGER, -- p_net_meter_heat_power missing_count
    p_net_meter_heat_power__missing_rate                       DOUBLE PRECISION, -- p_net_meter_heat_power missing_rate
    p_net_meter_volume__mean                                   DOUBLE PRECISION, -- p_net_meter_volume mean
    p_net_meter_volume__min                                    DOUBLE PRECISION, -- p_net_meter_volume min
    p_net_meter_volume__max                                    DOUBLE PRECISION, -- p_net_meter_volume max
    p_net_meter_volume__std                                    DOUBLE PRECISION, -- p_net_meter_volume std
    p_net_meter_volume__first                                  DOUBLE PRECISION, -- p_net_meter_volume first
    p_net_meter_volume__last                                   DOUBLE PRECISION, -- p_net_meter_volume last
    p_net_meter_volume__delta                                  DOUBLE PRECISION, -- p_net_meter_volume delta
    p_net_meter_volume__missing_count                          INTEGER, -- p_net_meter_volume missing_count
    p_net_meter_volume__missing_rate                           DOUBLE PRECISION, -- p_net_meter_volume missing_rate
    p_net_return_temperature__mean                             DOUBLE PRECISION, -- p_net_return_temperature mean
    p_net_return_temperature__min                              DOUBLE PRECISION, -- p_net_return_temperature min
    p_net_return_temperature__max                              DOUBLE PRECISION, -- p_net_return_temperature max
    p_net_return_temperature__std                              DOUBLE PRECISION, -- p_net_return_temperature std
    p_net_return_temperature__first                            DOUBLE PRECISION, -- p_net_return_temperature first
    p_net_return_temperature__last                             DOUBLE PRECISION, -- p_net_return_temperature last
    p_net_return_temperature__delta                            DOUBLE PRECISION, -- p_net_return_temperature delta
    p_net_return_temperature__missing_count                    INTEGER, -- p_net_return_temperature missing_count
    p_net_return_temperature__missing_rate                     DOUBLE PRECISION, -- p_net_return_temperature missing_rate
    p_net_supply_temperature__mean                             DOUBLE PRECISION, -- p_net_supply_temperature mean
    p_net_supply_temperature__min                              DOUBLE PRECISION, -- p_net_supply_temperature min
    p_net_supply_temperature__max                              DOUBLE PRECISION, -- p_net_supply_temperature max
    p_net_supply_temperature__std                              DOUBLE PRECISION, -- p_net_supply_temperature std
    p_net_supply_temperature__first                            DOUBLE PRECISION, -- p_net_supply_temperature first
    p_net_supply_temperature__last                             DOUBLE PRECISION, -- p_net_supply_temperature last
    p_net_supply_temperature__delta                            DOUBLE PRECISION, -- p_net_supply_temperature delta
    p_net_supply_temperature__missing_count                    INTEGER, -- p_net_supply_temperature missing_count
    p_net_supply_temperature__missing_rate                     DOUBLE PRECISION, -- p_net_supply_temperature missing_rate
    s_dhw_lower_storage_temperature__mean                      DOUBLE PRECISION, -- s_dhw_lower_storage_temperature mean
    s_dhw_lower_storage_temperature__min                       DOUBLE PRECISION, -- s_dhw_lower_storage_temperature min
    s_dhw_lower_storage_temperature__max                       DOUBLE PRECISION, -- s_dhw_lower_storage_temperature max
    s_dhw_lower_storage_temperature__std                       DOUBLE PRECISION, -- s_dhw_lower_storage_temperature std
    s_dhw_lower_storage_temperature__first                     DOUBLE PRECISION, -- s_dhw_lower_storage_temperature first
    s_dhw_lower_storage_temperature__last                      DOUBLE PRECISION, -- s_dhw_lower_storage_temperature last
    s_dhw_lower_storage_temperature__delta                     DOUBLE PRECISION, -- s_dhw_lower_storage_temperature delta
    s_dhw_lower_storage_temperature__missing_count             INTEGER, -- s_dhw_lower_storage_temperature missing_count
    s_dhw_lower_storage_temperature__missing_rate              DOUBLE PRECISION, -- s_dhw_lower_storage_temperature missing_rate
    s_dhw_supply_temperature__mean                             DOUBLE PRECISION, -- s_dhw_supply_temperature mean
    s_dhw_supply_temperature__min                              DOUBLE PRECISION, -- s_dhw_supply_temperature min
    s_dhw_supply_temperature__max                              DOUBLE PRECISION, -- s_dhw_supply_temperature max
    s_dhw_supply_temperature__std                              DOUBLE PRECISION, -- s_dhw_supply_temperature std
    s_dhw_supply_temperature__first                            DOUBLE PRECISION, -- s_dhw_supply_temperature first
    s_dhw_supply_temperature__last                             DOUBLE PRECISION, -- s_dhw_supply_temperature last
    s_dhw_supply_temperature__delta                            DOUBLE PRECISION, -- s_dhw_supply_temperature delta
    s_dhw_supply_temperature__missing_count                    INTEGER, -- s_dhw_supply_temperature missing_count
    s_dhw_supply_temperature__missing_rate                     DOUBLE PRECISION, -- s_dhw_supply_temperature missing_rate
    s_dhw_supply_temperature_setpoint__mean                    DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint mean
    s_dhw_supply_temperature_setpoint__min                     DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint min
    s_dhw_supply_temperature_setpoint__max                     DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint max
    s_dhw_supply_temperature_setpoint__std                     DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint std
    s_dhw_supply_temperature_setpoint__first                   DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint first
    s_dhw_supply_temperature_setpoint__last                    DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint last
    s_dhw_supply_temperature_setpoint__delta                   DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint delta
    s_dhw_supply_temperature_setpoint__missing_count           INTEGER, -- s_dhw_supply_temperature_setpoint missing_count
    s_dhw_supply_temperature_setpoint__missing_rate            DOUBLE PRECISION, -- s_dhw_supply_temperature_setpoint missing_rate
    s_dhw_upper_storage_temperature__mean                      DOUBLE PRECISION, -- s_dhw_upper_storage_temperature mean
    s_dhw_upper_storage_temperature__min                       DOUBLE PRECISION, -- s_dhw_upper_storage_temperature min
    s_dhw_upper_storage_temperature__max                       DOUBLE PRECISION, -- s_dhw_upper_storage_temperature max
    s_dhw_upper_storage_temperature__std                       DOUBLE PRECISION, -- s_dhw_upper_storage_temperature std
    s_dhw_upper_storage_temperature__first                     DOUBLE PRECISION, -- s_dhw_upper_storage_temperature first
    s_dhw_upper_storage_temperature__last                      DOUBLE PRECISION, -- s_dhw_upper_storage_temperature last
    s_dhw_upper_storage_temperature__delta                     DOUBLE PRECISION, -- s_dhw_upper_storage_temperature delta
    s_dhw_upper_storage_temperature__missing_count             INTEGER, -- s_dhw_upper_storage_temperature missing_count
    s_dhw_upper_storage_temperature__missing_rate              DOUBLE PRECISION, -- s_dhw_upper_storage_temperature missing_rate
    s_hc1_supply_temperature__mean                             DOUBLE PRECISION, -- s_hc1_supply_temperature mean
    s_hc1_supply_temperature__min                              DOUBLE PRECISION, -- s_hc1_supply_temperature min
    s_hc1_supply_temperature__max                              DOUBLE PRECISION, -- s_hc1_supply_temperature max
    s_hc1_supply_temperature__std                              DOUBLE PRECISION, -- s_hc1_supply_temperature std
    s_hc1_supply_temperature__first                            DOUBLE PRECISION, -- s_hc1_supply_temperature first
    s_hc1_supply_temperature__last                             DOUBLE PRECISION, -- s_hc1_supply_temperature last
    s_hc1_supply_temperature__delta                            DOUBLE PRECISION, -- s_hc1_supply_temperature delta
    s_hc1_supply_temperature__missing_count                    INTEGER, -- s_hc1_supply_temperature missing_count
    s_hc1_supply_temperature__missing_rate                     DOUBLE PRECISION, -- s_hc1_supply_temperature missing_rate
    s_hc1_supply_temperature_setpoint__mean                    DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint mean
    s_hc1_supply_temperature_setpoint__min                     DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint min
    s_hc1_supply_temperature_setpoint__max                     DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint max
    s_hc1_supply_temperature_setpoint__std                     DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint std
    s_hc1_supply_temperature_setpoint__first                   DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint first
    s_hc1_supply_temperature_setpoint__last                    DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint last
    s_hc1_supply_temperature_setpoint__delta                   DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint delta
    s_hc1_supply_temperature_setpoint__missing_count           INTEGER, -- s_hc1_supply_temperature_setpoint missing_count
    s_hc1_supply_temperature_setpoint__missing_rate            DOUBLE PRECISION, -- s_hc1_supply_temperature_setpoint missing_rate
    s_dhw_3way_valve_status__dominant                          TEXT, -- s_dhw_3way_valve_status dominant
    s_dhw_3way_valve_status__nunique                           INTEGER, -- s_dhw_3way_valve_status nunique
    s_dhw_3way_valve_status__change_count                      INTEGER, -- s_dhw_3way_valve_status change_count
    s_dhw_control_unit_mode__dominant                          TEXT, -- s_dhw_control_unit_mode dominant
    s_dhw_control_unit_mode__nunique                           INTEGER, -- s_dhw_control_unit_mode nunique
    s_dhw_control_unit_mode__change_count                      INTEGER, -- s_dhw_control_unit_mode change_count
    s_hc1_1_control_unit_mode__dominant                        TEXT, -- s_hc1_1_control_unit_mode dominant
    s_hc1_1_control_unit_mode__nunique                         INTEGER, -- s_hc1_1_control_unit_mode nunique
    s_hc1_1_control_unit_mode__change_count                    INTEGER, -- s_hc1_1_control_unit_mode change_count
    s_hc1_1_heating_pump_status__dominant                      TEXT, -- s_hc1_1_heating_pump_status dominant
    s_hc1_1_heating_pump_status__nunique                       INTEGER, -- s_hc1_1_heating_pump_status nunique
    s_hc1_1_heating_pump_status__change_count                  INTEGER, -- s_hc1_1_heating_pump_status change_count
    s_hc1_2_control_unit_mode__dominant                        TEXT, -- s_hc1_2_control_unit_mode dominant
    s_hc1_2_control_unit_mode__nunique                         INTEGER, -- s_hc1_2_control_unit_mode nunique
    s_hc1_2_control_unit_mode__change_count                    INTEGER, -- s_hc1_2_control_unit_mode change_count
    s_hc1_2_dhw_control_unit_mode__dominant                    TEXT, -- s_hc1_2_dhw_control_unit_mode dominant
    s_hc1_2_dhw_control_unit_mode__nunique                     INTEGER, -- s_hc1_2_dhw_control_unit_mode nunique
    s_hc1_2_dhw_control_unit_mode__change_count                INTEGER, -- s_hc1_2_dhw_control_unit_mode change_count
    s_hc1_2_heating_pump_status__dominant                      TEXT, -- s_hc1_2_heating_pump_status dominant
    s_hc1_2_heating_pump_status__nunique                       INTEGER, -- s_hc1_2_heating_pump_status nunique
    s_hc1_2_heating_pump_status__change_count                  INTEGER, -- s_hc1_2_heating_pump_status change_count
    s_hc1_3_control_unit_mode__dominant                        TEXT, -- s_hc1_3_control_unit_mode dominant
    s_hc1_3_control_unit_mode__nunique                         INTEGER, -- s_hc1_3_control_unit_mode nunique
    s_hc1_3_control_unit_mode__change_count                    INTEGER, -- s_hc1_3_control_unit_mode change_count
    s_hc1_3_heating_pump_status__dominant                      TEXT, -- s_hc1_3_heating_pump_status dominant
    s_hc1_3_heating_pump_status__nunique                       INTEGER, -- s_hc1_3_heating_pump_status nunique
    s_hc1_3_heating_pump_status__change_count                  INTEGER, -- s_hc1_3_heating_pump_status change_count
    s_hc1_control_unit_mode__dominant                          TEXT, -- s_hc1_control_unit_mode dominant
    s_hc1_control_unit_mode__nunique                           INTEGER, -- s_hc1_control_unit_mode nunique
    s_hc1_control_unit_mode__change_count                      INTEGER, -- s_hc1_control_unit_mode change_count
    s_hc1_heating_pump_status_setpoint__dominant               TEXT, -- s_hc1_heating_pump_status_setpoint dominant
    s_hc1_heating_pump_status_setpoint__nunique                INTEGER, -- s_hc1_heating_pump_status_setpoint nunique
    s_hc1_heating_pump_status_setpoint__change_count           INTEGER, -- s_hc1_heating_pump_status_setpoint change_count
    days_since_last_fault_event                                DOUBLE PRECISION, -- 이벤트 context
    days_since_last_task_event                                 DOUBLE PRECISION, -- 이벤트 context
    days_since_last_any_event                                  DOUBLE PRECISION, -- 이벤트 context
    post_fault_stabilization                                   BOOLEAN, -- 이벤트 context
    post_task_stabilization                                    BOOLEAN, -- 이벤트 context
    recent_regime_change_flag                                  BOOLEAN, -- 이벤트 context
    configuration_type                                         TEXT, -- 설비 context
    has_dhw                                                    BOOLEAN, -- 설비 context
    has_buffer_tank                                            BOOLEAN, -- 설비 context
    preprocessing_version                                      TEXT NOT NULL DEFAULT 'preprocessed_data_v1', -- 계약/lineage
    created_at                                                 TIMESTAMPTZ NOT NULL DEFAULT now(), -- 계약/lineage

    PRIMARY KEY (substation_id, window_start, window_end),
    CONSTRAINT preprocessed_windows_time_chk CHECK (window_start < window_end),
    CONSTRAINT preprocessed_windows_version_chk CHECK (preprocessing_version = 'preprocessed_data_v1')
);

CREATE INDEX IF NOT EXISTS idx_preprocessed_windows_sub_start
    ON preprocessed_windows (substation_id, window_start DESC);

COMMENT ON TABLE preprocessed_windows IS '피처 엔지니어링 전 표준 전처리 데이터. 1행은 기계실 1개 x 6시간 구간 1개.';
