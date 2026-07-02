# 전처리 데이터 계약 (preprocessed_data_v1)

이 문서는 HeatGrid Agent **전처리 데이터** 계약의 사람이 읽는 요약이다.  
흐름은 `raw 4테이블 -> 전처리 -> 전처리 데이터 -> 피처 엔지니어링`으로 둔다.

## 한 줄 요약

전처리 데이터는 raw 4테이블을 모델 실험과 무관한 표준 시간 구간으로 정리한 중간층이다.  
피처 엔지니어링은 이 전처리 데이터를 입력으로 받아 바뀔 수 있지만, 전처리 데이터의 grain과 기본 품질/통계/context 컬럼은 고정한다.

## 테이블

| 테이블 | 성격 | 1행의 의미 | 출처 |
|---|---|---|---|
| `preprocessed_windows` | 전처리 중간 데이터 | 기계실 1개 x 6시간 구간 1개 | `substations`, `sensor_readings`, `fault_events`, `maintenance_events` |

## 입력과 출력

| 구분 | 내용 |
|---|---|
| 입력 | 운영 raw 4테이블 |
| 출력 | `preprocessed_windows` |
| 기본 grain | `(substation_id, window_start, window_end)` |
| 계약 버전 | `preprocessed_data_v1` |
| 다음 단계 | 피처 엔지니어링 |

## 구현 위치

| 항목 | 위치 |
|---|---|
| public 함수 | `agent.preprocessing.build_preprocessed_windows` |
| 상수/컬럼 계약 | `agent/preprocessing/contracts.py` |
| 입력/출력 검증 | `agent/preprocessing/validate.py` |
| 테스트 | `tests/test_preprocessing_build_windows.py` |

핵심 함수는 다음 입력을 받는다.

```python
build_preprocessed_windows(
    substations,
    sensor_readings,
    fault_events,
    maintenance_events,
    *,
    window_size="6h",
)
```

## 컬럼 수 요약

| 그룹 | 산식 | 컬럼 수 |
|---|---:|---:|
| 식별/시간/품질 | 고정 컬럼 | 14 |
| numeric sensor 통계 | 17 sensors x 9 stats | 153 |
| control/status 요약 | 11 sensors x 3 summaries | 33 |
| 이벤트 context | 고정 컬럼 | 6 |
| 설비 context | 고정 컬럼 | 3 |
| lineage/version | 고정 컬럼 | 2 |
| 합계 | 14 + 153 + 33 + 6 + 3 + 2 | 211 |

## 포함하는 것

- 6시간 구간 식별자와 row count
- timestamp 품질 지표
- numeric sensor 기본 통계
- control/status dominant/nunique/change count
- 최근 고장/정비 이벤트 거리
- 설비 구성 context
- `preprocessing_version`

## 포함하지 않는 것

- one-hot encoding
- imputation 결과
- selected feature list
- model-specific feature version
- 모델 예측 결과와 우선순위 산출값

## fail-soft 처리 규칙

| 상황 | 처리 |
|---|---|
| `sensor_readings.substation_id` 또는 `sensor_readings.ts` 없음 | 명확한 `ValueError` 발생 |
| invalid timestamp | 전처리 집계에서 제외하고 `invalid_timestamp_rows_in_file`에 기록 |
| numeric 변환 실패 | `NaN`으로 처리 |
| control/status 결측 | `"missing"`으로 처리 |
| 고장/정비 이벤트 없음 | `days_since_last_* = NaN`, stabilization flag는 `False` |
| 설비 정보 없음 | `configuration_type = "missing"`, `has_dhw/has_buffer_tank = null` |

## 산출물 위치

- DDL: `schema/sql/005_preprocessed_windows.sql`
- JSON Schema: `schema/json/preprocessed_windows.schema.json`
- 생성 규칙: `schema/column_name_mapping.md`
- 상세/근거: `schema/README.md`
