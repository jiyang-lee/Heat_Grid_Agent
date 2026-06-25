# 운영 입력 데이터 계약 (operational_input_v1)

이 문서는 HeatGrid Agent **운영(추론) 입력** 데이터 계약의 사람이 읽는 요약이다.
실제 실행 산출물(DDL/JSON Schema)은 repo 루트 `schema/` 폴더에 있다.

## 한 줄 요약

학습 끝난 ML 모델을 예측기로 쓰므로, 운영 실시간 raw는 **센서 스트림 하나**뿐이다.
feature 생성을 위해 **설비 구성(정적)** 과 **고장/정비 이력(이벤트 로그)** 을 함께 둔다.

## 테이블 4종

| 테이블 | 성격 | 1행의 의미 | 출처 |
|---|---|---|---|
| `substations` | 정적 마스터 | 기계실 1개 | configuration_types.csv + 메타 |
| `sensor_readings` | 실시간 시계열(hypertable) | 기계실 1개 × 1시점 | operational_data/*.csv |
| `fault_events` | 이벤트 로그 | 고장 1건 | faults.csv |
| `maintenance_events` | 이벤트 로그 | 정비 1건 | disturbances.csv |

`normal_events.csv`는 훈련 전용 → 운영 미생성.

## 컬럼 수 요약

- `substations`: 식별/설비 7컬럼
- `sensor_readings`: `substation_id` + `ts` + 숫자 17 + 제어 11 = 30컬럼 (operational base 29 = ts + 28)
- `fault_events`: 운영 필요 6컬럼 (+ created_at)
- `maintenance_events`: 4컬럼 (+ created_at)

## 다음 단계(이번 범위 밖)

예측 결과(`model_predictions`)·우선순위(`priority_scores`)·윈도우 피처(`window_features`) 테이블은
ML 산출물 형태 확정 후 별도 계약으로 추가한다. 이때 `model_version` / `feature_version` /
`engine_version` 버전 필드를 둬서 모델 갱신과 스키마를 분리한다.

## 산출물 위치

- DDL: `schema/sql/000_extensions.sql` … `004_maintenance_events.sql`
- JSON Schema: `schema/json/*.schema.json`
- 컬럼 매핑: `schema/column_name_mapping.md`
- 상세/근거: `schema/README.md`
