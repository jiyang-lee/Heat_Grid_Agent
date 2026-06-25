# Agent Full Data Contract

## 1. 전처리 후 유지되는 operational base columns

총 29개다.

여기서 전처리는 불필요한 raw 컬럼 삭제, 결측/이상치 처리, 타입 정리까지를 의미한다.
따라서 아래 29개는 raw operational 원본에서 불필요 컬럼을 제거한 뒤, 타입 변환/결측 처리/이상치 처리를 거쳐 유지되는 최소 base columns다.

이 29개가 그대로 모델에 들어가는 최종 feature는 아니다.
이후 feature engineering/windowing 단계에서 이 29개를 기반으로 195개 모델 입력 feature가 생성된다.

- `outdoor_temperature`
- `p_dhw_control_valve_position`
- `p_dhw_return_temperature`
- `p_hc1_control_valve_position_setpoint`
- `p_hc1_return_temperature`
- `p_net_meter_energy`
- `p_net_meter_flow`
- `p_net_meter_heat_power`
- `p_net_meter_volume`
- `p_net_return_temperature`
- `p_net_supply_temperature`
- `s_dhw_3-way_valve_status`
- `s_dhw_control_unit_mode`
- `s_dhw_lower_storage_temperature`
- `s_dhw_supply_temperature`
- `s_dhw_supply_temperature_setpoint`
- `s_dhw_upper_storage_temperature`
- `s_hc1.1_control_unit_mode`
- `s_hc1.1_heating_pump_status`
- `s_hc1.2_control_unit_mode`
- `s_hc1.2_dhw_control unit_mode`
- `s_hc1.2_heating_pump_status`
- `s_hc1.3_control_unit_mode`
- `s_hc1.3_heating_pump_status`
- `s_hc1_control_unit_mode`
- `s_hc1_heating_pump_status_setpoint`
- `s_hc1_supply_temperature`
- `s_hc1_supply_temperature_setpoint`
- `timestamp`

## 2. 전처리에서 버릴 raw operational columns

총 21개다. 현재 파이프라인 기준으로 feature engineering과 모델 학습에 사용되지 않으므로 raw operational 전처리 단계에서 제외해도 된다.

- `p_dhw_return_temperature_setpoint`
- `p_hc1_return_temperature_setpoint`
- `s_dhw_upper_storage_temperature_setpoint`
- `s_hc1.1_control_valve_position`
- `s_hc1.1_return_temperature`
- `s_hc1.1_return_temperature_setpoint`
- `s_hc1.1_room_temperature_setpoint`
- `s_hc1.1_supply_temperature`
- `s_hc1.1_supply_temperature_setpoint`
- `s_hc1.2_control_valve_position`
- `s_hc1.2_return_temperature`
- `s_hc1.2_return_temperature_setpoint`
- `s_hc1.2_room_temperature_setpoint`
- `s_hc1.2_supply_temperature`
- `s_hc1.2_supply_temperature_setpoint`
- `s_hc1.3_control_valve_position`
- `s_hc1.3_return_temperature`
- `s_hc1.3_room_temperature_setpoint`
- `s_hc1.3_supply_temperature`
- `s_hc1.3_supply_temperature_setpoint`
- `s_hc1_room_temperature_setpoint`

## 3. 전처리 후 형식 변환/인코딩 결과 columns

이 섹션은 feature engineering이 아니라 전처리 산출물 기준이다.
전처리에는 타입 변환, 결측/이상치 처리, 문자열/범주형 인코딩 준비까지 포함한다.

따라서 아래는 feature engineering으로 새로 만든 파생 feature가 아니라, feature engineering 이전에 준비되는 입력 컬럼 구분이다.
컬럼 의미가 그대로 유지되는 base columns와, 문자열/범주형 값을 인코딩 대상으로 처리하는 columns를 나눈다.

### 3.1 형식 변환 후 그대로 유지되는 base columns

아래 컬럼들은 numeric 또는 datetime으로 정리된 뒤에도 컬럼 의미가 그대로 유지된다.
즉, 이 단계까지는 파생 feature가 아니라 전처리 후 base columns다.

- `timestamp`
- `outdoor_temperature`
- `p_dhw_control_valve_position`
- `p_dhw_return_temperature`
- `p_hc1_control_valve_position_setpoint`
- `p_hc1_return_temperature`
- `p_net_meter_energy`
- `p_net_meter_flow`
- `p_net_meter_heat_power`
- `p_net_meter_volume`
- `p_net_return_temperature`
- `p_net_supply_temperature`
- `s_dhw_lower_storage_temperature`
- `s_dhw_supply_temperature`
- `s_dhw_supply_temperature_setpoint`
- `s_dhw_upper_storage_temperature`
- `s_hc1_supply_temperature`
- `s_hc1_supply_temperature_setpoint`

### 3.2 인코딩 대상 raw/control columns

아래 컬럼들은 문자열/상태값으로 처리된다.
이 컬럼 자체를 numeric feature로 그대로 쓰는 것이 아니라, 결측값 처리와 dominant 상태 추출을 거친 뒤 one-hot 계열 컬럼으로 변환된다.

- `s_dhw_3-way_valve_status`
- `s_dhw_control_unit_mode`
- `s_hc1.1_control_unit_mode`
- `s_hc1.1_heating_pump_status`
- `s_hc1.2_control_unit_mode`
- `s_hc1.2_dhw_control unit_mode`
- `s_hc1.2_heating_pump_status`
- `s_hc1.3_control_unit_mode`
- `s_hc1.3_heating_pump_status`
- `s_hc1_control_unit_mode`
- `s_hc1_heating_pump_status_setpoint`

### 3.3 인코딩 대상 context columns

아래 컬럼들은 raw operational 센서 컬럼은 아니지만, 전처리/인코딩 단계에서 모델 입력에 사용할 수 있는 context 형태로 정리된다.

- `manufacturer`
- `configuration_type`
- `season_bucket`

### 3.4 전처리/인코딩 후 모델 입력에 남는 변환 계열

04 feature selection 이후 모델 입력으로 남은 변환 계열 feature는 다음 family로 정리된다.
이들은 raw 값을 그대로 둔 컬럼이 아니라, 전처리/인코딩 과정에서 모델이 읽을 수 있게 바뀐 컬럼이다.

- `derived_one_hot`: 44개
- `cyclic_time`: 6개
- `time_context`: 6개

## 4. 추가 context source

- `configuration_types.csv`: configuration_type
- `faults.csv`: fault_label, fault_event_id, estimated_lead_time_hours, risk labels
- `disturbances.csv`: maintenance/task event history, days_since_last_task_event
- `normal_events.csv`: normal reference windows
- `source_metadata`: manufacturer, substation_id, source_file

## 5. 전처리 규칙

- raw column pruning: operational raw 50개 중 불필요한 21개 제거
- `timestamp`: datetime으로 변환, invalid timestamp 제거, timestamp 기준 정렬
- numeric sensor columns: numeric 변환, 비정상 값/결측 처리
- control context columns: string 변환, 결측값은 `missing`으로 처리
- quality filter: 최소 row 수, missing rate, timestamp gap, leakage guard, normal reference filter 적용

## 6. feature engineering으로 생성된 모델 입력 feature columns

전처리 후 유지된 operational base columns 29개와 context source를 사용해 windowing/feature engineering을 수행한다.
여기서 말하는 feature engineering은 단순 타입 변환이 아니라, window 통계, 변화량, gap, 결측률, 시간 주기, event context, one-hot 결과처럼 모델 학습용으로 새로 구성된 feature 생성을 의미한다.

따라서 3.1의 base columns 자체는 feature engineering 결과로 보지 않는다.
04 feature selection 이후 모델 입력 feature는 195개로 고정된다.
family별 개수는 아래와 같다.

- `cyclic_time`: 6
- `derived_one_hot`: 44
- `event_context`: 2
- `sensor_numeric`: 137
- `time_context`: 6

### cyclic_time
- `dow_cos`
- `dow_sin`
- `doy_cos`
- `doy_sin`
- `hour_cos`
- `hour_sin`

### derived_one_hot
- `configuration_type__is__missing`
- `configuration_type__is__sh`
- `configuration_type__is__sh_dhw`
- `configuration_type__is__sh_dhw_with_sub_circuits`
- `configuration_type__is__sh_with_buffer_tank`
- `configuration_type__is__sh_with_sub_circuits`
- `manufacturer__is__manufacturer_1`
- `manufacturer__is__manufacturer_2`
- `s_dhw_3-way_valve_status__dominant__is__aus`
- `s_dhw_3-way_valve_status__dominant__is__ein`
- `s_dhw_3-way_valve_status__dominant__is__missing`
- `s_dhw_control_unit_mode__dominant__is__missing`
- `s_dhw_control_unit_mode__dominant__is__standby`
- `s_dhw_control_unit_mode__dominant__is__tag`
- `s_hc1.1_control_unit_mode__dominant__is__missing`
- `s_hc1.1_control_unit_mode__dominant__is__nacht`
- `s_hc1.1_control_unit_mode__dominant__is__tag`
- `s_hc1.1_heating_pump_status__dominant__is__ein`
- `s_hc1.1_heating_pump_status__dominant__is__missing`
- `s_hc1.2_control_unit_mode__dominant__is__missing`
- `s_hc1.2_control_unit_mode__dominant__is__nacht`
- `s_hc1.2_control_unit_mode__dominant__is__standby`
- `s_hc1.2_control_unit_mode__dominant__is__tag`
- `s_hc1.2_dhw_control unit_mode__dominant__is__missing`
- `s_hc1.2_dhw_control unit_mode__dominant__is__standby`
- `s_hc1.2_heating_pump_status__dominant__is__aus`
- `s_hc1.2_heating_pump_status__dominant__is__ein`
- `s_hc1.2_heating_pump_status__dominant__is__missing`
- `s_hc1.3_control_unit_mode__dominant__is__missing`
- `s_hc1.3_control_unit_mode__dominant__is__tag`
- `s_hc1.3_heating_pump_status__dominant__is__aus`
- `s_hc1.3_heating_pump_status__dominant__is__ein`
- `s_hc1.3_heating_pump_status__dominant__is__missing`
- `s_hc1_control_unit_mode__dominant__is__missing`
- `s_hc1_control_unit_mode__dominant__is__nacht`
- `s_hc1_control_unit_mode__dominant__is__standby`
- `s_hc1_control_unit_mode__dominant__is__tag`
- `s_hc1_heating_pump_status_setpoint__dominant__is__aus`
- `s_hc1_heating_pump_status_setpoint__dominant__is__ein`
- `s_hc1_heating_pump_status_setpoint__dominant__is__missing`
- `season_bucket__is__autumn`
- `season_bucket__is__spring`
- `season_bucket__is__summer`
- `season_bucket__is__winter`

### event_context
- `days_since_last_any_event`
- `days_since_last_task_event`

### sensor_numeric
- `extreme_change_count`
- `has_buffer_tank`
- `has_dhw`
- `max_timestamp_gap_minutes`
- `missing_count`
- `missing_rate`
- `network_temperature_gap__last`
- `network_temperature_gap__max_abs`
- `network_temperature_gap__mean`
- `outdoor_temperature__delta`
- `outdoor_temperature__first`
- `outdoor_temperature__last`
- `outdoor_temperature__max`
- `outdoor_temperature__mean`
- `outdoor_temperature__min`
- `outdoor_temperature__std`
- `p_hc1_return_temperature__delta`
- `p_hc1_return_temperature__first`
- `p_hc1_return_temperature__last`
- `p_hc1_return_temperature__max`
- `p_hc1_return_temperature__mean`
- `p_hc1_return_temperature__min`
- `p_hc1_return_temperature__std`
- `p_net_meter_energy__delta`
- `p_net_meter_energy__first`
- `p_net_meter_energy__last`
- `p_net_meter_energy__max`
- `p_net_meter_energy__mean`
- `p_net_meter_energy__min`
- `p_net_meter_energy__missing_count`
- `p_net_meter_energy__missing_rate`
- `p_net_meter_energy__std`
- `p_net_meter_flow__delta`
- `p_net_meter_flow__first`
- `p_net_meter_flow__last`
- `p_net_meter_flow__max`
- `p_net_meter_flow__mean`
- `p_net_meter_flow__min`
- `p_net_meter_flow__missing_count`
- `p_net_meter_flow__missing_rate`
- `p_net_meter_flow__std`
- `p_net_meter_heat_power__delta`
- `p_net_meter_heat_power__first`
- `p_net_meter_heat_power__last`
- `p_net_meter_heat_power__max`
- `p_net_meter_heat_power__mean`
- `p_net_meter_heat_power__min`
- `p_net_meter_heat_power__missing_count`
- `p_net_meter_heat_power__missing_rate`
- `p_net_meter_heat_power__std`
- `p_net_meter_volume__delta`
- `p_net_meter_volume__first`
- `p_net_meter_volume__last`
- `p_net_meter_volume__max`
- `p_net_meter_volume__mean`
- `p_net_meter_volume__min`
- `p_net_meter_volume__missing_count`
- `p_net_meter_volume__missing_rate`
- `p_net_meter_volume__std`
- `p_net_return_temperature__delta`
- `p_net_return_temperature__first`
- `p_net_return_temperature__last`
- `p_net_return_temperature__max`
- `p_net_return_temperature__mean`
- `p_net_return_temperature__min`
- `p_net_return_temperature__missing_count`
- `p_net_return_temperature__missing_rate`
- `p_net_return_temperature__std`
- `p_net_supply_temperature__delta`
- `p_net_supply_temperature__first`
- `p_net_supply_temperature__last`
- `p_net_supply_temperature__max`
- `p_net_supply_temperature__mean`
- `p_net_supply_temperature__min`
- `p_net_supply_temperature__missing_count`
- `p_net_supply_temperature__missing_rate`
- `p_net_supply_temperature__std`
- `row_count`
- `s_hc1_supply_temperature__delta`
- `s_hc1_supply_temperature__first`
- `s_hc1_supply_temperature__last`
- `s_hc1_supply_temperature__max`
- `s_hc1_supply_temperature__mean`
- `s_hc1_supply_temperature__min`
- `s_hc1_supply_temperature__std`
- `s_hc1_supply_temperature_setpoint__missing_count`
- `s_hc1_supply_temperature_setpoint__missing_rate`
- `timestamp_gap_count`
- `hc1_supply_temperature_gap__last`
- `hc1_supply_temperature_gap__max_abs`
- `hc1_supply_temperature_gap__mean`
- `s_hc1_supply_temperature_setpoint__delta`
- `s_hc1_supply_temperature_setpoint__first`
- `s_hc1_supply_temperature_setpoint__last`
- `s_hc1_supply_temperature_setpoint__max`
- `s_hc1_supply_temperature_setpoint__mean`
- `s_hc1_supply_temperature_setpoint__min`
- `s_hc1_supply_temperature_setpoint__std`
- `s_dhw_lower_storage_temperature__delta`
- `s_dhw_lower_storage_temperature__first`
- `s_dhw_lower_storage_temperature__last`
- `s_dhw_lower_storage_temperature__max`
- `s_dhw_lower_storage_temperature__mean`
- `s_dhw_lower_storage_temperature__min`
- `s_dhw_lower_storage_temperature__missing_count`
- `s_dhw_lower_storage_temperature__missing_rate`
- `s_dhw_lower_storage_temperature__std`
- `s_dhw_upper_storage_temperature__delta`
- `s_dhw_upper_storage_temperature__first`
- `s_dhw_upper_storage_temperature__last`
- `s_dhw_upper_storage_temperature__max`
- `s_dhw_upper_storage_temperature__mean`
- `s_dhw_upper_storage_temperature__min`
- `s_dhw_upper_storage_temperature__missing_count`
- `s_dhw_upper_storage_temperature__missing_rate`
- `s_dhw_upper_storage_temperature__std`
- `s_dhw_supply_temperature__delta`
- `s_dhw_supply_temperature__first`
- `s_dhw_supply_temperature__last`
- `s_dhw_supply_temperature__max`
- `s_dhw_supply_temperature__mean`
- `s_dhw_supply_temperature__min`
- `s_dhw_supply_temperature__missing_count`
- `s_dhw_supply_temperature__missing_rate`
- `s_dhw_supply_temperature__std`
- `dhw_supply_temperature_gap__last`
- `dhw_supply_temperature_gap__max_abs`
- `dhw_supply_temperature_gap__mean`
- `s_dhw_supply_temperature_setpoint__delta`
- `s_dhw_supply_temperature_setpoint__first`
- `s_dhw_supply_temperature_setpoint__last`
- `s_dhw_supply_temperature_setpoint__max`
- `s_dhw_supply_temperature_setpoint__mean`
- `s_dhw_supply_temperature_setpoint__min`
- `s_dhw_supply_temperature_setpoint__missing_count`
- `s_dhw_supply_temperature_setpoint__missing_rate`
- `s_dhw_supply_temperature_setpoint__std`

### time_context
- `day_of_week`
- `day_of_year`
- `hour_of_day`
- `is_heating_season`
- `is_weekend`
- `month`

## 7. metadata columns

- `manufacturer`: identifier, `str`
- `substation_id`: identifier, `int64`
- `source_file`: source_trace, `str`
- `window_start`: time_range, `str`
- `window_end`: time_range, `str`
- `main_missing_sensors`: explanation_text, `str`
- `main_changed_sensors`: explanation_text, `str`
- `season_bucket`: time_context, `str`
- `label`: target, `str`
- `fault_label`: target_context, `str`
- `fault_event_id`: event_identifier, `float64`
- `estimated_lead_time_hours`: lead_time_target, `float64`
- `normal_event_related`: label_context, `bool`
- `maintenance_related`: interpretation_context, `bool`
- `disturbance_count`: interpretation_context, `int64`
- `leakage_blocked_fault_count`: leakage_guard, `int64`
- `window_source_type`: training_control, `str`
- `use_for_supervised_training`: training_control, `bool`
- `configuration_type`: configuration_context, `str`
- `normal_reference_group`: configuration_context, `str`
- `s_hc1_control_unit_mode__dominant`: control_context, `str`
- `s_dhw_control_unit_mode__dominant`: control_context, `str`
- `s_hc1_heating_pump_status_setpoint__dominant`: control_context, `str`
- `s_dhw_3-way_valve_status__dominant`: control_context, `str`
- `s_hc1.2_heating_pump_status__dominant`: control_context, `str`
- `s_hc1.3_heating_pump_status__dominant`: control_context, `str`
- `s_hc1.1_control_unit_mode__dominant`: control_context, `str`
- `s_hc1.2_control_unit_mode__dominant`: control_context, `str`
- `s_hc1.2_dhw_control unit_mode__dominant`: control_context, `str`
- `s_hc1.1_heating_pump_status__dominant`: control_context, `str`
- `s_hc1.3_control_unit_mode__dominant`: control_context, `str`
- `split_time_based`: evaluation_split, `str`
- `split_substation_based`: evaluation_split, `str`
- `split_regime_based`: evaluation_split, `str`
- `normal_reference_outlier`: training_control, `bool`
- `normal_reference_outlier_count`: training_control, `int64`
- `normal_reference_filter_reason`: training_control, `str`

## 8. 머신러닝을 통해 나온 결과 columns

- `anomaly_score`
- `anomaly_threshold`
- `anomaly_label`
- `risk_score`
- `risk_probability`
- `risk_level`
- `risk_level_calibrated`
- `main_abnormal_features`
- `related_fault_history`
- `related_disturbance_history`
- `model_explanation_features`
- `predicted_lead_time_bucket`
- `predicted_lead_time_confidence`
- `predicted_lead_time_index`
- `lead_time_bucket_distance`
- `leadtime_prob_0-24h`
- `leadtime_prob_1-3d`
- `leadtime_prob_3-7d`

risk 기준 산출물: `data/processed/ml_risk/lgbm_risk_scores_calibrated.csv`

leadtime 기준 산출물: `data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv`

## 9. Priority Engine 입력 columns

- `manufacturer`
- `substation_id`
- `window_start`
- `window_end`
- `anomaly_score`
- `risk_score`
- `risk_probability`
- `risk_level_calibrated`
- `predicted_lead_time_bucket`
- `predicted_lead_time_confidence`
- `leadtime_prob_0-24h`
- `leadtime_prob_1-3d`
- `leadtime_prob_3-7d`
- `lead_time_bucket_distance`
- `days_since_last_fault_event`
- `days_since_last_task_event`
- `days_since_last_any_event`

## 10. Priority Engine 출력 columns

- `risk_base_score`
- `risk_probability_component_score`
- `leadtime_bucket_base_score`
- `leadtime_confidence_multiplier`
- `leadtime_component_score`
- `anomaly_component_score`
- `history_adjustment_score`
- `history_adjustment_reason`
- `priority_score`
- `priority_level`
- `priority_reason`
- `engine_version`

priority 기준 산출물: `data/processed/ml_priority/priority_engine_scores_tuned.csv`

