# 06 thermal feature experiment

## 목적

오탐/미탐 audit에서 반복적으로 보인 thermal feature를

- raw 유지
- group z-score 추가
- 관계식 feature 추가
- raw를 관계식으로 대체

형태로 비교하여, 어떤 표현이 더 안정적인지 확인한다.

## 실행 파일

```text
PREPROCESSING/osj/06_thermal_feature_experiment.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_thermal_feature_experiment.csv
data/processed/ml_risk/lgbm_thermal_feature_experiment_holdout.csv
```

## 대상 thermal feature

핵심 raw 후보:

```text
network_temperature_gap__mean
p_net_return_temperature__max
p_net_return_temperature__mean
p_net_supply_temperature__mean
p_net_supply_temperature__max
s_dhw_upper_storage_temperature__last
s_dhw_upper_storage_temperature__max
```

관계식 후보:

```text
p_net_supply_minus_return_mean
p_net_supply_minus_return_max
s_dhw_upper_minus_supply_last
s_dhw_upper_minus_supply_max
hc1_supply_setpoint_gap_mean
network_gap_over_outdoor_mean
return_temp_over_outdoor_mean
```

## 비교 variant

```text
baseline_raw
group_zscore_only
relation_only
group_zscore_plus_relation
replace_raw_with_relation
```

의미:

- `baseline_raw`: 현재 raw thermal feature 그대로
- `group_zscore_only`: raw 유지 + manufacturer/configuration/season 기준 z-score 추가
- `relation_only`: raw 유지 + 관계식 feature 추가
- `group_zscore_plus_relation`: z-score와 관계식 둘 다 추가
- `replace_raw_with_relation`: 핵심 raw thermal feature를 빼고 관계식으로 대체

## 현재 결과 요약

### holdout overall

`calibrated` 기준으로 가장 나은 variant는:

```text
group_zscore_only
```

결과:

```text
precision 0.5143
recall    0.4186
f1        0.4615
fpr       0.1589
```

같은 실험 안 baseline:

```text
baseline_raw
precision 0.3750
recall    0.2791
f1        0.3200
fpr       0.1869
```

즉 이 실험 구조 안에서는 `group_zscore_only`가 overall holdout 기준 가장 낫다.

### manufacturer 2 / SH holdout

`base` 기준 가장 나은 variant는:

```text
replace_raw_with_relation
```

결과:

```text
precision 0.7143
recall    0.4167
f1        0.5263
fpr       0.0377
```

즉 문제 그룹에서는

```text
raw thermal 절대값보다 관계식 표현이 더 유리하다.
```

## 해석

핵심 해석은 두 갈래다.

### 1. 전체 holdout에서는 z-score 정규화가 가장 안정적

이는 thermal 절대값이 그룹 차이를 타기 때문에,

```text
같은 manufacturer/configuration/season 안에서
얼마나 벗어났는가
```

가 의미가 있다는 뜻이다.

### 2. 문제 그룹에서는 raw보다 관계식 대체가 더 유리

특히 `manufacturer 2 / SH`에서는

```text
p_net supply/return 관계
storage vs supply 관계
setpoint gap 관계
```

같은 상대 관계가 raw absolute value보다 더 유효하다.

## 현재 결론

thermal 개선의 1차 방향은 다음처럼 정리된다.

```text
overall 관점:
  group_zscore_only 우선 후보

문제 그룹 관점:
  replace_raw_with_relation 우선 후보
```

즉 아직 바로 하나로 승격하기보다는,

```text
event-context 개선 결과와 조합해서
notebook-native 재검증
```

이 필요하다.

## 다음 액션

```text
1. event-context 최적 후보(bucket_any_task_keep_fault_raw)
2. thermal 최적 후보(group_zscore_only 또는 replace_raw_with_relation)
```

이 둘을 조합한 실험을 한 번 더 돌린다.

그 결과가 좋으면 메인 06 노트북에 반영 후보로 승격한다.
