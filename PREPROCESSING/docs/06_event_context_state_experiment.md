# 06 event-context state experiment

## 목적

false negative deep audit 이후,
event-context를 단순 raw day 또는 bucket만 두는 대신
상태형 표현으로 바꿨을 때 holdout 성능과 false negative가 개선되는지 비교했다.

핵심 질문:

```text
days_since_last_fault/task/any_event를
최근성 flag + 과거 존재 여부 + 구간 상태
형태로 바꾸면
1-3d false negative를 줄일 수 있는가?
```

## 실행 파일

```text
PREPROCESSING/osj/06_event_context_state_experiment.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_event_context_state_experiment.csv
data/processed/ml_risk/lgbm_event_context_state_experiment_holdout.csv
data/processed/ml_risk/lgbm_event_context_state_false_negative_summary.csv
```

## 비교 variant

```text
baseline_raw
bucket_any_task_keep_fault_raw
state_any_task_keep_fault_raw
state_all_event_days
state_plus_bucket_any_task_keep_fault_raw
state_plus_bucket_all_event_days
```

## 핵심 결과

### overall holdout calibrated

```text
baseline_raw
f1   0.3200
fpr  0.1869
fn   62
fn_1_3d 28

bucket_any_task_keep_fault_raw
f1   0.4177
fpr  0.1822
fn   53
fn_1_3d 24

state_any_task_keep_fault_raw
f1   0.4364
fpr  0.2009
fn   50
fn_1_3d 21
```

해석:

- `state_any_task_keep_fault_raw`가 overall holdout calibrated 기준 최고 F1이다.
- false negative 수도 가장 적다.
- 특히 `1-3d FN`이 `28 -> 21`로 줄었다.
- 다만 FPR은 `0.1822 -> 0.2009`로 약간 올라간다.

즉 이번 실험은

```text
recall / FN 개선은 확실히 있음
대신 FPR을 약간 더 내는 trade-off
```

이다.

### manufacturer 2 / SH holdout base

```text
baseline_raw
f1   0.3125
fpr  0.2830

bucket_any_task_keep_fault_raw
f1   0.6000
fpr  0.0377

state_any_task_keep_fault_raw
f1   0.6316
fpr  0.0189
```

해석:

- 문제 그룹 base 기준으로도 `state_any_task_keep_fault_raw`가 가장 좋다.
- bucket-only보다 더 낫다.

### manufacturer 2 / SH holdout calibrated

```text
bucket_any_task_keep_fault_raw
f1 0.5882
fpr 0.0000

state_any_task_keep_fault_raw
f1 0.5882
fpr 0.0000
```

해석:

- calibrated 기준에서는 bucket-only와 state variant가 동급이다.
- 즉 calibration 후 문제 그룹 성능은 더 좋아지지 않지만,
- overall 쪽 FN 개선은 state variant가 더 강하다.

## false negative 관점 결과

### overall calibrated FN

```text
baseline_raw                  62
bucket_any_task_keep_fault_raw 53
state_any_task_keep_fault_raw  50
```

### overall calibrated 1-3d FN

```text
baseline_raw                  28
bucket_any_task_keep_fault_raw 24
state_any_task_keep_fault_raw  21
```

즉 이번 실험의 가장 큰 의미는

```text
중간 pre_fault(1-3d) FN 감소
```

이다.

## 결론

현재 event-context 보강안 중 1순위 후보는 아래로 정리된다.

```text
state_any_task_keep_fault_raw
```

의미:

- `fault_event`는 raw 유지
- `task_event`, `any_event`는 상태형 표현으로 교체
- 상태형에는 아래가 포함된다.
  - has_previous
  - recent_7d
  - recent_30d
  - recent_90d
  - stale_gt_90d

## 다음 단계

이제 바로 다음은 아래가 맞다.

```text
1. thermal relation/group feature 재실험
2. state_any_task_keep_fault_raw와 thermal 후보를 다시 결합 비교
3. 공식 calibrated 체인 교체 가능 여부 재판단
```
