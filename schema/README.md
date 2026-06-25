# schema/ — 운영 입력 데이터 계약

HeatGrid Agent **운영(추론) 입력** 데이터 계약을 JSON Schema + PostgreSQL DDL로 고정한 폴더다.

- 계약 버전: `operational_input_v1`
- 대상 DB: PostgreSQL + TimescaleDB
- 범위: 운영 입력 4개 테이블 (예측/우선순위/피처 테이블은 다음 단계)

## 배경

학습 끝난 ML 모델을 예측기로만 쓰기 때문에, 운영에서 실시간으로 들어오는 raw는
**기계실 센서 스트림 하나**뿐이다. ML feature를 만들려면 추가로 **설비 구성(정적)** 과
**고장/정비 이력(이벤트 로그)** 이 필요하다. 그래서 입력 테이블을 3종 성격으로 나눈다.

| 테이블 | 성격 | 갱신 빈도 | 출처 |
|---|---|---|---|
| `substations` | 정적 마스터 | 거의 없음 | configuration_types.csv + 메타 |
| `sensor_readings` | 실시간 시계열 | 계속 | operational_data/substation_*.csv |
| `fault_events` | 이벤트 로그 | 고장 시 | faults.csv |
| `maintenance_events` | 이벤트 로그 | 정비 시 | disturbances.csv |

> `normal_events.csv`는 정상 기준 학습 구간 정의용이라 **운영에서는 만들지 않는다**(훈련 전용).

## 폴더 구조

```
schema/
  sql/    PostgreSQL DDL (실행 순서 000 -> 004)
  json/   JSON Schema (draft 2020-12) — 입력 데이터 검증용
  column_name_mapping.md   raw 컬럼명 -> DB 컬럼명 매핑
  README.md
```

## JOIN / 식별 키

- `substations.substation_id` = 모든 테이블의 `substation_id` (FK)
- 시계열 조회: `sensor_readings (substation_id, ts)`
- 최근 이벤트 조회: `fault_events (substation_id, report_date)`, `maintenance_events (substation_id, event_start)`

## 적재 시 처리 규칙

- `timestamp` → `ts`로 datetime 파싱, 정렬, invalid/중복 제거
- 숫자 센서: numeric 변환, 비정상값은 null로 (스키마상 nullable)
- 제어/상태 센서: string, 결측은 `missing`으로 채울 수 있음
- 컬럼명은 `column_name_mapping.md` 기준으로 정규화

## 주요 설계 근거 (why)

- **TimescaleDB hypertable(sensor_readings)**: 고빈도 시계열의 시간 파티셔닝/압축/시간범위 쿼리 성능. (AGENTS.md DB 규칙 정합성)
- **컬럼명 snake_case 정규화**: raw의 `.`/공백이 SQL 식별자로 부적합 → 따옴표 escape 제거로 유지보수성·디버깅 용이성 확보.
- **JSON Schema(draft 2020-12) 채택**: 입력 4종이 모두 외부 유입 데이터라 적재 전 자동 검증(타입/enum/필수)이 필요. 단순 목록형 계약보다 위험 감소에 유리.
- **이벤트 테이블 분리(fault/maintenance)**: 센서값으로 못 만드는 `days_since_last_*` feature의 원천. 원본/가공 분리 원칙(AGENTS.md)과 정합.
- **훈련 전용 컬럼 제외**: 운영 계약을 최소화해 ML 모델 갱신과 무관하게 스키마가 안정적으로 유지됨(확장성).

## 검증 방법

- DDL: `psql -f sql/000_extensions.sql` … 순서대로 실행해 테이블 생성 확인 (TimescaleDB 필요)
- JSON Schema: `python -c "from jsonschema import Draft202012Validator, ... ; Draft202012Validator.check_schema(...)"`
- 정합성: ML 계약(`agent_full_data_contract.json`)의 operational 29개 컬럼이 `sensor_readings`(ts+28) + `substations` 매핑으로 빠짐없이 커버되는지 `column_name_mapping.md`로 대조.
