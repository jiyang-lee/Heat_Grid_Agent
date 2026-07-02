# 06 combined feature experiment

## 목적

앞선 두 실험에서 방향은 이미 나왔다.

- event-context 쪽 최적 후보: `bucket_any_task_keep_fault_raw`
- thermal 쪽 최적 후보:
  - overall 기준 `group_zscore_only`
  - 문제 그룹(`manufacturer 2 / SH`) 기준 `replace_raw_with_relation`

이번 실험은 이 둘을 같이 넣었을 때 holdout이 실제로 더 좋아지는지 확인하기 위한 결합 비교 실험이다.

## 실행 파일

```text
PREPROCESSING/osj/06_combined_feature_experiment.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_combined_feature_experiment.csv
data/processed/ml_risk/lgbm_combined_feature_experiment_holdout.csv
```

## 비교 variant

```text
baseline_raw
event_context_only
thermal_group_zscore_only
thermal_replace_raw_with_relation
event_plus_group_zscore
event_plus_replace_raw_with_relation
```

의미:

- `baseline_raw`: 기존 raw feature 그대로
- `event_context_only`: event-context만 보강
- `thermal_group_zscore_only`: thermal만 group z-score로 보강
- `thermal_replace_raw_with_relation`: thermal raw 일부를 relation 중심으로 대체
- `event_plus_group_zscore`: event-context + thermal z-score 결합
- `event_plus_replace_raw_with_relation`: event-context + thermal relation 대체 결합

## 판정 기준

이번에도 기존 06과 동일하게 아래를 본다.

- split: `train`, `validation`, `holdout`
- scope: `overall`, `manufacturer_2_sh`
- metric_type: `base`, `calibrated`

주평가 기준은 holdout이며, 특히 아래 두 개를 같이 본다.

```text
f1_high_or_critical
false_positive_rate_high_or_critical
```

## 기대하는 판단

이 실험 결과로 아래 셋 중 하나를 결정한다.

1. event-context만 승격
2. thermal만 승격
3. 둘을 함께 승격

즉 이번 실험은 "보강 후보를 실제 메인 06에 반영할지" 결정하는 마지막 비교 단계다.

## 결과 요약

### holdout overall

`calibrated` 기준 최고 F1은 여전히 thermal 단독 보강 쪽이다.

```text
thermal_group_zscore_only
precision 0.5143
recall    0.4186
f1        0.4615
fpr       0.1589
```

결합 후보 비교:

```text
event_plus_group_zscore
precision 0.4486
recall    0.5581
f1        0.4974
fpr       0.2757

event_plus_replace_raw_with_relation
precision 0.3906
recall    0.2907
f1        0.3333
fpr       0.1822
```

해석:

- `event_plus_group_zscore`는 F1만 보면 높지만 FPR이 너무 커진다.
- `event_plus_replace_raw_with_relation`는 overall 기준으로 오히려 악화된다.
- 따라서 overall 운영 기준에서는 `thermal_group_zscore_only`가 더 안정적이다.

### manufacturer 2 / SH holdout

`calibrated` 기준 최고는 event-context가 들어간 조합들이다.

```text
event_context_only
precision 1.0000
recall    0.4167
f1        0.5882
fpr       0.0000

event_plus_group_zscore
precision 1.0000
recall    0.4167
f1        0.5882
fpr       0.0000

event_plus_replace_raw_with_relation
precision 1.0000
recall    0.4167
f1        0.5882
fpr       0.0000
```

해석:

- 문제 그룹에서는 event-context 보강이 핵심이다.
- thermal을 추가로 얹어도 calibrated 기준 성능이 더 좋아지지 않는다.
- 즉 이 그룹에서는 `bucket_any_task_keep_fault_raw`가 본질 개선이다.

## 현재 결론

이번 결합 실험 기준으로는 아래처럼 정리된다.

```text
overall 기본 승격 후보
  thermal_group_zscore_only

문제 그룹 보강 후보
  event_context_only

결합형 전면 승격
  보류
```

즉, "좋은 후보 두 개를 그냥 합치면 더 좋아질 것"이라는 가정은 이번 데이터에서는 성립하지 않았다.
