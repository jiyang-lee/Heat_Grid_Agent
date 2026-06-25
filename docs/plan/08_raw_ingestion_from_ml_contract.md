# raw ingestion 기준 (ML 계약 기반)

## 0. 이 문서의 위치

- **`docs/plan/07_raw_sensor_data_schema.md`의 raw 스키마 규칙은 무시한다.**
  07은 raw를 코어 센서 9개 wide 테이블로 좁히고 `*_mode/*_status/*_setpoint`·`s_dhw_*`·`s_hc1.1~3`을 제외했지만,
  ML팀 실제 계약은 그중 상당수를 **필수로 요구**한다. 따라서 raw 기준은 07이 아니라 **ML 계약**을 단일 출처로 삼는다.
- 출처(이 repo에 커밋됨):
  - `data/processed/ml_features/agent_required_raw_columns.json`
  - `data/processed/ml_features/agent_full_data_contract.json` (`version: agent_data_contract_v1`)
  - `data/processed/ml_features/agent_feature_contract.json`
- 07에서 **여전히 유효한 사실**(데이터 형식): operational CSV는 구분자 `;`, 수집 주기 10분, 파일 내부에
  설비 ID 없음 → `manufacturer`(폴더명)·`substation_id`(파일명)로 식별. 이 부분만 가져오고, 컬럼 선택 규칙은 버린다.

## 1. raw로 적재할 컬럼 = 29개

ML 전처리(`03_preprocess_windows`)가 요구하는 raw operational 컬럼. union 50개 중 **29개 유지 / 21개 제외**.
타입 처리 기준이 셋으로 갈린다.

### 1.1 시각 (1)

| 컬럼 | 타입 | 처리 |
|---|---|---|
| `timestamp` | datetime | 파싱 → 정렬 → 무효 행 drop → timestamp 기준 중복 제거 |

### 1.2 수치 코어 센서 (17) — numeric, 무효값은 null로 강제

`outdoor_temperature`, `p_dhw_control_valve_position`, `p_dhw_return_temperature`,
`p_hc1_control_valve_position_setpoint`, `p_hc1_return_temperature`,
`p_net_meter_energy`, `p_net_meter_flow`, `p_net_meter_heat_power`, `p_net_meter_volume`,
`p_net_return_temperature`, `p_net_supply_temperature`,
`s_dhw_lower_storage_temperature`, `s_dhw_supply_temperature`, `s_dhw_supply_temperature_setpoint`,
`s_dhw_upper_storage_temperature`, `s_hc1_supply_temperature`, `s_hc1_supply_temperature_setpoint`

### 1.3 제어/상태 범주형 (11) — string 캐스팅, 결측은 `"missing"`으로 채움

`s_dhw_3-way_valve_status`, `s_dhw_control_unit_mode`,
`s_hc1.1_control_unit_mode`, `s_hc1.1_heating_pump_status`,
`s_hc1.2_control_unit_mode`, `s_hc1.2_dhw_control unit_mode`, `s_hc1.2_heating_pump_status`,
`s_hc1.3_control_unit_mode`, `s_hc1.3_heating_pump_status`,
`s_hc1_control_unit_mode`, `s_hc1_heating_pump_status_setpoint`

> ⚠️ 컬럼명 주의: `s_dhw_3-way_valve_status`(하이픈), `s_hc1.2_dhw_control unit_mode`(**중간에 공백** — 원본 오타로 보이나 계약은 이 이름 그대로 요구), `s_hc1.1/.2/.3`(점 포함). SQL/DataFrame에서 따옴표·escape 필요.

### 1.4 제외 컬럼 (21) — raw에 넣지 않음

`p_dhw_return_temperature_setpoint`, `p_hc1_return_temperature_setpoint`,
`s_dhw_upper_storage_temperature_setpoint`,
`s_hc1.1_control_valve_position`, `s_hc1.1_return_temperature`, `s_hc1.1_return_temperature_setpoint`,
`s_hc1.1_room_temperature_setpoint`, `s_hc1.1_supply_temperature`, `s_hc1.1_supply_temperature_setpoint`,
`s_hc1.2_control_valve_position`, `s_hc1.2_return_temperature`, `s_hc1.2_return_temperature_setpoint`,
`s_hc1.2_room_temperature_setpoint`, `s_hc1.2_supply_temperature`, `s_hc1.2_supply_temperature_setpoint`,
`s_hc1.3_control_valve_position`, `s_hc1.3_return_temperature`, `s_hc1.3_room_temperature_setpoint`,
`s_hc1.3_supply_temperature`, `s_hc1.3_supply_temperature_setpoint`, `s_hc1_room_temperature_setpoint`

## 2. 식별/추적 컬럼 (CSV에 없음 → 적재 시 생성)

ML 계약 `source_metadata` = `manufacturer`, `substation_id`, `source_file`.

| 컬럼 | 출처 | 비고 |
|---|---|---|
| `manufacturer` | 폴더명 | `manufacturer_1` / `manufacturer_2` (피처에서 one-hot됨) |
| `substation_id` | 파일명 `substation_{N}` | CSV 내부에 없음 |
| `source_file` | 적재 시 | 원본 역추적 |

## 3. 품질 필터 (전처리 단계)

`agent_full_data_contract.json` → `quality_filters`:
minimum row ratio, missing rate, timestamp gap, leakage guard, normal reference filtering.
+ `raw_column_pruning`: 21개 drop / 29개 keep.

## 4. context 소스 (raw 아님 — 후속 단계 join)

| 파일 | 제공 | 용도 |
|---|---|---|
| `configuration_types.csv` | `configuration_type` | 설비 구성 타입 (one-hot 6종: sh / sh_dhw / sh_with_buffer_tank / sh_with_sub_circuits / sh_dhw_with_sub_circuits / missing) |
| `faults.csv` | `fault_label`, `fault_event_id`, `estimated_lead_time_hours`, risk labels | 라벨/리드타임 |
| `disturbances.csv` | maintenance/task event history, `days_since_last_task_event` | 외란/정비 이력 |
| `normal_events.csv` | normal reference windows | 정상 기준 구간 |

## 5. 다운스트림 요약 (raw 단계 아님 — 참고용)

- **windowing**: operational 시계열에서 **6시간 윈도우**(sliding/fixed) → canonical prediction의 `window_start/window_end`와 연결됨.
- 인코딩: 제어 범주형 11개 + context 3개(`manufacturer`, `configuration_type`, `season_bucket`)를 dominant 값 기준 one-hot.
  - 범주값 예: valve `aus`/`ein`, mode `tag`/`nacht`/`standby`, 그리고 `missing`.
- 최종 모델 피처 **195개** (가족: derived_one_hot 44, cyclic_time 6, time_context 6, 그 외 window 집계/delta/gap/missing-rate 등), metadata 37개.

## 6. 파이프라인 매핑 + 열린 결정

- raw 단계가 보존할 것 = **§1의 29개(타입 3분류) + §2 식별 3개**. 환산/인코딩/윈도우는 후속 단계.
- **결정 필요 1 — raw 저장 표현**:
  (a) `raw_sensor_events.raw_payload`(JSONB)에 29개를 그대로 담기(report/01 방식, 스키마 변경 없이 확장 쉬움) vs
  (b) 29개를 컬럼으로 갖는 wide raw 테이블. 범주형/수치 혼합·불규칙 컬럼명 때문에 (a)가 단순.
- **결정 필요 2 — 범주형 결측 처리 위치**: `"missing"` 치환을 raw 적재에서 할지, normalize/전처리 단계에서 할지.
  ML 계약은 전처리 단계 기준이므로 raw는 원시값 보존, `"missing"` 치환은 normalize 이후 권장.
- **결정 필요 3 — feature_columns.csv / metadata_columns.csv / configuration_types.csv** 원본이 필요하면
  `mlmodel1` 브랜치 `data/processed/ml_features/`에서 추가로 가져온다(현재 repo엔 agent_*.json 3개만 있음).

## 7. 한 줄 정리

raw 기준은 plan/07이 아니라 **ML 계약의 29개 컬럼(시각 1 + 수치 17 + 범주 11) + 식별 3개**다.
raw는 원시값을 보존하고, 인코딩·6h 윈도우·195 피처 생성은 모두 후속 단계로 미룬다.
