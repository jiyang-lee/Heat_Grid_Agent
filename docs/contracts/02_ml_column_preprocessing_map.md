# HeatGrid ML Column Preprocessing Map

기준 소스:
- `PREPROCESSING/osj/03_preprocess_windows.ipynb`
- `PREPROCESSING/osj/04_feature_selection.ipynb`
- 보조 문서: `PREPROCESSING/docs/agent_full_data_contract.md`, `PREPROCESSING/docs/agent_preprocessed_input_columns.md`, `PREPROCESSING/docs/agent_feature_contract.md`

이 문서는 컬럼별로 어떤 전처리가 적용되는지 기록한 맵이다.

## 1) 원천 운영 컬럼

### 1.1 유지되는 raw operational 컬럼 29개

| 원본 컬럼 | 전처리 종류 | 적용 단계 | 결과 컬럼 / 상태 | 비고 |
|---|---|---|---|---|
| `timestamp` | datetime 파싱, invalid 제거, 정렬, 중복 제거 | 03 | `timestamp` | 윈도우 기준 컬럼 |
| `outdoor_temperature` | numeric 변환, window ffill/bfill/median fill, 통계 생성 | 03 | `outdoor_temperature__mean/min/max/std/first/last/delta/missing_count/missing_rate` | base sensor |
| `p_dhw_control_valve_position` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | base sensor |
| `p_dhw_return_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | base sensor |
| `p_hc1_control_valve_position_setpoint` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | base sensor |
| `p_hc1_return_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | base sensor |
| `p_net_meter_energy` | numeric 변환, cumulative check, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + `sensor_error_candidate_count` | 누적값 감소 금지 |
| `p_net_meter_flow` | numeric 변환, negative check, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | 유량 음수 후보 |
| `p_net_meter_heat_power` | numeric 변환, negative check, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | 열량/출력 음수 후보 |
| `p_net_meter_volume` | numeric 변환, cumulative check, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | 누적값 감소 금지 |
| `p_net_return_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + gap feature | 네트워크 gap 계산에 사용 |
| `p_net_supply_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + gap feature | 네트워크 gap 계산에 사용 |
| `s_dhw_3-way_valve_status` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_dhw_3-way_valve_status__dominant`, one-hot | control context |
| `s_dhw_control_unit_mode` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_dhw_control_unit_mode__dominant`, one-hot | control context |
| `s_dhw_lower_storage_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | base sensor |
| `s_dhw_supply_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + `dhw_supply_temperature_gap__*` | gap feature |
| `s_dhw_supply_temperature_setpoint` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + `dhw_supply_temperature_gap__*` | gap feature |
| `s_dhw_upper_storage_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 | base sensor |
| `s_hc1.1_control_unit_mode` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.1_control_unit_mode__dominant`, one-hot | control context |
| `s_hc1.1_heating_pump_status` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.1_heating_pump_status__dominant`, one-hot | control context |
| `s_hc1.2_control_unit_mode` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.2_control_unit_mode__dominant`, one-hot | control context |
| `s_hc1.2_dhw_control unit_mode` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.2_dhw_control unit_mode__dominant`, one-hot | 원본 이름에 공백 포함 |
| `s_hc1.2_heating_pump_status` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.2_heating_pump_status__dominant`, one-hot | control context |
| `s_hc1.3_control_unit_mode` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.3_control_unit_mode__dominant`, one-hot | control context |
| `s_hc1.3_heating_pump_status` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1.3_heating_pump_status__dominant`, one-hot | control context |
| `s_hc1_control_unit_mode` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1_control_unit_mode__dominant`, one-hot | control context |
| `s_hc1_heating_pump_status_setpoint` | string 정리, missing 채움, dominant 추출, 변화횟수 계산 | 03 / 04 | `s_hc1_heating_pump_status_setpoint__dominant`, one-hot | control context |
| `s_hc1_supply_temperature` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + `hc1_supply_temperature_gap__*` | gap feature |
| `s_hc1_supply_temperature_setpoint` | numeric 변환, 보간, 통계 생성 | 03 | 동일한 suffix 통계 + `hc1_supply_temperature_gap__*` | gap feature |

### 1.2 전처리에서 제외되는 raw operational 컬럼 21개

| 원본 컬럼 | 제외 이유 | 적용 단계 | 결과 컬럼 / 상태 | 비고 |
|---|---|---|---|---|
| `p_dhw_return_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `p_hc1_return_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_dhw_upper_storage_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.1_control_valve_position` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.1_return_temperature` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.1_return_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.1_room_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.1_supply_temperature` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.1_supply_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.2_control_valve_position` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.2_return_temperature` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.2_return_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.2_room_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.2_supply_temperature` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.2_supply_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.3_control_valve_position` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.3_return_temperature` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.3_room_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.3_supply_temperature` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1.3_supply_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |
| `s_hc1_room_temperature_setpoint` | feature engineering 대상 아님 | 04 제외 기준 | 제거 | raw base로 미사용 |

## 2) 03 단계의 파생 컬럼

### 2.1 센서 통계

각 numeric sensor에 대해 다음이 생성된다.

| 전처리 종류 | 생성 컬럼 |
|---|---|
| 윈도우 통계 | `__mean`, `__min`, `__max`, `__std`, `__first`, `__last`, `__delta` |
| 결측 정보 | `__missing_count`, `__missing_rate` |
| 품질 정보 | `missing_count`, `missing_rate`, `sensor_error_candidate_count`, `extreme_change_count`, `timestamp_gap_count`, `max_timestamp_gap_minutes` |

### 2.2 gap 계열

| 원본 컬럼 | 전처리 종류 | 결과 컬럼 |
|---|---|---|
| `s_hc1_supply_temperature` + `s_hc1_supply_temperature_setpoint` | 차분 | `hc1_supply_temperature_gap__mean`, `hc1_supply_temperature_gap__max_abs`, `hc1_supply_temperature_gap__last` |
| `s_dhw_supply_temperature` + `s_dhw_supply_temperature_setpoint` | 차분 | `dhw_supply_temperature_gap__mean`, `dhw_supply_temperature_gap__max_abs`, `dhw_supply_temperature_gap__last` |
| `p_net_supply_temperature` + `p_net_return_temperature` | 차분 | `network_temperature_gap__mean`, `network_temperature_gap__max_abs`, `network_temperature_gap__last` |

### 2.3 time / event context

| 전처리 종류 | 결과 컬럼 |
|---|---|
| 시간대 파생 | `hour_of_day`, `day_of_week`, `day_of_year`, `month` |
| 이산 상태 | `is_weekend`, `is_heating_season`, `season_bucket` |
| 순환 인코딩 | `hour_sin`, `hour_cos`, `dow_sin`, `dow_cos`, `doy_sin`, `doy_cos` |
| 이벤트 거리 | `days_since_last_fault_event`, `days_since_last_task_event`, `days_since_last_any_event` |
| 안정화 플래그 | `post_fault_stabilization`, `post_task_stabilization`, `recent_regime_change_flag` |

## 3) 02 라벨 정렬용 컬럼

| 원본 컬럼 | 전처리 종류 | 적용 단계 | 결과 컬럼 / 상태 | 비고 |
|---|---|---|---|---|
| `report_date` | datetime 파싱 | 02 | label cutoff | fault lead time 기준 |
| `Possible anomaly start` / `Possible anomaly end` | datetime 파싱 | 02 | fault candidate window | fault window 후보 |
| `Training start` / `Training end` | datetime 파싱 | 02 | normal candidate window | normal reference |
| `Event start` / `Event end` | datetime 파싱 | 02 | disturbance / normal alignment | 이력 정렬 |
| `manufacturer`, `substation_id` | 식별자 정리 | 02 | alignment join key | 운영 CSV와 라벨 매칭 |

## 4) 04 feature selection 전처리

### 4.1 metadata 분리

| 컬럼 | 전처리 종류 | 적용 단계 | 결과 컬럼 / 상태 | 비고 |
|---|---|---|---|---|
| `manufacturer`, `substation_id`, `source_file` | metadata 분리 | 04 | metadata 유지 | 식별자 |
| `window_start`, `window_end` | metadata 분리 | 04 | metadata 유지 | 시간 범위 |
| `label`, `fault_label`, `fault_event_id`, `estimated_lead_time_hours` | target/context 분리 | 04 | metadata 유지 | supervised target 관련 |
| `main_missing_sensors`, `main_changed_sensors` | 설명 텍스트 유지 | 04 | metadata 유지 | explainability |
| `normal_event_related`, `maintenance_related`, `disturbance_count`, `leakage_blocked_fault_count` | 평가/해석 보조 | 04 | metadata 유지 | 모델 입력 제외 |
| `window_source_type`, `use_for_supervised_training`, `split_time_based`, `split_substation_based`, `split_regime_based` | 학습 제어 / split | 04 | metadata 유지 | leakage control |
| `configuration_type`, `normal_reference_group`, `season_bucket` | context 분리 | 04 | metadata 유지 | categorical source |
| `normal_reference_outlier`, `normal_reference_outlier_count`, `normal_reference_filter_reason` | normal filter metadata | 04 | metadata 유지 | audit / control |

### 4.2 one-hot 파생

| source column | 전처리 종류 | 적용 단계 | 결과 컬럼 / 상태 | 비고 |
|---|---|---|---|---|
| `manufacturer` | one-hot | 04 | `manufacturer__is__manufacturer_1`, `manufacturer__is__manufacturer_2` | train category 고정 |
| `configuration_type` | one-hot | 04 | `configuration_type__is__...` | low-cardinality만 |
| `season_bucket` | one-hot | 04 | `season_bucket__is__spring/summer/autumn/winter` | time context |
| `*_dominant` | one-hot | 04 | `*_dominant__is__...` | control/status dominant |

### 4.3 결측 대체

| 컬럼 타입 | 전처리 종류 | 적용 단계 | 결과 컬럼 / 상태 | 규칙 |
|---|---|---|---|---|
| bool | mode | 04 | selected feature imputed | non-null mode |
| numeric | median | 04 | selected feature imputed | train median |
| categorical 파생 | one-hot 기준 생성 | 04 | 0/1 | missing은 `missing`으로 정규화 |

## 5) 코드와 문서의 차이 메모

- 기존 문서에는 `selected feature 195`, `metadata 37`, `catalog 259`가 기준값으로 적혀 있다.
- 현재 실제 코드 확인 결과, 03/04의 전처리 흐름은 이 문서의 분류와 일치한다.
- 숫자 카운트는 문서/노트북 버전에 따라 일부 표현 차이가 있을 수 있으니, 최종 산출물 저장 후 `feature_columns.csv`와 `metadata_columns.csv`를 다시 맞추는 것이 안전하다.
