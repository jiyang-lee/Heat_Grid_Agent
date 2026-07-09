# 공간 매핑 및 외부 데이터 DB 구축 계획

## 현재 프로젝트 기준 확인값

- 현재 모델/카드 산출물 기준 `substation_id`는 1~31번까지 총 31개이다.
- 데이터는 `manufacturer 1`만 포함한다.
- `data/processed/trainable_windows.csv`, `output/agent_priority_card.csv` 모두 1,252행이다.
- 윈도우 길이는 주로 6시간이다.
- `window_start` 범위는 2014-05-03 18:00:00부터 2020-06-13 00:00:00까지다.
- 고유 `window_start`는 1,054개다.
- 같은 `window_start`에 동시에 존재하는 substation 수는 최대 3개다.
- 따라서 현재 학습/검증 산출물은 "동시간대 31개 substation 전체 비교" 구조가 아니다.

실서비스에서는 `card_id` 하나만 중심에 두면 부족하다. 화면에서 특정 카드 하나를 눌러도, 서버는 그 카드가 속한 `window_id`를 찾아 같은 시간대의 모든 substation 상태를 같이 가져올 수 있어야 한다.

## 세종 1생활권 31개 단지 보강 산출물

최종 보강 파일은 `data/external/substation_buildings_sejong_lifezone1_31_enriched.csv`다.

- 기준 매핑: 한국지역난방공사 건물별 지역난방 공급현황 정보_20221231에서 세종 1생활권 아파트 후보 선별
- 주소/좌표: Kakao Map place search 기준 도로명주소, 지번주소, 위도, 경도 보강
- 공동주택 정보: K-APT 화면/JSON 흐름에서 단지 기본정보, 관리시설정보, 월별 관리비 대시보드 요약 보강
- K-APT 매칭 결과: 31개 모두 `matched`
- K-APT 난방방식: 31개 모두 `지역난방`
- 총 세대수: matched 단지 기준 23,503세대
- 관리비 요약: 31개 모두 `dashboard_summary_ok`

교체 이력은 다음과 같다.

- `substation_id=29`: 기존 `범지기마을1단지한양수자인에듀센텀아파트`는 K-APT 난방방식이 `중앙난방`으로 조회되어, 같은 원본 세종 1-2생활권/아름동/범지기마을 후보인 `범지기마을7단지호반베르디움아파트`로 교체했다.
- `substation_id=30`: 기존 `범지기마을3단지중흥S클래스에듀하이아파트`는 K-APT 자동 매칭이 되지 않아, 같은 원본 세종 1-2생활권/아름동/범지기마을 후보인 `범지기마을9단지한신휴플러스리버파크아파트`로 교체했다.

DB 적재 시에는 `substation_id`를 내부 모델 번호, `kapt_code`를 공동주택 외부 식별자, `kakao_place_id`를 지도/장소 식별자로 분리해서 유지한다. `district_heating_supply_confirmed`는 원천 지역난방공사 CSV 기준 후보 여부이고, 실제 현장 substation과의 1:1 검증 상태는 `mapping_status`로 별도 관리해야 한다.

## 실서비스 ID 구조

### 1. `window_id`

동일 시간 비교의 기준 ID다.

예:

```text
window_id = 20260708T090000_6H_REGION_GY
window_start = 2026-07-08 09:00:00
window_end = 2026-07-08 15:00:00
region_id = REGION_GY
```

### 2. `card_id`

특정 시간 윈도우 안의 특정 substation 한 개를 가리키는 ID다.

예:

```text
card_id = REGION_GY_20260708T090000_6H_SUBSTATION_001
window_id = 20260708T090000_6H_REGION_GY
substation_id = 1
```

이렇게 해야 카드 하나를 눌렀을 때도 다음 두 가지가 모두 가능하다.

- `get_ops_evidence(card_id)`: 선택된 substation의 센서값, 모델 점수, 우선순위 이유 조회
- `get_window_comparison(window_id)`: 같은 시간대 전체 substation의 우선순위 비교 조회

## 지역 매핑 방향

현재 `substation_id`는 1~31 숫자뿐이라 실제 위치 의미가 없다. 그러므로 실서비스 데모에서는 실제 지역난방 사용 건물/아파트 중 한 지역을 정하고, 그 지역 안의 31개 후보 건물 또는 단지를 내부 substation 31개에 매핑한다.

주의할 점은 이 매핑이 "실제 해당 아파트의 실제 substation 장비"라는 뜻은 아니라는 것이다. 현재 모델 데이터가 독일 PreDist 계열의 익명화된 substation 데이터이기 때문에, 국내 지도 위에 올릴 때는 `demo_mapping` 또는 `surrogate_mapping` 상태로 관리해야 한다.

단순 `region_id`만으로는 실제 지역난방 운영 느낌이 약하다. 같은 행정구 안에서도 건물 간 거리가 멀고, 서로 다른 공급권역일 수 있기 때문이다. 따라서 후보 선정은 행정구보다 좁은 생활권 단위로 한다. 다만 최종 seed CSV에는 모든 행에서 반복되는 `supply_network_id` 같은 컬럼은 넣지 않는다.

초기 데모 후보는 세종 1생활권으로 둔다.

- 원천: `한국지역난방공사_건물별 지역난방 공급현황 정보_20221231`
- 지역: 세종특별자치시
- 공급망 후보: 세종 1생활권
- 후보 수: 1생활권 아파트 76개
- 최종 파일: `data/external/substation_buildings_sejong_lifezone1_31_geocoded.csv`
- 생활권 분포: `life_zone=4` 10개, `life_zone=1` 9개, `life_zone=3` 6개, `life_zone=2` 6개
- 최종 컬럼: `substation_id`, `life_zone`, `dong`, `village`, `building_name`, `road_address`, `jibun_address`, `latitude`, `longitude`, `geocode_status`

이 후보는 "같은 생활권 기반 공급망 후보"이지, 실제 열원/관망 확정값은 아니다. 실제성을 더 높이려면 좌표를 붙인 뒤 열원시설/공급권역 데이터와 함께 거리 검증을 해야 한다.

권장 매핑 테이블은 다음과 같다.

```text
substations
- substation_id
- display_name
- region_id
- mapped_building_id
- latitude
- longitude
- mapping_status
- mapping_confidence
- source_dataset
- created_at
- updated_at
```

`mapping_status` 예:

- `internal_only`: 내부 번호만 있음
- `candidate_mapped`: 공공데이터 건물/단지에 후보 매핑됨
- `verified`: 실제 운영자가 확인한 매핑

## 첨부 Excel 기준 DB 우선 후보

### 1순위: 지도 매핑용

#### 한국지역난방공사_건물별 지역난방 공급현황 정보

- URL: https://www.data.go.kr/data/15090340/fileData.do
- Excel 분류: 영향도
- 주요 용도: 실제 지역난방 공급 건물 후보 추출
- DB 테이블: `district_heating_buildings`
- 필요한 컬럼:
  - `use_type`
  - `building_name`
  - `road_address`
  - `jibun_address`
  - `region_name`
  - `latitude`
  - `longitude`
  - `source_dataset`

이 데이터가 지도 매핑의 중심이다. 건물명, 주소, 용도 정보가 있으므로 한 지역 안에서 아파트 중심으로 31개 후보를 뽑아 `substation_id`와 연결할 수 있다.

#### 국토교통부_공동주택 단지 목록제공 서비스

- URL: https://www.data.go.kr/data/15057332/openapi.do
- Excel 분류: 건물·부하
- 주요 용도: 공동주택 단지명, 법정동/도로명주소 보강
- DB 테이블: `apartment_complexes`
- 필요한 컬럼:
  - `kapt_code`
  - `complex_name`
  - `sido`
  - `sigungu`
  - `dong`
  - `road_address`
  - `jibun_address`

지역난방 건물 데이터의 주소/건물명을 K-APT 단지 목록과 매칭해 프론트 지도 표기명을 안정화한다.

#### 국토교통부_공동주택 기본 정보제공 서비스

- URL: https://www.data.go.kr/data/15058453/openapi.do
- Excel 분류: 건물·부하
- 주요 용도: 세대수, 난방방식, 동수, 연면적 등 영향도 보강
- DB 테이블: `apartment_complex_profiles`
- 필요한 컬럼:
  - `kapt_code`
  - `heating_method`
  - `household_count`
  - `building_count`
  - `gross_floor_area`
  - `approval_date`

우선순위 설명에서 "영향 세대가 큰 단지", "난방방식상 부하 민감도가 큰 단지" 같은 보조 근거로 쓸 수 있다.

### 2순위: 시간대 외부 컨텍스트용

#### 기상청 지상(ASOS) 시간자료 조회서비스

- URL: https://www.data.go.kr/data/15057210/openapi.do
- Excel 분류: 기상·부하
- 주요 용도: 시간 단위 외기온, 습도, 강수, 풍속 등
- DB 테이블: `weather_observations_hourly`
- 필요한 컬럼:
  - `station_id`
  - `observed_at`
  - `temperature_c`
  - `humidity_pct`
  - `precipitation_mm`
  - `wind_speed_mps`
  - `pressure_hpa`

Agent tool은 처음부터 API를 직접 치지 말고, 서버가 수집한 DB 테이블을 조회하게 두는 편이 운영에 맞다.

#### 한국천문연구원_특일 정보

- URL: https://www.data.go.kr/data/15012690/openapi.do
- Excel 분류: 기타(특일)
- 주요 용도: 공휴일, 국경일, 24절기, 특일 부하 패턴
- DB 테이블: `calendar_special_days`
- 필요한 컬럼:
  - `date`
  - `date_name`
  - `date_kind`
  - `is_holiday`

난방 부하는 평일/휴일/절기 영향을 받기 때문에 낮은 비용으로 설명력을 보강할 수 있다.

### 3순위: 운영 영향도 보강용

#### 지역난방 공급현황 정보

- URL: https://www.data.go.kr/data/3070435/fileData.do
- Excel 분류: 영향도
- 주요 용도: 지역별 공급세대수, 사업자, 공급지역 기준으로 대상 지역 선정
- DB 테이블: `district_heating_supply_regions`
- 필요한 컬럼:
  - `base_year`
  - `company_name`
  - `region_group`
  - `supply_area`
  - `household_count`
  - `supply_ratio`

이 데이터는 31개 아파트를 고르는 원천이라기보다, "어느 지역을 데모 지역으로 잡을지"와 "지역 단위 영향도"를 잡는 데 좋다.

#### 한국지역난방공사_일자별 설비 가동 현황

- URL: https://www.data.go.kr/data/15124158/fileData.do
- Excel 분류: 설비 가동·생산
- 주요 용도: 일자별 공급측 설비 가동 맥락
- DB 테이블: `district_heating_facility_daily_operations`
- 필요한 컬럼:
  - `operation_date`
  - `facility_type`
  - `facility_name`
  - `operation_minutes`

단, 이 데이터는 개별 substation과 직접 연결되지는 않는다. 초반에는 지도/날씨/세대수보다 우선순위를 낮춘다.

### 후순위 또는 RAG 후보

아래 자료는 구조화 DB보다 RAG 또는 규칙 근거 문서로 나중에 넣는 쪽이 맞다.

- 한국지역난방공사 열사용시설기준
- 열사용시설 점검업무 기술 기준서
- 열공급규정
- 집단에너지사업법
- 집단에너지시설의 기술기준
- 열공급시설의 검사기준
- IEA DHC Connection Handbook
- Swedish F:101 District Heating Substations
- Danfoss Troubleshooting Table

## 권장 DB 테이블 묶음

### 내부 모델/카드 테이블

```text
window_groups
- window_id
- region_id
- window_start
- window_end
- created_at

substation_window_cards
- card_id
- window_id
- substation_id
- priority_score
- priority_level
- risk_probability
- risk_score
- anomaly_score
- leadtime_bucket
- review_required
- why_reason
- recommended_action

ops_evidence_snapshots
- card_id
- raw_context jsonb
- priority_context jsonb
- model_context jsonb
- created_at
```

### 공간/지역 테이블

```text
service_regions
- region_id
- region_name
- sido
- sigungu
- center_latitude
- center_longitude
- map_zoom

district_heating_buildings
- building_id
- use_type
- building_name
- road_address
- jibun_address
- latitude
- longitude
- geocode_status
- source_dataset

substation_building_map
- substation_id
- building_id
- mapping_status
- mapping_confidence
- mapping_note
```

### 외부 컨텍스트 테이블

```text
weather_observations_hourly
- station_id
- observed_at
- temperature_c
- humidity_pct
- precipitation_mm
- wind_speed_mps
- pressure_hpa

calendar_special_days
- date
- date_name
- date_kind
- is_holiday

apartment_complex_profiles
- kapt_code
- complex_name
- address
- heating_method
- household_count
- building_count
- gross_floor_area
```

## 프론트 직전 단계 API

프론트 담당자가 지도 UI를 만들기 전, 백엔드는 아래 형태까지만 만들어주면 된다.

```http
GET /api/windows/{window_id}/map-context
```

응답 예:

```json
{
  "window": {
    "window_id": "20260708T090000_6H_REGION_GY",
    "window_start": "2026-07-08T09:00:00+09:00",
    "window_end": "2026-07-08T15:00:00+09:00"
  },
  "region": {
    "region_id": "REGION_GY",
    "region_name": "데모 지역",
    "center": {
      "lat": 37.0,
      "lon": 127.0
    }
  },
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [127.0, 37.0]
      },
      "properties": {
        "card_id": "REGION_GY_20260708T090000_6H_SUBSTATION_001",
        "substation_id": 1,
        "site_name": "매핑된 아파트/건물명",
        "address": "주소",
        "priority_score": 0.91,
        "priority_level": "urgent",
        "risk_probability": 0.82,
        "review_required": true
      }
    }
  ]
}
```

이 응답은 지도 라이브러리에서 바로 쓸 수 있는 GeoJSON에 가깝게 둔다.

## LangGraph tool 확장

기존 단일 카드 흐름은 유지한다.

```text
get_ops_evidence(card_id)
```

여기에 실서비스 비교용 tool을 추가한다.

```text
get_window_comparison(window_id)
get_weather_context(region_id, window_start, window_end)
```

Agent 시작 입력은 여전히 카드 중심이어도 된다.

```json
{
  "card_id": "REGION_GY_20260708T090000_6H_SUBSTATION_001"
}
```

서버는 DB에서 이 `card_id`가 속한 `window_id`, `region_id`, `substation_id`를 찾는다. LLM Agent는 필요하면 `get_ops_evidence(card_id)`로 선택 카드 근거를 보고, `get_window_comparison(window_id)`로 같은 시간대 전체 substation 대비 순위를 본다. 날씨 설명이 필요하면 `get_weather_context(...)`를 호출한다.

## 구현 순서

1. 현재 31개 `substation_id`를 기준으로 `substations` 시드 테이블을 만든다.
2. 실제 지역난방 건물 데이터에서 세종 1생활권 후보를 고른다.
3. `substation_buildings_sejong_lifezone1_31_geocoded.csv`의 31개를 시드로 쓴다.
4. `건물명 + 세종특별자치시`를 지도/주소 검색과 매칭해 도로명주소, 지번주소, 위경도를 붙인다.
5. 좌표 기준으로 건물 간 거리와 열원시설/공급권역 거리를 검증한다.
6. 주소와 좌표를 `district_heating_buildings`에 저장한다.
7. `substation_building_map`으로 내부 번호와 실제 지도 후보를 연결한다.
8. 모델 산출물에서 `window_groups`, `substation_window_cards`, `ops_evidence_snapshots`를 만든다.
9. ASOS 시간자료와 특일 정보를 수집해 DB에 저장한다.
10. `/api/windows/{window_id}/map-context`를 만든다.
11. LangGraph tool에 `get_window_comparison`, `get_weather_context`를 추가한다.
12. RAG는 위 구조가 안정화된 뒤 기준서/법령/점검표 문서부터 추가한다.
