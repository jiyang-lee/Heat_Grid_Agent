# 06 leadtime improvement experiments

## 목적

현재 pseudo leadtime 모델의 개선 여지를 세 갈래로 나눠 검토했다.

1. 시간흐름 feature 보강
2. 버킷 재설계
3. pseudo label 정제

기준선은 현재 공식 3버킷 모델이다.

```text
0-24h
1-3d
3-7d
```

## 실행 파일

```text
PREPROCESSING/osj/06_leadtime_improvement_experiments.py
```

## 출력 파일

```text
data/processed/ml_leadtime/leadtime_timeflow_experiment.csv
data/processed/ml_leadtime/leadtime_timeflow_experiment_holdout.csv
data/processed/ml_leadtime/leadtime_bucket_redesign_experiment.csv
data/processed/ml_leadtime/leadtime_bucket_redesign_experiment_holdout.csv
data/processed/ml_leadtime/leadtime_label_refinement_experiment.csv
data/processed/ml_leadtime/leadtime_label_refinement_experiment_holdout.csv
```

## 1. 시간흐름 feature 보강 결과

비교 variant:

```text
baseline
timeflow_lag_delta
timeflow_lag_delta_roll3
```

holdout 결과:

```text
baseline
accuracy  0.6512
macro_f1  0.4329
weighted  0.6385

timeflow_lag_delta
accuracy  0.6512
macro_f1  0.4396
weighted  0.6430

timeflow_lag_delta_roll3
accuracy  0.6512
macro_f1  0.4405
weighted  0.6432
```

해석:

- 정확도는 그대로다.
- 하지만 `macro F1`과 `weighted F1`은 소폭 개선된다.
- 즉 시간흐름 feature는 효과가 있긴 하지만, 아직 개선 폭은 작다.

현재 best candidate:

```text
timeflow_lag_delta_roll3
```

## 2. 버킷 재설계 결과

비교 대상:

```text
current_3bucket
original_4bucket
binary_24h_vs_1_7d
```

holdout 결과:

```text
current_3bucket
accuracy  0.6512
macro_f1  0.4405

original_4bucket
accuracy  0.5814
macro_f1  0.3432

binary_24h_vs_1_7d
accuracy  0.6163
macro_f1  0.6120
```

해석:

- `4버킷`은 명확히 악화된다.
- `3버킷`은 지금 구조에서 가장 균형이 좋다.
- `2버킷`은 문제를 단순화해서 macro F1은 좋아지지만, 현재 3버킷과 직접 대체 비교 대상은 아니다.

정리:

```text
메인 pseudo leadtime 체인은 3버킷 유지
보조 urgency 체인 후보로는 2버킷 검토 가능
4버킷 복귀는 비추천
```

## 3. pseudo label 정제 결과

비교 대상:

```text
no_filter
exclude_recent_task_3d
exclude_recent_task_7d
exclude_recent_any_event_3d
exclude_recent_any_event_7d
exclude_maintenance_related
```

holdout 결과:

- 최근 task/event 기반 필터는 `성능 변화 없음`
- `exclude_maintenance_related`는 오히려 소폭 악화

이유:

holdout pre_fault 86개를 확인해보면

```text
days_since_last_task_event <= 7d : 0 rows
days_since_last_any_event  <= 7d : 0 rows
maintenance_related = 1         : 1 row
```

즉 현재 holdout 분할에서는 이 필터들이 실제로 거의 작동하지 않는다.

## 결론

현재 단계의 결론은 아래와 같다.

1. 시간흐름 feature는 넣을 가치가 있다.
2. 메인 bucket 구조는 여전히 `3버킷`이 맞다.
3. 최근 task/event 기반 pseudo label 정제는 현재 holdout 기준 효과가 없다.

## 현재 추천안

### 공식본

당장은 기존 공식본을 유지한다.

```text
data/processed/ml_leadtime/leadtime_bucket_scores.csv
data/processed/ml_leadtime/leadtime_bucket_metrics.csv
```

### 다음 승격 후보

가장 현실적인 다음 승격 후보는 아래다.

```text
3버킷 유지
+ timeflow_lag_delta_roll3 추가
```

### 보조 체인 후보

운영상 즉시성 판단만 더 단순하게 보고 싶다면 아래를 별도 체인으로 검토할 수 있다.

```text
0-24h vs 1-7d
```

즉,

```text
메인 leadtime = 3버킷
보조 urgency = 2버킷
```

구조가 현재 데이터에는 더 맞다.
