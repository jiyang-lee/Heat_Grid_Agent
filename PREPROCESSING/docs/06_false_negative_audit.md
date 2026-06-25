# 06 false negative audit

## 목적

holdout에서 실제 `pre_fault`인데도

```text
risk_level_calibrated가 low 또는 medium
```

으로 남은 샘플을 따로 분석한다.

즉 질문은 다음이다.

```text
왜 진짜 위험 구간인데 high/critical까지 못 올라갔는가?
```

## 실행 파일

```text
PREPROCESSING/osj/06_false_negative_audit.py
```

## 출력 파일

```text
data/processed/ml_risk/holdout_false_negative_rows.csv
data/processed/ml_risk/holdout_false_negative_feature_summary.csv
data/processed/ml_risk/holdout_false_negative_vs_true_positive_compare.csv
```

## 비교 기준

- split: `split_event_regime_based == holdout`
- 실제 라벨: `label == pre_fault`
- false negative:
  - `risk_level_calibrated`가 `low` 또는 `medium`
- true positive:
  - `risk_level_calibrated`가 `high` 또는 `critical`

현재 개수:

```text
holdout false negatives: 42
holdout true positives: 44
```

## 핵심 결과

true positive와 비교했을 때,
false negative에서는 아래 feature가 충분히 양수 기여를 못 받거나 음수로 눌린다.

상위 gap feature:

```text
days_since_last_any_event
p_net_return_temperature__max
s_dhw_upper_storage_temperature__last
s_dhw_3-way_valve_status__dominant__is__missing
doy_sin
anomaly_score
days_since_last_task_event
p_net_return_temperature__mean
day_of_year
network_temperature_gap__mean
```

### 가장 중요한 해석

#### 1. `days_since_last_any_event`가 false negative에서 음수로 작동하는 경우가 많다

이 feature는 false positive audit에서는 오탐을 밀어올리는 쪽이었지만,
false negative audit에서는 오히려 위험 점수를 충분히 못 올리는 방향으로도 나타난다.

즉:

```text
event-context feature가 현재는
어떤 그룹에서는 과민반응,
어떤 그룹에서는 과소반응
둘 다 만들고 있다.
```

이건 raw days 표현이 불안정하다는 근거다.

#### 2. thermal feature도 false negative에서 눌린다

특히:

```text
p_net_return_temperature__max
p_net_return_temperature__mean
network_temperature_gap__mean
s_dhw_upper_storage_temperature__last
```

이런 feature는 true positive에서는 점수를 올리는데,
false negative에서는 그 정도가 약하거나 음수로 작동한다.

즉 thermal feature 표현도 현재 불안정하다.

#### 3. false negative는 특정 한 그룹만의 문제가 아니다

대표적으로 보인 구간:

```text
manufacturer 1 / substation 12
manufacturer 1 / substation 13
manufacturer 1 / substation 26
manufacturer 2 / substation 18
manufacturer 2 / substation 24
manufacturer 2 / substation 45
manufacturer 2 / substation 53
```

그리고 lead time bucket 기준으로는

```text
1-3d
6-24h
```

구간에서 많이 나타난다.

즉 지금 calibration만으로는 잡히지 않는

```text
중간 단계 pre_fault
```

미탐 문제가 남아 있다.

## 샘플 패턴

false negative 샘플에서는 아래 패턴이 반복된다.

```text
positive:
  days_since_last_task_event
  day_of_year
  anomaly_score
  p_net_return_temperature__max
  network_temperature_gap__mean

negative:
  days_since_last_any_event
  s_dhw_lower_storage_temperature__last
  p_net_supply_temperature__mean/max
  s_dhw_upper_storage_temperature__max
  network_temperature_gap__mean
```

즉 일부 feature는 동시에

```text
오탐 증가 원인
미탐 증가 원인
```

둘 다 될 수 있다.

이건 전역 삭제보다

```text
표현 변경
```

이 더 중요하다는 뜻이다.

## 현재 판단

### 우선순위 1

```text
days_since_last_task_event
days_since_last_any_event
```

이 둘은 raw 숫자 그대로 두지 말고,
bucket 또는 clipping 실험을 계속 가져가는 것이 맞다.

### 우선순위 2

```text
p_net_return_temperature__max/mean
network_temperature_gap__mean
s_dhw_upper_storage_temperature__last
```

이쪽은 thermal feature 재표현 대상이다.

## 다음 액션

```text
1. event-context bucket 실험 결과와 false negative audit을 함께 묶어 해석
2. thermal feature 정규화/관계식화 실험
3. 그 뒤 notebook-native 재학습으로 승격 여부 판단
```

## 현재 실무 결론

false positive audit와 false negative audit을 같이 보면 결론은 같다.

```text
지금 문제는 단일 feature 삭제가 아니라
event-context와 thermal feature의 표현 방식 문제다.
```
