# 06 state thermal combined experiment

## 목적

event-context 1순위 후보였던

```text
state_any_task_keep_fault_raw
```

위에 thermal 후보를 얹었을 때

1. overall holdout이 더 좋아지는지
2. false negative가 더 줄어드는지
3. 현재 공식 calibrated 본을 넘을 수 있는지

를 확인한 실험이다.

## 실행 파일

```text
PREPROCESSING/osj/06_state_thermal_combined_experiment.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_state_thermal_combined_experiment.csv
data/processed/ml_risk/lgbm_state_thermal_combined_experiment_holdout.csv
data/processed/ml_risk/lgbm_state_thermal_combined_false_negative_summary.csv
```

## 비교 variant

```text
baseline_raw
state_any_task_keep_fault_raw
state_plus_group_zscore
state_plus_replace_raw_with_relation
state_plus_group_zscore_plus_relation
```

## 핵심 결과

### overall holdout calibrated

```text
baseline_raw
f1   0.3200
fpr  0.1869
fn   62
fn_1_3d 37

state_any_task_keep_fault_raw
f1   0.4364
fpr  0.2009
fn   50
fn_1_3d 29

state_plus_group_zscore
f1   0.4889
fpr  0.2336
fn   42
fn_1_3d 24

state_plus_replace_raw_with_relation
f1   0.4756
fpr  0.1822
fn   47
fn_1_3d 30
```

해석:

- `state_plus_group_zscore`가 이번 결합 실험의 최고 F1이다.
- false negative도 가장 많이 줄였다.
- 특히 `1-3d FN`이 `37 -> 24`로 크게 감소했다.
- 하지만 그 대가로 FPR이 `0.2336`까지 올라간다.

### manufacturer 2 / SH holdout calibrated

```text
state_plus_group_zscore_plus_relation
f1   0.6667
fpr  0.0000

state_any_task_keep_fault_raw
f1   0.5882
fpr  0.0000
```

해석:

- 문제 그룹만 보면 더 좋아지는 조합이 있다.
- 하지만 메인 승격 판단은 overall holdout 기준이 우선이다.

## 공식 calibrated 본과 비교

현재 공식 운영본:

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
```

이번 결합 실험 최고 후보:

```text
state_plus_group_zscore
precision 0.4681
recall    0.5116
f1        0.4889
fpr       0.2336
```

## 결론

이번 결합 실험은 아래를 확인해줬다.

1. `state_any_task_keep_fault_raw`는 FN 감소 방향으로 유효하다.
2. thermal `group_zscore`를 얹으면 FN은 더 줄일 수 있다.
3. 하지만 현재 공식 calibrated 본보다 overall 성능은 아직 부족하다.

즉 지금 단계 결론은:

```text
state + thermal은 좋은 연구 방향이지만
아직 메인 06 공식본 교체 후보로는 부족하다.
```

## 다음 판단

이제 남은 선택지는 두 가지다.

```text
1. 06 추가개선을 더 이어간다
2. 현재 공식본으로 07/08 연결을 먼저 진행한다
```

현재 기준으로는

```text
risk 공식본은 calibrated 유지
leadtime는 promoted 후보 사용 가능
```

상태가 유지된다.
