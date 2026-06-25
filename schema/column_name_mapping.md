# 컬럼명 정규화 매핑 (raw → DB)

## 왜 정규화하는가

raw operational 컬럼명에는 `.`(점)과 공백이 들어 있다.
예: `s_hc1.1_control_unit_mode`, `s_hc1.2_dhw_control unit_mode`

이런 이름은 PostgreSQL에서 식별자로 쓰려면 매 쿼리마다 큰따옴표로 감싸야 하고(`"s_hc1.1_..."`),
점은 스키마/테이블 구분자로 오인될 수 있어 버그를 유발한다.

따라서 DB에서는 snake_case로 정규화하고, 적재 파이프라인이 아래 매핑으로 변환한다.

- `.` → `_`
- 공백 → `_`
- `-` → `` (제거; `3-way` → `3way`)
- 그 외 의미는 그대로 유지

근거: 유지보수성/디버깅 용이성(따옴표 escape 제거), ML feature 계약과의 정합성.

## sensor_readings — 정규화가 필요한 컬럼

| raw 컬럼명 | DB 컬럼명 |
|---|---|
| `timestamp` | `ts` |
| `s_dhw_3-way_valve_status` | `s_dhw_3way_valve_status` |
| `s_hc1.1_control_unit_mode` | `s_hc1_1_control_unit_mode` |
| `s_hc1.1_heating_pump_status` | `s_hc1_1_heating_pump_status` |
| `s_hc1.2_control_unit_mode` | `s_hc1_2_control_unit_mode` |
| `s_hc1.2_dhw_control unit_mode` | `s_hc1_2_dhw_control_unit_mode` |
| `s_hc1.2_heating_pump_status` | `s_hc1_2_heating_pump_status` |
| `s_hc1.3_control_unit_mode` | `s_hc1_3_control_unit_mode` |
| `s_hc1.3_heating_pump_status` | `s_hc1_3_heating_pump_status` |

## sensor_readings — 이름 그대로 유지되는 컬럼 (정규화 불필요)

숫자 센서 17개 + 점/공백 없는 제어 센서 2개는 raw 이름과 동일:

`outdoor_temperature`, `p_dhw_control_valve_position`, `p_dhw_return_temperature`,
`p_hc1_control_valve_position_setpoint`, `p_hc1_return_temperature`, `p_net_meter_energy`,
`p_net_meter_flow`, `p_net_meter_heat_power`, `p_net_meter_volume`, `p_net_return_temperature`,
`p_net_supply_temperature`, `s_dhw_lower_storage_temperature`, `s_dhw_supply_temperature`,
`s_dhw_supply_temperature_setpoint`, `s_dhw_upper_storage_temperature`, `s_hc1_supply_temperature`,
`s_hc1_supply_temperature_setpoint`, `s_dhw_control_unit_mode`, `s_hc1_control_unit_mode`,
`s_hc1_heating_pump_status_setpoint`

## substations — 매핑

| 출처 | raw | DB 컬럼명 |
|---|---|---|
| source metadata | manufacturer | `manufacturer` |
| 파일명/메타 | substation_id | `substation_id` |
| source metadata | source_file | `source_file` |
| configuration_types.csv | configuration_type | `configuration_type` |
| (파생) | has_dhw | `has_dhw` |
| (파생) | has_buffer_tank | `has_buffer_tank` |

## fault_events — 매핑 (faults.csv)

| raw | DB 컬럼명 | 비고 |
|---|---|---|
| `Event ID` | `event_id` | PK |
| `substation ID` | `substation_id` | |
| `Report date` | `report_date` | |
| `Problem EN` | `problem_en` | |
| `Fault label` | `fault_label` | |
| `Event description EN` | `event_description_en` | optional |

운영 제외(훈련 전용): `Possible anomaly start/end`, `Training start/end`, `efd_possible`, `Monitoring potential`

## maintenance_events — 매핑 (disturbances.csv)

| raw | DB 컬럼명 | 비고 |
|---|---|---|
| (없음) | `id` | 합성 BIGSERIAL 대리키 |
| `substation ID` | `substation_id` | |
| `Event start` | `event_start` | |
| `type` | `type` | |
