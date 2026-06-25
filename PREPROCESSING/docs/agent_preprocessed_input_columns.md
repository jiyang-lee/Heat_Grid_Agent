# Agent Preprocessed Input Columns

이 문서는 Agent/DB 팀에 넘길 **feature engineering 이전 입력 컬럼 기준**만 정리한다.

여기서 전처리는 다음을 의미한다.

- 불필요 raw column 삭제
- 데이터 타입 변환
- 결측/이상치 처리
- 문자열/범주형 column의 인코딩 준비

따라서 이 문서의 컬럼들은 **모델 입력 feature 195개가 아니다**.
아래 컬럼들은 feature engineering/windowing 이전에 보존하거나 정리해야 하는 입력 컬럼이다.

## 1. 전체 요약

- operational raw 전체 후보: 50개
- 전처리 후 유지되는 operational base columns: 29개
- 전처리에서 제외하는 operational raw columns: 21개
- 형식 변환 후 의미가 그대로 유지되는 base columns: 18개
- 인코딩 대상 raw/control columns: 11개
- source metadata columns: 3개
- context source tables: 4개

source별로 보존해야 하는 항목은 다음이다.

- operational table: 29개
- source metadata: 3개
- `configuration_types.csv`: 2개
- `faults.csv`: 12개
- `disturbances.csv`: 3개
- `normal_events.csv`: 6개

주의: context source table들은 서로 다른 테이블이므로 `substation ID`, `Event ID`처럼 이름이 겹쳐도 각 source별로 유지한다.

## 2. 전처리 후 유지되는 operational base columns 29개

아래 29개는 raw operational 원본 50개 중 불필요한 21개를 제거한 뒤에도 유지되는 기본 operational columns다.
이 컬럼들은 타입 변환, 결측/이상치 처리를 거친 뒤 feature engineering/windowing 입력으로 사용된다.

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

## 3. 형식 변환 후 그대로 유지되는 base columns 18개

아래 컬럼들은 전처리 후에도 컬럼 의미가 그대로 유지된다.
즉, numeric 또는 datetime으로 정리되지만, 아직 feature engineering으로 새로 파생된 컬럼은 아니다.

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

## 4. 인코딩 대상 raw/control columns 11개

아래 컬럼들은 문자열/상태값으로 처리한다.
이 컬럼 자체를 numeric 모델 feature로 그대로 쓰는 것이 아니라, 결측값 처리와 window별 dominant 상태 추출을 거친 뒤 one-hot 계열 feature로 변환한다.

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

## 5. source metadata columns 3개

아래 컬럼들은 operational CSV 내부 센서 컬럼이 아니라, 파일 경로/파일명/source metadata에서 유지해야 하는 식별자다.

- `manufacturer`
- `substation_id`
- `source_file`

## 6. context source tables

아래 context source들은 feature engineering 이전에 라벨, 설비 구성, 정상 기준, 이력 정보를 만들기 위해 유지해야 한다.

### 6.1 `configuration_types.csv`

- `substation ID`
- `configuration_type`

사용 목적:

- `substation_id` 기준으로 operational data에 설비 구성 정보를 결합한다.
- `configuration_type`은 이후 인코딩 대상 context column이다.

### 6.2 `faults.csv`

- `Event ID`
- `substation ID`
- `Report date`
- `Problem EN`
- `Event description EN`
- `Possible anomaly start`
- `Possible anomaly end`
- `Training start`
- `Training end`
- `efd_possible`
- `Fault label`
- `Monitoring potential`

사용 목적:

- `fault_event_id`
- `fault_label`
- `estimated_lead_time_hours`
- risk label
- leadtime label
- fault window alignment

### 6.3 `disturbances.csv`

- `substation ID`
- `Event start`
- `type`

사용 목적:

- 정비/작업 이력 계산
- `maintenance_related`
- `disturbance_count`
- `days_since_last_task_event`
- `days_since_last_any_event`

### 6.4 `normal_events.csv`

- `Event ID`
- `substation ID`
- `Event start`
- `Event end`
- `Training start`
- `Training end`

사용 목적:

- normal reference window 생성
- 정상 기준 학습 구간 정의
- `normal_event_related`
- `normal_reference_group`
- normal reference filter

## 7. feature engineering 이후 컬럼은 이 문서에서 제외

아래 항목들은 이 문서의 범위가 아니다.

- window 통계 feature
- 변화량 feature
- gap feature
- missing rate/count feature
- cyclic time feature
- one-hot 결과 feature
- event distance feature
- 모델 결과 컬럼
- priority score 컬럼

이 항목들은 `agent_full_data_contract.md`의 feature engineering, ML output, Priority Engine 섹션에서 관리한다.
