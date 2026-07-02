# 04. 학습용 feature selection 문서

이 문서는 `PREPROCESSING/osj/04_feature_selection.ipynb`의 목적과 산출물 기준을 HeatGrid Agent 프로젝트 관점에서 정리한다.

04번 노트북은 03번에서 만든 `ml_window_dataset.csv`를 바로 모델에 넣지 않고, 실제 baseline 학습에 사용할 행과 컬럼을 확정하는 단계다.

## 프로젝트 관점의 목적

HeatGrid Agent에서 ML은 우선순위를 직접 계산하지 않는다.
대신 Agent가 해석할 수 있는 이상도, 위험도, 리드타임, 근거 센서를 안정적으로 만들 수 있어야 한다.

이를 위해 04번에서는 다음을 고정한다.

- 어떤 행을 학습 후보로 쓸지
- 어떤 컬럼을 feature로 쓸지
- 어떤 컬럼은 metadata로 분리할지
- 어떤 컬럼은 baseline에서 제외할지

즉, 04번의 역할은 모델 성능을 높이는 미세 튜닝이 아니라, 이후 05번 baseline 모델이 재현 가능하게 돌아가도록 입력 계약을 정리하는 것이다.
현재 보강안에서는 여기에 더해, 06 holdout 일반화에 필요한 시간 문맥과 categorical context까지 입력 계약에 포함한다.

## 입력 데이터

04번은 다음 파일을 입력으로 사용한다.

```text
data/processed/ml_windows/ml_window_dataset.csv
```

이 파일은 03번 노트북에서 생성된 산출물이다.

## 행 선택 기준

04번의 기본 학습 후보는 다음 조건을 모두 만족하는 행이다.

```text
use_for_supervised_training == True
label in {normal, pre_fault}
data_quality_issue == False
```

이 기준을 기본값으로 두는 이유는 다음과 같다.

- `unlabeled`는 정상 라벨이 아니다.
- `disturbance_context`, `post_fault_blocked`는 지도학습 기본셋에 바로 넣기 어렵다.
- `data_quality_issue == True`인 구간은 비교 실험용으로는 의미가 있지만, baseline 기준셋으로 두면 품질 문제가 모델 성능 해석을 흐릴 수 있다.

다만 `data_quality_issue == True`를 포함한 relaxed 후보셋도 함께 유지해, 이후 비교 실험에 사용할 수 있도록 한다.

## feature 선택 통계 기준

feature 선택 통계는 전체 strict 후보셋이 아니라 다음 subset에서만 계산한다.

```text
strict 후보셋
+ split_regime_based == train
```

즉, 결측률, 상수 여부, 제조사별 coverage 판단은 regime-aware train split 기준으로만 수행한다.

이 기준을 두는 이유는 다음과 같다.

- validation / holdout 구간 통계를 보고 feature를 고르면 데이터 누수가 생긴다.
- 05번 모델 평가에서 feature 선택까지 포함한 train-only 재현 경로를 유지해야 한다.
- 이후 split 방식이 바뀌어도 동일 원칙을 재사용할 수 있다.

## metadata 분리 기준

다음 계열 컬럼은 baseline 입력 feature에서 제외하고 metadata로 분리한다.

- 식별자: `manufacturer`, `substation_id`, `source_file`
- 시간 범위: `window_start`, `window_end`
- 목표/라벨 관련: `label`, `fault_label`, `fault_event_id`, `estimated_lead_time_hours`
- 설명용 문자열: `main_missing_sensors`, `main_changed_sensors`, `configuration_type`, `season_bucket`, `normal_reference_group`, `*_dominant`
- 학습 제어/분리: `window_source_type`, `use_for_supervised_training`, `split_time_based`, `split_substation_based`, `split_regime_based`
- 해석 보조 또는 누수 우려: `normal_event_related`, `maintenance_related`, `disturbance_count`, `leakage_blocked_fault_count`

이 컬럼들은 모델 입력으로 쓰기보다, 평가/설명/추적 용도로 남기는 편이 안전하다.

## feature 선택 기준

04번의 기본 baseline feature 선택 규칙은 다음과 같다.

### 1. 숫자형 또는 bool형 + 파생 one-hot 사용

원본 문자열 컬럼은 그대로 모델에 넣지 않는다.
대신 low-cardinality categorical은 train split 기준 category를 고정해 one-hot으로 파생한다.

현재 기본 대상:

```text
manufacturer
configuration_type
season_bucket
*_dominant
```

시간의 순환성은 one-hot보다 `sin/cos`가 적합하므로, `hour/dow/doy`는 03에서 만든 numeric cyclic feature를 그대로 사용한다.

### 2. strict train split 기준 결측률 50% 이하

기본 기준:

```text
missing_rate <= 0.50
```

이 기준을 두는 이유는 설비 구성 차이로 일부 센서가 구조적으로 비어 있기 때문이다.
특히 DHW 관련 센서 일부는 coverage가 매우 낮아 baseline 공통 feature로 두기 어렵다.

### 3. 상수 컬럼 제외

strict train split에서 유일값이 1개뿐인 컬럼은 제외한다.

예:

```text
expected_row_count
median_interval_minutes
invalid_timestamp_rows_in_file
```

이런 컬럼은 모델에 정보를 주지 않는다.

### 4. 양 제조사 모두에서 최소한 값이 존재해야 함

기본 baseline은 제조사 공통 feature셋을 사용한다.
따라서 선택된 feature는 manufacturer 1, manufacturer 2 모두에서 non-null 값이 존재해야 한다.

이 기준을 두는 이유는 다음과 같다.

- baseline 단계에서 제조사별 전용 feature에 의존하지 않기 위해
- 하나의 공통 모델 실험을 먼저 단순하게 재현하기 위해
- 이후 manufacturer-specific 실험을 분리하기 쉽게 하기 위해

## 기본 결론

04번의 기본 결과는 다음 형태다.

- feature 선택 통계는 strict train split에서만 계산
- `strict` 학습 후보셋을 baseline 기본셋으로 사용
- `data_quality_issue == True`는 relaxed 비교 실험용으로 남김
- 제조사 공통 numeric/bool feature를 기본으로 두되, 제조사/설비구성/계절/상태 context는 one-hot으로 확장
- 고결측 feature와 상수 컬럼은 제외
- 결측 대체값은 strict train split 통계로만 계산

## 저장 산출물

노트북은 아래 경로에 파일을 저장한다.

```text
data/processed/ml_features/
```

생성 파일:

- `trainable_windows.csv`
  - 기본 학습 입력 파일
  - `trainable_windows_strict_imputed.csv`와 같은 내용
  - 05번 baseline에서 바로 로드할 기본 경로

- `trainable_windows_strict.csv`
  - strict 기준으로 필터링한 raw 학습 후보 행
  - 선택된 feature와 metadata만 포함
  - 결측 대체 전 원본

- `trainable_windows_relaxed.csv`
  - `data_quality_issue == True`를 포함한 relaxed 후보 행
  - 비교 실험용 raw 입력

- `trainable_windows_strict_imputed.csv`
  - strict raw 입력에 train 기준 결측 대체를 적용한 버전

- `trainable_windows_relaxed_imputed.csv`
  - relaxed raw 입력에 strict train 기준 결측 대체를 적용한 버전

- `feature_columns.csv`
  - 전체 feature 후보 요약
  - train 기준 결측률, 유일값 수, 제조사별 coverage, feature family, 선택 여부, 제외 사유 포함

- `metadata_columns.csv`
  - metadata 컬럼 목록과 역할 설명

- `imputation_values.csv`
  - 선택된 feature별 결측 대체값
  - 대체 전략과 train 기준 통계 포함

- `categorical_feature_map.csv`
  - 원본 categorical 컬럼과 one-hot 파생 컬럼 매핑

- `feature_family_summary.csv`
  - `sensor_numeric`, `cyclic_time`, `time_context`, `event_context`, `derived_one_hot`, `control_context`별 요약

## 다음 단계 연결

다음 단계는 05번 baseline 모델링이다.

05번에서는 04번 산출물을 기준으로 다음을 수행한다.

- `trainable_windows.csv` 로드
- `label`을 target으로 사용
- 선택된 feature 컬럼만 입력으로 사용
- `imputation_values.csv`는 train 기준 대체 계약 검증용으로 사용
- baseline 분류 또는 anomaly 모델 학습
- split 기준 성능 비교

04번의 핵심은 다음 한 문장으로 정리할 수 있다.

```text
03번의 넓은 후보 데이터셋을, regime-train 기준 선택과 결측 대체, cyclic time, categorical one-hot 계약이 고정된 05/06 학습 입력으로 좁히는 단계다.
```
