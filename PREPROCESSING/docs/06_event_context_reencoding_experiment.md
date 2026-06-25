# 06 event-context reencoding experiment

## 목적

`days_since_last_fault_event`, `days_since_last_task_event`, `days_since_last_any_event`를
raw 숫자 그대로 쓰는 대신,

- clipping
- bucket encoding

으로 바꿨을 때 holdout 성능이 좋아지는지 비교한다.

## 실행 파일

```text
PREPROCESSING/osj/06_event_context_reencoding_experiment.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_event_context_reencoding_experiment.csv
data/processed/ml_risk/lgbm_event_context_reencoding_holdout.csv
```

## 비교 variant

```text
baseline_raw
clip90_all_event_days
bucket_any_task_keep_fault_raw
bucket_all_event_days
bucket_any_task_clip90_fault
```

의미:

- `baseline_raw`: 기존 raw days
- `clip90_all_event_days`: 세 event day를 90일 상한 clipping
- `bucket_any_task_keep_fault_raw`: task/any는 bucket, fault는 raw 유지
- `bucket_all_event_days`: fault/task/any 모두 bucket
- `bucket_any_task_clip90_fault`: task/any는 bucket, fault는 90일 clipping

## 현재 결과 요약

### holdout overall

`calibrated` 기준으로 가장 나은 variant는:

```text
bucket_any_task_keep_fault_raw
```

결과:

```text
precision 0.4583
recall    0.3837
f1        0.4177
fpr       0.1822
```

같은 실험 안에서의 baseline:

```text
baseline_raw
precision 0.3750
recall    0.2791
f1        0.3200
fpr       0.1869
```

### manufacturer 2 / SH holdout

`base` 기준 가장 나은 variant도:

```text
bucket_any_task_keep_fault_raw
```

결과:

```text
precision 0.7500
recall    0.5000
f1        0.6000
fpr       0.0377
```

즉 문제 그룹에서도 개선 방향이 일관된다.

## 해석

핵심 해석은 다음과 같다.

```text
task/any event distance는 raw 숫자보다 bucket 표현이 더 안정적이고,
fault event distance는 아직 raw 값을 유지하는 편이 낫다.
```

즉 현재 event-context 개선의 1차 후보는:

```text
days_since_last_task_event -> bucket
days_since_last_any_event  -> bucket
days_since_last_fault_event -> raw 유지
```

## 주의사항

이번 실험은 메인 06 노트북을 경량 재학습 형태로 재구성한 비교 실험이다.

따라서:

- variant 간 상대 비교에는 유효하다.
- 하지만 메인 `06` 공식 산출물과 절대 수치가 완전히 일치하지는 않는다.

즉 이 결과는

```text
승격 후보를 고르는 근거
```

로 쓰고,

```text
최종 반영 전에는 notebook-native 재검증
```

이 한 번 더 필요하다.

## 현재 결론

전역 risk 개선 1순위 후보는 아래와 같다.

```text
bucket_any_task_keep_fault_raw
```

다음 단계:

```text
1. false negative audit
2. 그 다음 notebook-native로 event-context 재표현 재검증
3. 이후 thermal feature 재표현 실험
```
