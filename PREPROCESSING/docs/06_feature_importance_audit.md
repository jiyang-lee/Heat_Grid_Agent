# 06 feature importance audit

## 목적

`06 risk model`에서 새 feature를 더 넣기 전에, 현재 feature가 실제로 무엇을 설명하는지 먼저 점검한다.

이번 audit은 아래 3가지를 함께 본다.

```text
1. LightGBM gain importance
2. LightGBM split importance
3. permutation importance by split
   - train
   - validation
   - holdout
```

핵심은 `train에서 중요해 보이는 feature`와 `holdout에서 실제로 일반화되는 feature`를 분리하는 것이다.

## 실행 파일

```text
PREPROCESSING/osj/06_feature_importance_audit.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_feature_importance_audit.csv
data/processed/ml_risk/lgbm_feature_importance_split_summary.csv
data/processed/ml_risk/lgbm_feature_importance_family_summary.csv
data/processed/ml_risk/lgbm_feature_importance_drift_candidates.csv
```

## 현재 핵심 결과

### 1. holdout에서 실제로 기여한 상위 feature

holdout permutation 기준 상위권은 아래와 같다.

```text
days_since_last_fault_event
doy_sin
s_dhw_upper_storage_temperature__max
p_net_return_temperature__max
s_dhw_3-way_valve_status__dominant__is__aus
anomaly_score
s_dhw_supply_temperature__min
s_dhw_upper_storage_temperature__last
doy_cos
days_since_last_task_event
```

해석:

- `event_context`는 여전히 중요하다.
- `anomaly_score`도 holdout에서 의미가 있다.
- 일부 저장탱크/DHW 계열 온도 feature가 holdout에서 실제 신호를 준다.
- 단순 gain 순위와 holdout 기여 순위는 다르다.

### 2. feature family 요약

```text
event_context    mean_holdout_permutation 0.0223
cyclic_time      mean_holdout_permutation 0.0101
context          mean_holdout_permutation 0.0098
derived_one_hot  mean_holdout_permutation 0.0015
time_context     mean_holdout_permutation 0.0010
sensor_numeric   mean_holdout_permutation 0.0006
```

해석:

- `event_context`가 가장 안정적이다.
- `cyclic_time`도 holdout에서 생각보다 기여한다.
- `sensor_numeric`은 수가 많지만 평균 기여도는 낮다.
- 즉 센서 절대값 feature를 더 늘리는 것보다, 안정적인 관계식/상태 전이 feature를 더 만드는 편이 낫다.

### 3. drift 의심 feature

다음 feature는 train/validation 대비 holdout 기여가 급감하거나 방향이 다르다.

```text
day_of_year
p_net_supply_temperature__max
p_net_supply_temperature__mean
days_since_last_any_event
network_temperature_gap__mean
```

해석:

- `day_of_year`는 train/validation에서는 강하지만 holdout에서는 급감한다.
- `p_net_supply_temperature__mean/max`는 train에서만 먹히고 holdout에서는 오히려 음수 기여다.
- `days_since_last_any_event`는 gain은 매우 높지만 holdout 일반화는 약하다.

이들은 바로 삭제 대상은 아니지만, 다음 보강에서 우선 검토해야 한다.

### 4. holdout-only signal

아래는 train보다 holdout에서만 더 기여한 feature다.

```text
s_dhw_supply_temperature__min
s_dhw_upper_storage_temperature__last
days_since_last_task_event
s_dhw_3-way_valve_status__dominant__is__missing
p_hc1_return_temperature__first
```

해석:

- holdout의 SH/DHW 관련 상태/온도 구조가 train과 다를 가능성이 있다.
- 제조사 2 / SH 계열 잔여 false positive와 연결해서 같이 봐야 한다.

## 현재 판단

### 유지 우선

```text
days_since_last_fault_event
anomaly_score
doy_sin
doy_cos
s_dhw_upper_storage_temperature__max
p_net_return_temperature__max
```

### 재검토 우선

```text
day_of_year
days_since_last_any_event
p_net_supply_temperature__mean
p_net_supply_temperature__max
network_temperature_gap__mean
```

### 바로 결론 내리면 안 되는 것

`gain importance`만 보고 feature를 유지/삭제하면 안 된다.

이유:

- gain은 train 분기 사용량 중심이다.
- holdout permutation과 다를 수 있다.
- 지금처럼 drift가 있는 상황에서는 holdout permutation이 더 중요하다.

## 다음 액션

```text
1. drift 의심 feature 제거 실험
2. event_context 세분화 실험
3. sensor 절대값보다 관계식 feature 우선 추가
4. 04 -> 05 -> 06 재평가
```

우선순위는 `feature 추가`보다 `drift 후보 제거/축소 ablation`이 먼저다.
