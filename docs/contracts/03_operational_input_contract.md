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

## 추론 산출물 계약

운영 입력 4테이블은 raw 계약이고, 추론 산출물은 별도 테이블 계약으로 분리한다.

- `preprocessed_windows`: raw 4테이블을 6시간 window로 집계한 전처리 중간층
- `model_chain_output`: IF + LGBM risk + LGBM leadtime 중간 예측 결과
- `priority_scores`: 규칙 기반 priority engine의 운영 큐 점수/등급

`model_chain_output`은 `priority_scores`의 직접 입력이므로 DDL 실행 순서도 `006_model_chain_output.sql` 다음 `007_priority_scores.sql`로 둔다. IF + LGBM risk + LGBM leadtime 체인은 유지하고, priority에는 규칙 엔진 버전 추적용 `model_version`을 둔다.

## 산출물 위치

- DDL: `schema/sql/000_extensions.sql` … `007_priority_scores.sql`
- JSON Schema: `schema/json/*.schema.json`
- 컬럼 매핑: `schema/column_name_mapping.md`
- 상세/근거: `schema/README.md`
