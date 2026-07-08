# HeatGrid Frontend Test Handoff

## 전달 파일

이 폴더에는 프론트 지도/카드 테스트와 DB 적재 후보로 쓸 최신 파일만 들어 있습니다.

1. `substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv`
   - 프론트에서 바로 읽어 지도 마커와 단지 카드를 만들 수 있는 최신 데이터입니다.
   - 총 31행이며, 세종 1생활권 지역난방 아파트 후보 31개입니다.
   - K-APT 기준 31개 모두 `지역난방`으로 확인했습니다.
   - PreDist 원본 설비/센서 메타데이터를 가상 매핑으로 붙인 DB 적재 후보 파일입니다.
   - 실제 세종 아파트와 PreDist 설비가 물리적으로 연결된 것은 아니며, `substation_id` 기준 데모 매핑입니다.
   - 상세 모델 점수, 라벨, 이벤트 이력은 여기 넣지 않았고 Agent 도구 호출 단계에서 가져가는 구조를 전제로 했습니다.

2. `substation_buildings_sejong_lifezone1_31_district_heating_with_predist_column_dictionary.csv`
   - `_with_predist` CSV의 컬럼별 한국어 설명입니다.
   - `column`, `ko_name`, `description`, `usage_note` 구조입니다.

3. `predist_virtual_substation_sensor_metadata_m1.csv`
   - PreDist 관련 컬럼만 따로 분리한 31행 메타데이터입니다.
   - DB에서 별도 테이블로 나누고 싶을 때 사용할 수 있습니다.

## 프론트에서 우선 사용할 컬럼

지도 마커:

```text
substation_id
matched_name
latitude
longitude
road_address
heating_type
```

카드/팝업 기본 정보:

```text
kapt_code
life_zone
dong
village
household_count
building_count
gross_floor_area_m2
exclusive_residential_area_m2
```

열수요/영향도 대리 지표:

```text
private_usage_cost_latest_month_krw
private_usage_cost_latest_month_unit_krw_per_m2
total_mgmt_cost_latest_month_krw
total_mgmt_cost_latest_month_unit_krw_per_m2
total_mgmt_cost_ytd_per_household_krw
```

PreDist 설비/센서 요약:

```text
predist_configuration_type
predist_configuration_ko
predist_sensor_groups_ko
predist_sensor_column_count
predist_has_outdoor_temperature_sensor
predist_has_space_heating_sensor
predist_has_dhw_sensor
predist_has_dhw_storage_sensor
predist_has_primary_heat_meter_sensor
predist_has_primary_supply_return_temp_sensor
```

## 주의할 점

현재 `substation_id`는 실제 세종시 현장 설비 ID가 아닙니다. 모델 데이터의 익명화된 substation 번호를 세종 지역난방 아파트 후보에 데모용으로 매핑한 값입니다.

따라서 프론트에서는 `substation_id`를 내부 카드/마커 ID로 쓰면 됩니다. 실제 운영 설비와 1:1로 검증된 ID처럼 표현하면 안 됩니다.

`predist_*` 컬럼도 같은 원칙입니다. 실제 세종 아파트의 현장 센서가 아니라, 원본 PreDist substation_id의 설비/센서 구성을 데모용으로 붙인 값입니다.

`predist_has_*_sensor` 컬럼은 `1/0` 값입니다. `1`은 해당 센서 그룹이 원본 샘플에 존재한다는 뜻이고, `0`은 샘플에서 확인되지 않았다는 뜻입니다.

CSV의 `부하` 관련 값은 실제 열량계에서 나온 열부하가 아닙니다. 현재는 세대수, 연면적, 관리비 등을 이용한 `열수요 규모 대리 지표`입니다.

실제 열부하는 나중에 다음 센서값이 있어야 계산할 수 있습니다.

```text
열부하 = 유량 x 비열 x (공급온도 - 환수온도)
```

## 화면 테스트 추천 형태

마커 label:

```text
{substation_id}. {matched_name}
```

마커 tooltip/card:

```text
단지명: matched_name
난방방식: heating_type
세대수: household_count
연면적: gross_floor_area_m2
주소: road_address
최신월 총관리비: total_mgmt_cost_latest_month_krw
면적당 최신월 총관리비: total_mgmt_cost_latest_month_unit_krw_per_m2
```

## 데이터 상태

```text
rows: 31
district heating matched: 31
K-APT matched: 31
latest fee summary available: 31
with_predist columns: 48
predist configuration source: configuration_types.csv
predist mapping: virtual_by_substation_id
```
