# Agent Required Raw Columns

## 결론

전처리를 불필요 raw 컬럼 삭제, 결측/이상치 처리, 타입 정리까지로 정의하면 raw operational column union 50개 중 전처리 후 유지할 raw 컬럼은 29개다.

이 29개는 그대로 모델에 들어가는 최종 feature가 아니다. 이후 feature engineering/windowing을 통해 195개 모델 입력 feature로 확장된다.

## 전처리 후 DB에 유지할 raw operational columns

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

## 전처리에서 제외해도 되는 raw operational columns

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

## 추가로 필요한 context source

- `manufacturer`: 파일 경로 또는 source metadata에서 유지
- `substation_id`: 파일명 또는 source metadata에서 유지
- `source_file`: 추적용 source metadata
- `configuration_types.csv`: `configuration_type` 생성에 필요
- `faults.csv`: fault label, risk label, event distance 생성에 필요
- `disturbances.csv`: task/disturbance 이력 및 event distance 생성에 필요
- `normal_events.csv`: normal reference 구간 정의에 필요

## 단계 구분

- 전처리: 불필요 raw 컬럼 삭제, 결측/이상치 처리, 타입 정리
- feature engineering/windowing: 전처리 후 유지된 raw 29개를 기반으로 window 통계, 변화량, one-hot, 시간 주기 feature 생성
- 04 feature selection: selected feature 195개 고정
- 05~07: raw를 직접 읽지 않고 03/04/06 산출물을 사용

## 주의

최종 모델 feature만 보면 26개 raw로 보일 수 있지만, 03 전처리 단계에서 `p_dhw_return_temperature`, `p_hc1_control_valve_position_setpoint`, `p_dhw_control_valve_position`도 사용한다.

따라서 DB 원천 보존 기준은 26개가 아니라 29개로 보는 것이 맞다.
