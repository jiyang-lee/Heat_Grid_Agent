# HeatGrid ML Stage Column Contract

기준 소스:
- `PREPROCESSING/osj/00_load_dataset.ipynb`
- `PREPROCESSING/osj/01_raw_inspection.ipynb`
- `PREPROCESSING/osj/02_label_alignment.ipynb`
- `PREPROCESSING/osj/03_preprocess_windows.ipynb`
- `PREPROCESSING/osj/04_feature_selection.ipynb`
- 대응 문서: `PREPROCESSING/docs/*.md`

이 문서는 `data json contract`에 해당하는 단계별 컬럼 사용 계약을 표로 정리한 것이다.

## 1) 단계별 요약

| 단계 | 입력 | 핵심 사용 컬럼 / 그룹 | 생성 / 유지 컬럼 | 제외 / 필터 | 출력 산출물 |
|---|---|---|---|---|---|
| 00 데이터 준비 | PreDist v2, XAI4HEAT SCADA 원천 파일 | 파일 경로, 디렉터리 구조 | 로컬 raw data 트리 | 원천 데이터는 저장소에 미포함 | `data/raw/...` |
| 01 원천 구조 확인 | manufacturer 1/2 운영 CSV, `faults.csv`, `normal_events.csv`, `disturbances.csv`, `feature_descriptions.csv`, `configuration_types.csv` | 전체 원천 컬럼, timestamp, 결측 요약, 제조사별 컬럼 존재 여부 | 컬럼 카탈로그, 결측 요약, 공통/전용 컬럼 후보 | 아직 학습용 컬럼 제거 없음 | 구조 점검 표, 결측 표 |
| 02 라벨 정렬 | `operational_coverage.csv`, `fault_alignment.csv`, `normal_alignment.csv`, `disturbance_alignment.csv`, 운영 CSV | `manufacturer`, `substation_id`, `timestamp`, `report_date`, `window_start`, `window_end`, `event_start`, `event_end`, `Training start/end` | `is_usable`, 정렬된 fault/normal/disturbance alignment | 운영 범위 밖, window 생성 불가, row 없는 구간 | `data/processed/label_alignment/*.csv` |
| 03 윈도우 생성 | 02의 정렬 결과 + 운영 CSV + `configuration_types.csv` | `timestamp`, `CORE_SENSOR_COLUMNS`, control/status 컬럼, 이벤트 이력, 구성정보 | 6시간 윈도우 feature, label/context, split 후보 | irrelevant interval, invalid timestamp row, timestamp duplicate | `data/processed/ml_windows/ml_window_dataset.csv` |
| 04 feature selection | 03의 `ml_window_dataset.csv` | strict/relaxed 후보, metadata, numeric/bool candidate, categorical candidate | 195개 선택 feature, 37개 metadata, imputation table, categorical map | non-numeric, high-missing, constant, one-sided manufacturer coverage | `data/processed/ml_features/*.csv` |

## 2) 03 단계에서 실제로 쓰는 컬럼

### 2.1 운영 시계열

| 그룹 | 컬럼 |
|---|---|
| timestamp | `timestamp` |
| 수치 센서 17개 | `outdoor_temperature`, `s_hc1_supply_temperature`, `s_hc1_supply_temperature_setpoint`, `s_dhw_supply_temperature`, `s_dhw_supply_temperature_setpoint`, `p_hc1_return_temperature`, `p_dhw_return_temperature`, `s_dhw_upper_storage_temperature`, `s_dhw_lower_storage_temperature`, `p_net_meter_energy`, `p_net_meter_volume`, `p_net_meter_heat_power`, `p_net_meter_flow`, `p_net_supply_temperature`, `p_net_return_temperature`, `p_hc1_control_valve_position_setpoint`, `p_dhw_control_valve_position` |
| control/status 컬럼 | `s_dhw_3-way_valve_status`, `s_dhw_control_unit_mode`, `s_hc1.1_control_unit_mode`, `s_hc1.1_heating_pump_status`, `s_hc1.2_control_unit_mode`, `s_hc1.2_dhw_control unit_mode`, `s_hc1.2_heating_pump_status`, `s_hc1.3_control_unit_mode`, `s_hc1.3_heating_pump_status`, `s_hc1_control_unit_mode`, `s_hc1_heating_pump_status_setpoint` |

### 2.2 외부 컨텍스트

| 그룹 | 컬럼 |
|---|---|
| 라벨 정렬 | `report_date`, `Possible anomaly start`, `Possible anomaly end`, `Training start`, `Training end`, `Event start`, `Event end` |
| 설비 구성 | `substation ID`, `configuration_type` |
| 이벤트 이력 | `fault_label`, `event_id`, `disturbance type` |

### 2.3 03 생성 컬럼

| 생성 컬럼 | 의미 |
|---|---|
| `row_count`, `expected_row_count`, `median_interval_minutes` | 윈도우 품질 / 샘플링 기준 |
| `invalid_timestamp_rows_in_file`, `timestamp_gap_count`, `max_timestamp_gap_minutes` | 원천 시계열 품질 |
| `missing_count`, `missing_rate` | 윈도우 전체 결측 요약 |
| `sensor_error_candidate_count`, `extreme_change_count` | 이상치 후보 / 급격 변화 카운트 |
| `*_mean`, `*_min`, `*_max`, `*_std`, `*_first`, `*_last`, `*_delta`, `*_missing_count`, `*_missing_rate` | 센서별 윈도우 통계 |
| `hc1_supply_temperature_gap__*`, `dhw_supply_temperature_gap__*`, `network_temperature_gap__*` | 설정값 대비 편차 / 네트워크 온도 차이 |
| `hour_of_day`, `day_of_week`, `day_of_year`, `month`, `is_weekend`, `is_heating_season`, `season_bucket`, `hour_sin/cos`, `dow_sin/cos`, `doy_sin/cos` | 시간 문맥 |
| `*_dominant`, `*_nunique`, `*_change_count` | control/status 문맥 |
| `days_since_last_fault_event`, `days_since_last_task_event`, `days_since_last_any_event`, `post_fault_stabilization`, `post_task_stabilization`, `recent_regime_change_flag` | 이벤트 문맥 |
| `label`, `fault_label`, `fault_event_id`, `estimated_lead_time_hours`, `normal_event_related`, `maintenance_related`, `disturbance_count`, `leakage_blocked_fault_count`, `window_source_type`, `use_for_supervised_training` | 라벨 / 학습 제어 |
| `configuration_type`, `has_dhw`, `has_buffer_tank`, `normal_reference_group` | 설비 구성 문맥 |

## 3) 04 단계에서 실제로 쓰는 컬럼

| 구분 | 컬럼 |
|---|---|
| metadata | `manufacturer`, `substation_id`, `source_file`, `window_start`, `window_end`, `main_missing_sensors`, `main_changed_sensors`, `label`, `fault_label`, `fault_event_id`, `estimated_lead_time_hours`, `normal_event_related`, `maintenance_related`, `disturbance_count`, `leakage_blocked_fault_count`, `window_source_type`, `use_for_supervised_training`, `normal_reference_outlier`, `normal_reference_outlier_count`, `normal_reference_filter_reason`, `configuration_type`, `normal_reference_group`, `season_bucket`, `split_time_based`, `split_substation_based`, `split_regime_based` |
| categorical source | `manufacturer`, `configuration_type`, `season_bucket`, `*_dominant` |
| numeric/bool candidate | metadata를 제외한 03 산출 컬럼 중 numeric/bool |
| selected feature | 195개 최종 feature |
| imputation source | selected feature의 train median / mode |

## 4) 실제 계약에서 중요한 점

- 03은 raw 센서값을 그대로 두지 않고 윈도우 통계로 바꾼다.
- 04는 raw가 아니라 03 산출물에서 feature/metadata를 다시 분리한다.
- `unlabeled`는 baseline 학습 대상이 아니다.
- `data_quality_issue == True`는 strict baseline에서 제외한다.
- one-hot 파생은 train split 기준 category만 사용한다.
